import os
import urllib.request
import zipfile

# Models required for the system
MODELS = {
    "vision": {
        "url": "https://github.com/premprakashgupta/gadget_python/raw/main/models/mobilenet_v3_small.onnx",
        "dest": "models/mobilenet_v3_small.onnx"
    },
    "vad": {
        "url": "https://github.com/premprakashgupta/gadget_python/raw/main/models/silero_vad.onnx",
        "dest": "models/silero_vad.onnx"
    },
    "whisper": {
        "url": "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-whisper-tiny.en.tar.bz2",
        "dest": "models/sherpa-onnx-whisper-tiny.en",
        "is_archive": True,
        "archive_format": "tar.bz2"
    }
}

def download_file(url, dest):
    if os.path.exists(dest):
        print(f"✅ {dest} already exists.")
        return
    
    print(f"📥 Downloading {url} ...")
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    urllib.request.urlretrieve(url, dest)
    print(f"✅ Downloaded to {dest}")

def main():
    if not os.path.exists("models"):
        os.makedirs("models")

    # For now, we only download if missing. 
    # Note: On RPi, we might already have vision and vad from git if they were pushed.
    
    # Whisper Tiny (Smaller and faster for Pi)
    whisper_dir = "models/sherpa-onnx-whisper-tiny.en"
    if not os.path.exists(whisper_dir):
        url = "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-whisper-tiny.en.tar.bz2"
        archive_path = "models/whisper.tar.bz2"
        print(f"📥 Downloading Whisper Tiny for Sherpa-ONNX...")
        urllib.request.urlretrieve(url, archive_path)
        print("📦 Extracting...")
        import tarfile
        with tarfile.open(archive_path, "r:bz2") as tar:
            tar.extractall(path="models")
        os.remove(archive_path)
        print("✅ Whisper model ready.")
    else:
        print("✅ Whisper model already exists.")

    # Ensure other models are present (fallbacks)
    # The vision engine expects models/mobilenet_v3_small.onnx
    # The vad expects models/silero_vad.onnx

if __name__ == "__main__":
    main()
