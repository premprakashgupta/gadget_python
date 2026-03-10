import os
import urllib.request
import zipfile

MODEL_URL = "https://alphacephei.com/vosk/models/vosk-model-small-hi-0.22.zip"
DEST_DIR = "models"
ZIP_PATH = os.path.join(DEST_DIR, "vosk-model-small-hi-0.22.zip")

def download_model():
    if not os.path.exists(DEST_DIR):
        os.makedirs(DEST_DIR)
        print(f"Created directory: {DEST_DIR}")

    if os.path.exists(os.path.join(DEST_DIR, "vosk-model-small-hi-0.22")):
        print("Model already exists. Skipping download.")
        return

    print(f"Downloading model from {MODEL_URL}...")
    urllib.request.urlretrieve(MODEL_URL, ZIP_PATH)
    print("Download complete.")

    print("Extracting model...")
    with zipfile.ZipFile(ZIP_PATH, 'r') as zip_ref:
        zip_ref.extractall(DEST_DIR)
    print("Extraction complete.")

    os.remove(ZIP_PATH)
    print("Cleaned up zip file.")

if __name__ == "__main__":
    download_model()
