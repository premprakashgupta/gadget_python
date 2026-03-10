"""
gadget/core/audio_engine.py
===========================
Handles local audio capture and speech-to-text using Faster-Whisper.
Optimized for running on low-power devices like Raspberry Pi.
"""

import os
import time
import threading
import queue
import numpy as np
try:
    import pyaudio
    HAS_PYAUDIO = True
except ImportError:
    HAS_PYAUDIO = False

import wave
import json
from vosk import Model, KaldiRecognizer

class AudioEngine:
    def __init__(self, model_path="models/vosk-model-small-hi-0.22", sample_rate=16000):
        """
        model_path: path to the Vosk model directory
        sample_rate: sample rate of the audio (default 16000)
        """
        self.use_sim = not HAS_PYAUDIO
        self.is_recording = False
        self.frames = []
        self.recording_thread = None
        
        # Parallel Processing Queues
        self.transcription_queue = queue.Queue()
        self.result_queue = queue.Queue()
        self.frame_lock = threading.Lock()
        
        # Start background worker immediately
        self.worker_thread = threading.Thread(target=self._transcribe_worker_loop, daemon=True)
        self.worker_thread.start()

        if self.use_sim:
            print("[AudioEngine] ⚠️ PyAudio not found. Running in SIMULATION MODE (returns mock text).")
            self.model = None
            return

        print(f"[AudioEngine] Loading Vosk model from {model_path}...")
        print("[AudioEngine] ⏳ This may take 30-60 seconds on first run or slow systems. Please wait...")
        if not os.path.exists(model_path):
            print(f"[AudioEngine] ❌ Model path not found: {model_path}. Please download the model.")
            self.use_sim = True
            self.model = None
        else:
            self.model = Model(model_path)
            self.sample_rate = sample_rate
            print(f"[AudioEngine] ✅ Vosk Model loaded successfully.")
        
        # Recording settings
        self.format = pyaudio.paInt16
        self.channels = 1
        self.rate = sample_rate
        self.chunk = 1024
        
        try:
            self.audio = pyaudio.PyAudio()
            self.is_recording = False
            self.frames = []
            self.recording_thread = None
            print("[AudioEngine] ✅ Model and Audio Drivers loaded.")
        except Exception as e:
            print(f"[AudioEngine] ⚠️ Failed to init PyAudio: {e}. Switching to SIMULATION.")
            self.use_sim = True

    def _record_loop(self):
        if self.use_sim:
            while self.is_recording:
                time.sleep(0.5)
            return

        stream = self.audio.open(
            format=self.format,
            channels=self.channels,
            rate=self.rate,
            input=True,
            frames_per_buffer=self.chunk
        )
        
        last_log_time = time.time()
        
        while self.is_recording:
            try:
                data = stream.read(self.chunk, exception_on_overflow=False)
                with self.frame_lock:
                    self.frames.append(data)
                
                # Activity meter logging
                # Check amplitude every chunk, but only print at most once every 5 seconds if noisy
                data_np = np.frombuffer(data, dtype=np.int16)
                if len(data_np) > 0:
                    rms = np.abs(data_np).mean()
                    if rms > 150: # Threshold for detectable voice/noise
                        now = time.time()
                        if now - last_log_time > 5.0:
                            print(f"[AudioEngine] 🔊 Microphone Active (Level: {int(rms)})")
                            last_log_time = now
                    elif rms < 5: # Very low, likely silent or dead stream
                         now = time.time()
                         if now - last_log_time > 10.0:
                            print(f"[AudioEngine] 🔇 Microphone Silent (Level: {int(rms)}) - Check settings!")
                            last_log_time = now

            except Exception as e:
                print(f"[AudioEngine] ⚠️ Stream read error: {e}")
            
        stream.stop_stream()
        stream.close()

    def start_recording(self):
        """Start capturing audio in a background thread."""
        if self.is_recording:
            return
        
        print("[AudioEngine] 🎙️ Starting background recording...")
        self.is_recording = True
        self.frames = []
        self.recording_thread = threading.Thread(target=self._record_loop, daemon=True)
        self.recording_thread.start()

    def _transcribe_worker_loop(self):
        """Background thread that waits for audio chunks and transcribes them in parallel."""
        while True:
            # Block until an item is pushed to the queue
            item = self.transcription_queue.get()
            if item is None: 
                break # Poison pill to exit
                
            frames = item['frames']
            timestamp = item['timestamp']
            local_att_id = item['local_att_id']
            
            print(f"[AudioEngine-Worker] ⚙️ Picked up chunk at {timestamp} for processing ({len(frames)} frames). Percentage: 0%...")
            
            if self.use_sim:
                print(f"[AudioEngine-Worker] ⚙️ Processing... 50%...")
                time.sleep(2) # simulate processing time
                mock_text = "[SIMULATED] नमस्ते, आज हम विज्ञान पढ़ेंगे। (Namaste, today we will study science.)"
                print(f"[AudioEngine-Worker] ✅ Processing Complete 100%! Transcript: {mock_text[:30]}...")
                self.result_queue.put({
                    'text': mock_text,
                    'timestamp': timestamp,
                    'local_att_id': local_att_id
                })
                self.transcription_queue.task_done()
                continue
                
            if not frames:
                self.transcription_queue.task_done()
                continue
                
            try:
                # Vosk expects bytes, so we can use the frames directly
                audio_data = b"".join(frames)

                # Initialize recognizer for this chunk
                rec = KaldiRecognizer(self.model, self.sample_rate)
                
                # Diagnostic: check volume of the chunk we just received
                data_np = np.frombuffer(audio_data, dtype=np.int16)
                avg_volume = np.abs(data_np).mean()
                print(f"[AudioEngine-Worker] ⚙️ Processing Vosk AI... (Volume: {int(avg_volume)})")

                rec.AcceptWaveform(audio_data)
                result_json = rec.FinalResult()
                full_text = json.loads(result_json).get("text", "").strip()
                
                if full_text:
                    print(f"[AudioEngine-Worker] ✅ Processing Complete 100%!\n  -> {full_text}")
                    self.result_queue.put({
                        'text': full_text,
                        'timestamp': timestamp,
                        'local_att_id': local_att_id
                    })
                else:
                    print(f"[AudioEngine-Worker] ⚠️ No speech detected in chunk.")

            except Exception as e:
                print(f"[AudioEngine-Worker] ❌ Transcription Failed: {e}")
            finally:
                self.transcription_queue.task_done()

    def queue_for_transcription(self, timestamp_str, local_att_id):
        """
        Takes the current audio frames, replaces them with an empty array instantly (gapless recording),
        and sends the captured frames to the background worker thread.
        """
        if not self.is_recording:
            return

        with self.frame_lock:
            # Steal the frames seamlessly
            captured_frames = self.frames
            self.frames = []
            
        print(f"[AudioEngine] 📤 Sending {len(captured_frames)} audio frames for queue process...")
        self.transcription_queue.put({
            'frames': captured_frames,
            'timestamp': timestamp_str,
            'local_att_id': local_att_id
        })

    def get_finished_transcripts(self):
        """Yields all finished transcripts from the worker thread."""
        results = []
        while not self.result_queue.empty():
            try:
                results.append(self.result_queue.get_nowait())
            except queue.Empty:
                break
        return results

    def stop_and_wait(self):
        """Stop completely (e.g. at end of class or shutdown) and wait for pending transcripts."""
        print("[AudioEngine] 🛑 Shutting down microphone...")
        self.is_recording = False
        if self.recording_thread:
            self.recording_thread.join()
            
        print("[AudioEngine] ⏳ Waiting for any pending background transcripts to finish...")
        self.transcription_queue.put(None) # Poison pill
        if hasattr(self, 'worker_thread') and self.worker_thread:
            self.worker_thread.join(timeout=30)
            
        print("[AudioEngine] ✅ AudioEngine shutdown complete.")
