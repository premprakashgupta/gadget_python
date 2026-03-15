"""
gadget/core/sherpa_engine.py
===========================
Handles continuous audio capture and speech-to-english translation using Sherpa-ONNX.
Optimized for Raspberry Pi 4GB with background queue processing.
"""

import os
import time
import threading
import queue
import numpy as np
import sounddevice as sd
import sherpa_onnx

class SherpaAudioEngine:
    def __init__(self, model_dir="models/sherpa-onnx-whisper-base", sample_rate=16000):
        """
        model_dir: path to the whisper onnx model directory
        sample_rate: sample rate of the audio (default 16000)
        """
        self.sample_rate = sample_rate
        self.model_dir = model_dir
        self.is_recording = False
        self.frames_buffer = []
        self.frame_lock = threading.Lock()
        
        # Parallel Processing Queues
        self.transcription_queue = queue.Queue()
        self.result_queue = queue.Queue()
        
        # Initialize Sherpa-ONNX
        self._init_recognizer()

        # Start background worker
        self.worker_thread = threading.Thread(target=self._transcribe_worker_loop, daemon=True)
        self.worker_thread.start()
        
        # Audio stream
        self.stream = None
        
        # VAD Initialization (Silero)
        self._init_vad()

    def _init_recognizer(self):
        # Dynamically find files (supports both 'base' and 'small' prefixes)
        files = os.listdir(self.model_dir)
        encoder_path = None
        decoder_path = None
        tokens_path = None

        for f in files:
            if f.endswith("encoder.onnx") or f.endswith("encoder.int8.onnx"):
                encoder_path = os.path.join(self.model_dir, f)
            elif f.endswith("decoder.int8.onnx"):
                decoder_path = os.path.join(self.model_dir, f)
            elif f.endswith("tokens.txt"):
                tokens_path = os.path.join(self.model_dir, f)

        if not all([encoder_path, decoder_path, tokens_path]):
            raise FileNotFoundError(f"Required model files missing in {self.model_dir}. Need encoder, decoder, and tokens.")

        print(f"[SherpaEngine] Loading Whisper Model: {encoder_path}")
        self.recognizer = sherpa_onnx.OfflineRecognizer.from_whisper(
            encoder=encoder_path,
            decoder=decoder_path,
            tokens=tokens_path,
            num_threads=4,
            task="translate", # Hindi -> English translation
        )
        print(f"[SherpaEngine] ✅ AI Engine initialized: {os.path.basename(self.model_dir)}")

    def _init_vad(self):
        """Initialize the Silero VAD detector to filter noise."""
        vad_path = "models/silero_vad.onnx"
        if not os.path.exists(vad_path):
            print("[SherpaEngine] ⚠️ VAD model not found. Proceeding with energy-only filter.")
            self.vad = None
            return

        vad_config = sherpa_onnx.VadModelConfig()
        vad_config.silero_vad.model = vad_path
        vad_config.silero_vad.min_speech_duration = 0.5   # Don't trigger on clicks/pops
        vad_config.silero_vad.min_silence_duration = 1.0  # More stable chunks
        vad_config.silero_vad.window_size = 512
        vad_config.sample_rate = self.sample_rate

        self.vad = sherpa_onnx.VoiceActivityDetector(vad_config, buffer_size_in_seconds=60)
        print("[SherpaEngine] ✅ Silero VAD initialized for noise filtering.")

    def _audio_callback(self, indata, frames, time, status):
        """This is called by sounddevice for every audio chunk."""
        if status:
            print(f"[SherpaEngine] ⚠️ Audio Status: {status}")
        with self.frame_lock:
            self.frames_buffer.append(indata.copy())

    def start_recording(self):
        """Start capturing audio in a continuous background stream."""
        if self.is_recording:
            return
        
        print("[SherpaEngine] 🎙️ Starting background recording (sounddevice)...")
        self.is_recording = True
        self.frames_buffer = []
        
        try:
            self.stream = sd.InputStream(
                samplerate=self.sample_rate,
                channels=1,
                dtype='float32',
                callback=self._audio_callback
            )
            self.stream.start()
        except Exception as e:
            print(f"⚠️ [SherpaEngine] Audio disabled. Could not connect to microphone: {e}")
            print("⚠️ [SherpaEngine] Please ensure a USB audio adapter with a microphone is plugged in.")
            self.is_recording = False
            self.stream = None

    def _transcribe_worker_loop(self):
        """Background thread that waits for audio chunks and transcribes them in parallel."""
        while True:
            item = self.transcription_queue.get()
            if item is None: 
                break # Poison pill
                
            samples = item['samples']
            timestamp = item['timestamp']
            local_att_id = item['local_att_id']
            
            if len(samples) < 1600: # Less than 0.1 sec
                self.transcription_queue.task_done() # This one is fine as it's outside try
                continue
                
            try:
                # 1. Fast Energy Check (Pre-filter)
                rms = np.sqrt(np.mean(samples**2))
                if rms < 0.005:
                    print(f"[SherpaEngine-Worker] 🔇 Dead silent at {timestamp} (RMS={rms:.5f}), skipping.")
                    continue 

                # 2. VAD Check (Advanced Noise Filter)
                if self.vad:
                    is_speech = False
                    # Reset VAD for this specific chunk check
                    v = self.vad
                    # We feed the samples to VAD. Whisper chunks are usually short (25s)
                    # For a simple "is there ANY speech" check:
                    for i in range(0, len(samples), 512):
                        chunk = samples[i:i+512]
                        if len(chunk) < 512: break
                        v.accept_waveform(chunk)
                        if v.is_speech_detected():
                            is_speech = True
                            # We can stop early if speech found
                            break
                    
                    # Clear VAD internal buffer for next time
                    v.reset()

                    if not is_speech:
                        print(f"[SherpaEngine-Worker] 🌫️ Filtered background noise/fan at {timestamp} (RMS={rms:.5f}).")
                        continue

                print(f"[SherpaEngine-Worker] 🗣️ Speech detected at {timestamp} (RMS={rms:.5f}). Processing...")
                
                s = self.recognizer.create_stream()
                s.accept_waveform(self.sample_rate, samples)
                self.recognizer.decode_stream(s)
                
                text = s.result.text.strip()
                if text:
                    print(f"[SherpaEngine-Worker] ✅ Transcript: {text}")
                    self.result_queue.put({
                        'text': text,
                        'timestamp': timestamp,
                        'local_att_id': local_att_id
                    })
                else:
                    print(f"[SherpaEngine-Worker] ⚠️ No speech detected in chunk.")

            except Exception as e:
                print(f"[SherpaEngine-Worker] ❌ Transcription Failed: {e}")
            finally:
                self.transcription_queue.task_done()

    def queue_for_transcription(self, timestamp_str, local_att_id):
        """Captures current buffer and tasks the worker thread."""
        if not self.is_recording:
            return

        with self.frame_lock:
            if not self.frames_buffer:
                return
            captured_frames = self.frames_buffer
            self.frames_buffer = []
            
        # Flatten the list of numpy arrays into one long array
        samples = np.concatenate(captured_frames).flatten()
        
        print(f"[SherpaEngine] 📤 Queueing {len(samples)/self.sample_rate:.1f}s for AI translation...")
        self.transcription_queue.put({
            'samples': samples,
            'timestamp': timestamp_str,
            'local_att_id': local_att_id
        })

    def get_finished_transcripts(self):
        """Returns all finished transcripts."""
        results = []
        while not self.result_queue.empty():
            try:
                results.append(self.result_queue.get_nowait())
            except queue.Empty:
                break
        return results

    def stop_and_wait(self):
        """Closes stream and waits for worker."""
        print("[SherpaEngine] 🛑 Shutting down stream...")
        self.is_recording = False
        if self.stream:
            self.stream.stop()
            self.stream.close()
            
        print("[SherpaEngine] ⏳ Flushing background transcripts...")
        self.transcription_queue.put(None)
        self.worker_thread.join(timeout=10)
        print("[SherpaEngine] ✅ Shutdown complete.")
