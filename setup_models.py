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
    try:
        urllib.request.urlretrieve(url, dest)
        print(f"✅ Downloaded to {dest}")
    except Exception as e:
        print(f"❌ Error downloading {url}: {e}")

def main():
    if not os.path.exists("models"):
        os.makedirs("models")

    # 1. Whisper Tiny (Smaller and faster for Pi)
    whisper_dir = "models/sherpa-onnx-whisper-tiny.en"
    if not os.path.exists(whisper_dir):
        url = "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-whisper-tiny.en.tar.bz2"
        archive_path = "models/whisper.tar.bz2"
        print(f"📥 Downloading Whisper Tiny for Sherpa-ONNX...")
        try:
            urllib.request.urlretrieve(url, archive_path)
            print("📦 Extracting...")
            import tarfile
            with tarfile.open(archive_path, "r:bz2") as tar:
                tar.extractall(path="models")
            os.remove(archive_path)
            print("✅ Whisper model ready.")
        except Exception as e:
            print(f"❌ Error setting up Whisper: {e}")
    else:
        print("✅ Whisper model already exists.")

    # 2. Vision Models (MobileNetV3 ONNX)
    # We download this if not already present
    # Replaced MobileNetV3 with SFace as it's more compatible with OpenCV DNN on RPi
    sface_url = "https://github.com/opencv/opencv_zoo/raw/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx"
    download_file(sface_url, "models/face_recognition_sface_2021dec.onnx")

    # 3. Haar Cascades (Fix for cv2.data attribute error on some systems)
    base_url = "https://raw.githubusercontent.com/opencv/opencv/4.x/data/haarcascades/"
    cascades = [
        "haarcascade_frontalface_default.xml",
        "haarcascade_profileface.xml"
    ]
    for cascade in cascades:
        download_file(base_url + cascade, "models/" + cascade)

    print("🏁 All models checked.")

if __name__ == "__main__":
    main()
