import requests
import json
import os
import uuid
import socket
import time
import subprocess
import platform

class SyncManager:
    def __init__(self, base_url):
        self.base_url = base_url.rstrip('/')
        self.hardware_id = self._get_hardware_id()
        self.device_secret = None
        self.school_id = None

    def _get_hardware_id(self):
        """
        Generates a stable hardware ID. 
        On Raspberry Pi (Linux): Uses the CPU serial number.
        On Windows: Uses the UUID from 'wmic'.
        Fallback: hostname + MAC address (uuid.getnode).
        """
        try:
            if platform.system() == "Linux":
                # Raspberry Pi specific: try to get CPU serial
                # Generally found in /proc/cpuinfo
                with open('/proc/cpuinfo', 'r') as f:
                    for line in f:
                        if line.startswith('Serial'):
                            return f"{socket.gethostname()}-{line.split(':')[1].strip()}"
            
            elif platform.system() == "Windows":
                # Use wmic to get a stable UUID
                cmd = 'wmic csproduct get uuid'
                uuid_bytes = subprocess.check_output(cmd, shell=True, stderr=subprocess.DEVNULL)
                uuid_str = uuid_bytes.decode().split('\n')[1].strip() if uuid_bytes else None
                if uuid_str:
                    return f"{socket.gethostname()}-{uuid_str}"

        except Exception as e:
            print(f"[SyncManager] Warning getting stable ID: {e}")

        # Fallback to the original method (Mac Address based)
        return f"{socket.gethostname()}-{uuid.getnode()}"

    def register_device(self, name=None):
        payload = {"hardwareId": self.hardware_id, "name": name}
        try:
            requests.post(f"{self.base_url}/api/gadgets/register", json=payload)
            return True
        except:
            return False

    def check_activation_status(self):
        try:
            response = requests.get(f"{self.base_url}/api/gadgets/status/{self.hardware_id}")
            if response.status_code == 200:
                data = response.json()
                # Consider active if we have a secret, regardless of exact status string
                if data.get('deviceSecret'):
                    self.school_id = data['schoolId']
                    self.device_secret = data['deviceSecret']
                    return True
            return False
        except:
            return False

    def _get_headers(self):
        return {
            "X-Device-Secret": self.device_secret,
            "X-Hardware-Id": self.hardware_id
        }

    def get_teachers(self):
        try:
            response = requests.get(
                f"{self.base_url}/api/sync/teachers/{self.school_id}",
                headers=self._get_headers()
            )
            return response.json() if response.status_code == 200 else []
        except:
            return []

    # ─── Provisioning ─────────────────────────────────────────────────────────

    def provision_gadget(self, known_faces_dir, config_path):
        """
        Downloads all teacher face images and derives the monitoring window
        from the school timetable. Stores monitoring window in config.yaml.

        Returns: { teachers: [...], monitoringWindow: { startTime, endTime } }
        """
        print("[Provision] Fetching resources from server...")
        try:
            res = requests.get(
                f"{self.base_url}/api/sync/resources",
                headers=self._get_headers(),
                timeout=15
            )
            if res.status_code != 200:
                print(f"[Provision] [X] Server error: {res.status_code} - {res.text[:100]}")
                return None
        except Exception as e:
            print(f"[Provision] [X] Cannot reach server: {e}")
            return None

        data = res.json()
        teachers         = data.get('teachers', [])
        monitoring_window = data.get('monitoringWindow', {'startTime': '08:00', 'endTime': '17:00'})

        os.makedirs(known_faces_dir, exist_ok=True)

        # ── Download face images ──────────────────────────────────────────────
        downloaded = 0
        skipped    = 0
        for teacher in teachers:
            name     = teacher.get('name', 'Unknown')
            face_url = teacher.get('faceImageUrl')
            if not face_url:
                print(f"[Provision]   [!] {name} - no face image on server, skipping")
                skipped += 1
                continue

            save_path = os.path.join(known_faces_dir, f"{name}.jpg")
            try:
                img_res = requests.get(face_url, timeout=10)
                if img_res.status_code == 200:
                    with open(save_path, 'wb') as f:
                        f.write(img_res.content)
                    print(f"[Provision]   [OK] {name} face downloaded -> {save_path}")
                    downloaded += 1
                else:
                    print(f"[Provision]   [X] {name} face URL returned {img_res.status_code}")
            except Exception as e:
                print(f"[Provision]   [X] {name} download error: {e}")

        print(f"[Provision] Faces: {downloaded} downloaded, {skipped} skipped (no image)")

        # ── Update monitoring window in config.yaml ───────────────────────────
        try:
            import yaml as _yaml
            with open(config_path) as f:
                cfg = _yaml.safe_load(f)

            cfg['monitoring']['start_time'] = monitoring_window['startTime']
            cfg['monitoring']['end_time']   = monitoring_window['endTime']

            with open(config_path, 'w') as f:
                _yaml.dump(cfg, f, default_flow_style=False, allow_unicode=True)

            print(f"[Provision] [OK] Monitoring window set: "
                  f"{monitoring_window['startTime']} -> {monitoring_window['endTime']}")
        except Exception as e:
            print(f"[Provision] [!] Could not update config.yaml: {e}")

        # ── Tell server provisioning is done ──────────────────────────────────
        try:
            requests.post(
                f"{self.base_url}/api/gadgets/clear-provision/{self.hardware_id}",
                timeout=5
            )
        except Exception:
            pass

        print(f"[Provision] [OK] Done - gadget provisioned successfully")
        return data

    def check_provision_requested(self):
        """Return True if Principal requested a resource re-provision."""
        try:
            res = requests.get(
                f"{self.base_url}/api/gadgets/provision-status/{self.hardware_id}",
                timeout=5
            )
            if res.status_code == 200:
                return res.json().get('provisionRequested', False)
        except Exception:
            pass
        return False

    # ─── Sync & Upload ────────────────────────────────────────────────────────

    def sync_attendance(self, teacher_id, date, status, entry_time, exit_time=None):
        payload = {
            "teacherId": teacher_id, 
            "date": date, 
            "status": status, 
            "entryTime": entry_time,
            "exitTime": exit_time
        }
        try:
            res = requests.post(f"{self.base_url}/api/sync/attendance", json=payload, headers=self._get_headers())
            return res.json() if res.status_code == 201 else None
        except:
            return None

    def log_session_activity(self, attendance_id, timestamp, activity_type, image_path=None, transcript=None):
        """
        Log either a transcript segment or a proof snapshot.
        type: 'TRANSCRIPT' or 'SNAPSHOT'
        """
        # Note: server expects 'timestamp', 'type', 'imagePath', 'transcript'
        payload = {
            "attendanceId": attendance_id,
            "timestamp": timestamp,
            "type": activity_type,
            "transcript": transcript
        }
        
        files = None
        if image_path and os.path.exists(image_path):
            files = {'file': open(image_path, 'rb')}

        try:
            res = requests.post(
                f"{self.base_url}/api/sync/session-activity",
                data=payload,
                files=files,
                headers=self._get_headers()
            )
            return res.json() if res.status_code == 201 else None
        except Exception as e:
            print(f"[Sync] Exception uploading activity: {e}")
            return None
        finally:
            if files:
                files['file'].close()

    def check_sync_requested(self):
        """Return True if the Principal has requested a manual sync for this device."""
        try:
            res = requests.get(
                f"{self.base_url}/api/gadgets/sync-status/{self.hardware_id}",
                timeout=5
            )
            if res.status_code == 200:
                return res.json().get('syncRequested', False)
        except Exception:
            pass
        return False
