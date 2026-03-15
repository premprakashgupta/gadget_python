import time
import datetime
import os
import yaml
import warnings
warnings.filterwarnings("ignore", category=UserWarning, module="torch")

from gadget.core.vision import VisionEngine
from gadget.core.sherpa_engine import SherpaAudioEngine
from gadget.utils.sync_manager import SyncManager
from gadget.utils.local_db import (
    init_db, upsert_attendance, update_pulse,
    insert_activity, get_stats
)

CONFIG_PATH = os.path.join(os.path.dirname(__file__), 'config/config.yaml')

def load_config():
    with open(CONFIG_PATH, 'r') as f:
        return yaml.safe_load(f)

class ClassroomMonitor:
    def __init__(self):
        self.config = load_config()
        self.sync = SyncManager(self.config['api']['url'])
        self.active_local_att = None
        
        self.last_snapshot_time = 0
        self.last_transcript_time = 0
        self.last_sync_time = time.time() # Track last auto-sync
        self.poll_counter = 0
        
        self.teacher_map = {}
        self.last_seen_time = 0
        self.presence_grace_seconds = 120  # 2 mins to handle whiteboard teaching
        self.is_present = False

        # Init local SQLite buffer
        init_db()

        # Discovery Handshake with server
        hostname = os.environ.get('COMPUTERNAME', os.environ.get('HOSTNAME', 'WinDevice'))
        self.sync.register_device(name=f"Classroom Gadget - {hostname}")

    def wait_for_activation(self):
        print(f"Device Discovery ID: {self.sync.hardware_id}")
        print("Waiting for Super Admin activation in web portal...")
        while not self.sync.check_activation_status():
            time.sleep(10)
        print(f"Device Activated for School ID: {self.sync.school_id}")

    def provision(self):
        """Download face images from server and sync monitoring window from timetable."""
        print("[Main] Starting gadget provisioning...")
        result = self.sync.provision_gadget(
            known_faces_dir=self.config['storage']['known_faces_dir'],
            config_path=CONFIG_PATH
        )
        if result:
            # Reload config (monitoring window may have changed)
            self.config = load_config()
            print(f"[Main] Monitoring window: "
                  f"{self.config['monitoring']['start_time']} -> "
                  f"{self.config['monitoring']['end_time']}")
        return result

    def start_engines(self):
        print("\n" + "="*50)
        print("[!] INITIALIZING ENGINES (Please wait... [TASK])")
        print("="*50)
        
        # 1. Start Vision
        print("[1/2] [EYE] Starting Vision Engine (loading face models)...")
        self.vision = VisionEngine(
            self.config['storage']['known_faces_dir'],
            self.config['monitoring']['camera_index']
        )
        
        # 2. Start Audio
        sherpa_cfg = self.config.get('sherpa', {})
        if sherpa_cfg.get('enabled', True):
            print("[2/2] [MIC] Starting Audio Engine (loading Sherpa-ONNX AI)...")
            self.audio = SherpaAudioEngine(
                model_dir=sherpa_cfg.get('model_dir', 'models/sherpa-onnx-whisper-base'),
                sample_rate=sherpa_cfg.get('sample_rate', 16000)
            )
        else:
            print("[2/2] [MIC] Audio Engine disabled in config.")
            self.audio = None
        
        # 3. Load Metadata
        print("[3/3] [LIST] Syncing teacher metadata...")
        self.load_teachers()
        
        print("="*50)
        print("[OK] ALL ENGINES READY")
        print("="*50 + "\n")

    def load_teachers(self):
        teachers = self.sync.get_teachers()
        self.teacher_map = {t['name']: t['id'] for t in teachers}
        print(f"[Main] Registered {len(self.teacher_map)} teachers.")

    def run(self):
        self.wait_for_activation()

        # First-time provisioning: download faces + timetable from server
        self.provision()

        # --- IMMEDIATE SYNC ON STARTUP ---
        # We do this BEFORE starting heavy frames capture/engines to ensure clean state
        print("[Monitor] [SYNC] Syncing initial data to server...")
        from batch_sync import run_batch_sync
        run_batch_sync()
        self.last_sync_time = time.time()

        self.start_engines()

        print("Monitoring engine engaged (Hybrid Audio+Snapshot mode)...")
        # self.poll_counter = 0 # Moved to __init__

        while True:
            # Reload config each loop (monitoring window might change after re-provision)
            self.config = load_config()
            now_ts = time.time()

            if self.is_monitoring_time():
                self.monitoring_step()
            else:
                self.handle_out_of_monitoring()
                time.sleep(30)

            # --- AUTO SYNC (Every 5 minutes) ---
            if now_ts - self.last_sync_time > 300: # 5 minutes
                print("[Monitor] [WAIT] 5-minute Auto-Sync triggered...")
                from batch_sync import run_batch_sync
                run_batch_sync()
                self.last_sync_time = now_ts

            # Every 6 cycles (~30s): check if Principal triggered manual sync or re-provision
            self.poll_counter += 1
            if self.poll_counter >= 6:
                self.poll_counter = 0

                if self.sync.check_provision_requested():
                    print("[Monitor] [REFRESH] Re-provision requested by Principal - downloading resources...")
                    self.provision()
                    self.start_engines()

                elif self.sync.check_sync_requested():
                    print("[Monitor] [SYNC] Manual sync requested by Principal - running batch sync...")
                    from batch_sync import run_batch_sync
                    run_batch_sync()
                    self.last_sync_time = time.time()

    def handle_out_of_monitoring(self):
        if self.is_present:
            print("[Monitor] Recording hours ended. Closing session.")
            self.mark_exit(datetime.datetime.now().strftime("%H:%M:%S"))

    def is_monitoring_time(self):
        now   = datetime.datetime.now().time()
        start_str = str(self.config['monitoring']['start_time'])
        if ':' not in start_str: start_str = f"{start_str}:00"
        end_str = str(self.config['monitoring']['end_time'])
        if ':' not in end_str: end_str = f"{end_str}:00"

        start = datetime.datetime.strptime(start_str, "%H:%M").time()
        end   = datetime.datetime.strptime(end_str,   "%H:%M").time()
        return start <= now <= end

    def monitoring_step(self):
        # 0. Check for completed background transcripts
        if self.audio:
            finished_transcripts = self.audio.get_finished_transcripts()
            for ft in finished_transcripts:
                insert_activity(
                    local_att_id=ft['local_att_id'],
                    timestamp=ft['timestamp'],
                    type='TRANSCRIPT',
                    transcript=ft['text']
                )
                print(f"[Monitor] [SAVE] Background Transcript saved to DB:\n  -> {ft['text']}")

        # 0b. Get current teacher name for hysteresis if already present
        current_name = None
        if self.is_present and self.active_local_att:
            for name, tid in self.teacher_map.items():
                if tid == self.active_local_att['teacher_id']:
                    current_name = name
                    break

        # Use 0.45 for initial entry (permissive for test), 0.35 to keep session
        effective_threshold = 0.45
        if current_name: # If a teacher is currently present
            # Lowered threshold to maintain existing session
            effective_threshold = 0.35 

        # VERIFY: High-speed face scanning at boundary
        teacher_name, in_zone, max_sim, faces = self.vision.identify_teacher(
            current_teacher_name=current_name,
            detection_threshold=effective_threshold
        )
        now_ts = time.time()
        now_str = datetime.datetime.now().strftime("%H:%M:%S")
        today = datetime.date.today().isoformat()

        # Visual Feedback for console
        if teacher_name != "Face not clear / No face detected" and teacher_name != "Unknown Teacher":
            print(f"[Scan] Seen: {teacher_name} | Similarity: {max_sim:.2f} | In Zone: {in_zone}")
        elif faces:
             print(f"[Scan] Unverified Face | Best Match Similarity: {max_sim:.2f} | In Zone: {in_zone}")

        # EVENT: WALK IN / ENTRY
        if teacher_name and teacher_name in self.teacher_map and in_zone:
            teacher_id = self.teacher_map[teacher_name]
            self.last_seen_time = now_ts

            if not self.is_present or (self.active_local_att and self.active_local_att['teacher_id'] != teacher_id):
                # If switch, mark old teacher out first
                if self.is_present:
                    self.mark_exit(now_str)

                # Log New Entry Event
                self.active_local_att = upsert_attendance(
                    teacher_id=teacher_id,
                    date=today,
                    status='PRESENT',
                    entry_time=now_str
                )
                self.is_present = True
                self.last_transcript_time = now_ts
                self.last_snapshot_time = now_ts
                print(f"[Event] Teacher IN: {teacher_name}. Starting audio capture.")
                if self.audio:
                    self.audio.start_recording()
        
        # EVENT: WALK OUT / EXIT
        else:
            if self.is_present:
                idle_time = now_ts - self.last_seen_time
                
                # We use 2 mins to handle "turning to the board"
                if idle_time > 120:
                    print(f"[Event] Teacher OUT: Verified departure after 120s absence.")
                    self.mark_exit(now_str)

        # Periodic Activities (Only if teacher is present)
        if self.active_local_att and self.is_present:
            # 1. Transcript Capture (every transcript_interval_seconds, default 2 mins)
            elapsed = now_ts - self.last_transcript_time
            interval = self.config['monitoring']['transcript_interval_seconds']
            if elapsed >= interval:
                self.process_transcript()
                self.last_transcript_time = now_ts
                # Notice: self.audio.start_recording() removed because recording is now seamless & continuous

            # 2. Proof Snapshot (e.g., every 10 mins)
            if now_ts - self.last_snapshot_time >= self.config['monitoring']['snapshot_interval_seconds']:
                self.take_proof_snapshot()
                self.last_snapshot_time = now_ts

        time.sleep(self.config['monitoring']['interval_seconds'])

    def mark_exit(self, exit_time_str):
        if self.active_local_att:
            # Save final transcript before leaving
            id_to_mark = self.active_local_att['id']
            if self.audio:
                self.process_transcript()
            
            from gadget.utils.local_db import _conn
            with _conn() as conn:
                conn.execute("UPDATE attendance SET exit_time=?, synced=0 WHERE id=?", (exit_time_str, id_to_mark))
            self.is_present = False
            self.active_local_att = None
            print("[Event] Session closed.")

    def has_internet(self, host="8.8.8.8", port=53, timeout=3):
        """Quick connectivity check: try connecting to Google DNS."""
        # SKIP if localhost (development)
        if 'localhost' in self.config['api']['url'] or '127.0.0.1' in self.config['api']['url']:
            return True

        try:
            import socket
            socket.setdefaulttimeout(timeout)
            socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect((host, port))
            return True
        except OSError:
            return False

    def process_transcript(self):
        if not self.is_present or not self.active_local_att or not self.audio:
            return
        
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        self.audio.queue_for_transcription(timestamp, self.active_local_att['id'])

    def take_proof_snapshot(self):
        if not self.is_present or not self.active_local_att:
            return
            
        timestamp  = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        image_path = os.path.join(
            self.config['storage']['captures_dir'],
            f"proof_{timestamp}.jpg"
        )

        if self.vision.capture_board(image_path):
            insert_activity(
                local_att_id=self.active_local_att['id'],
                timestamp=datetime.datetime.now().strftime("%H:%M:%S"),
                type='SNAPSHOT',
                image_path=image_path
            )
            print(f"[Monitor] [CAM] Proof snapshot logged: {os.path.basename(image_path)}")

if __name__ == "__main__":
    monitor = ClassroomMonitor()
    try:
        monitor.run()
    except KeyboardInterrupt:
        print("\n[Main] Early exit requested via Ctrl+C. Cleaning up...")
        if monitor.is_present:
            now_str = datetime.datetime.now().strftime("%H:%M:%S")
            monitor.mark_exit(now_str)
        
        if hasattr(monitor, 'audio') and monitor.audio:
            monitor.audio.stop_and_wait()
            # Drain any final transcripts that finished during shutdown
            finished_transcripts = monitor.audio.get_finished_transcripts()
            for ft in finished_transcripts:
                insert_activity(
                    local_att_id=ft['local_att_id'],
                    timestamp=ft['timestamp'],
                    type='TRANSCRIPT',
                    transcript=ft['text']
                )
                print(f"[Monitor] [SAVE] Final Transcript saved:\n  -> {ft['text']}")
        
        print("[Main] Cleanup finished. Goodbye!")
