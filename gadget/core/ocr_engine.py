import easyocr
import os

class OCREngine:
    def __init__(self, languages=['en', 'hi']):  # Added 'hi' for Hindi support
        # Note: GPU=True is recommended for performance, but False for compatibility (Pi)
        print("[OCR] Initializing engine with English + Hindi support...")
        self.reader = easyocr.Reader(languages, gpu=False)

    def extract_text(self, image_path):
        """Extracts text from an image and returns as a single string."""
        if not os.path.exists(image_path):
            return ""
        
        results = self.reader.readtext(image_path)
        # results is a list of [box, text, confidence]
        text_list = [res[1] for res in results]
        return " ".join(text_list)

if __name__ == "__main__":
    # Test
    # engine = OCREngine()
    # print(engine.extract_text("data/captures/test_board.jpg"))
    pass
