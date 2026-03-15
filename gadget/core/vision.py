import cv2
import os
import glob
import pickle
import time
from PIL import Image
import numpy as np

# Optimized for Raspberry Pi using Haar Cascades + MobileNetV3 (OpenCV DNN)

class VisionEngine:
    def __init__(self, known_faces_dir, camera_index=0):
        self.known_faces_dir = known_faces_dir
        self.camera_index = camera_index
        self.known_face_encodings = []
        self.known_face_names = []
        
        # 1. Init Haar Cascades for fast face detection (Frontal + Profile)
        # Fix for 'AttributeError: module cv2 has no attribute data' on some systems
        frontal_path = 'models/haarcascade_frontalface_default.xml'
        profile_path = 'models/haarcascade_profileface.xml'
        
        # fallback to cv2.data if local files aren't found
        if not os.path.exists(frontal_path):
            if hasattr(cv2, 'data'):
                frontal_path = os.path.join(cv2.data.haarcascades, 'haarcascade_frontalface_default.xml')
                profile_path = os.path.join(cv2.data.haarcascades, 'haarcascade_profileface.xml')
            else:
                # Last resort fallbacks for Debian
                frontal_path = '/usr/share/opencv4/haarcascades/haarcascade_frontalface_default.xml'
                profile_path = '/usr/share/opencv4/haarcascades/haarcascade_profileface.xml'

        print(f"[VisionEngine] Loading frontal cascade from {frontal_path}")
        self.face_cascade = cv2.CascadeClassifier(frontal_path)
        self.profile_cascade = cv2.CascadeClassifier(profile_path)
        
        if self.face_cascade.empty():
            print(f"⚠️ [VisionEngine] Warning: Frontal cascade is empty! Path: {frontal_path}")
        
        # 2. Init MobileNetV3 via OpenCV DNN
        onnx_model_path = os.path.join(os.path.dirname(__file__), '../../models/mobilenet_v3_small.onnx')
        if not os.path.exists(onnx_model_path):
             # Fallback to local 'models' if relative fails
             onnx_model_path = 'models/mobilenet_v3_small.onnx'
             
        print(f"[VisionEngine] Loading model via OpenCV DNN from {onnx_model_path}")
        self.net = cv2.dnn.readNetFromONNX(onnx_model_path)
        
        # Preprocessing constants (Matching torchvision.transforms.Normalize)
        self.mean = np.array([0.485, 0.456, 0.406]).reshape(1, 1, 3).astype(np.float32)
        self.std = np.array([0.229, 0.224, 0.225]).reshape(1, 1, 3).astype(np.float32)
        
        # 3. Teaching Zone (Normalized: x1, y1, x2, y2)
        # Default: 10% margin on all sides (center 80%)
        self.teaching_zone = (0.1, 0.1, 0.9, 0.9)
            
        self.load_known_faces()

    def get_encodings(self, frame):
        """Returns a list of (embedding, face_center) for ALL faces found in the frame."""
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        
        # Detect frontal faces
        frontal_faces = self.face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=4, minSize=(30, 30))
        # Detect profile faces
        profile_faces = self.profile_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=4, minSize=(30, 30))
        # Also try flipped profile (for the other side)
        flipped_gray = cv2.flip(gray, 1)
        flipped_profile_faces = self.profile_cascade.detectMultiScale(flipped_gray, scaleFactor=1.1, minNeighbors=4, minSize=(30, 30))
        
        # Combine all detections
        faces = list(frontal_faces)
        for (x, y, w, h) in profile_faces:
            faces.append((x, y, w, h))
        for (x, y, w, h) in flipped_profile_faces:
            # Mirror the X coordinate back
            w_frame = frame.shape[1]
            faces.append((w_frame - x - w, y, w, h))
        
        if not faces:
            return None
            
        results = []
        for (x, y, w, h) in faces:
            # Crop and pad
            margin = int(w * 0.2)
            y1, y2 = max(0, y - margin), min(frame.shape[0], y + h + margin)
            x1, x2 = max(0, x - margin), min(frame.shape[1], x + w + margin)
            face_crop = frame[y1:y2, x1:x2]
            
            if face_crop.size == 0: continue
            
            # --- ONNX Preprocessing ---
            # Resize
            face_resize = cv2.resize(face_crop, (224, 224))
            # BGR to RGB
            face_rgb = cv2.cvtColor(face_resize, cv2.COLOR_BGR2RGB)
            # Normalize (0-1)
            face_norm = face_rgb.astype(np.float32) / 255.0
            # Mean/Std subtraction
            face_norm = (face_norm - self.mean) / self.std
            # HWC to CHW and add batch dimension
            face_input = np.transpose(face_norm, (2, 0, 1))[np.newaxis, :]
            
            # --- OpenCV DNN Inference ---
            self.net.setInput(face_input)
            embedding = self.net.forward()
            
            # Normalize embedding (L2)
            norm = np.linalg.norm(embedding, ord=2, axis=1, keepdims=True)
            embedding = embedding / (norm + 1e-6)
            
            # Normalized center
            char_h, char_w = frame.shape[:2]
            face_center = ((x + w/2)/char_w, (y + h/2)/char_h)
            results.append((embedding, face_center))
                
        return results if results else None

    def load_known_faces(self):
        print(f"[VisionEngine] Loading {len(glob.glob(os.path.join(self.known_faces_dir, '*.[jJ][pP][gG]')))} known faces...")
        for i, img_path in enumerate(glob.glob(os.path.join(self.known_faces_dir, "*.[jJ][pP][gG]"))):
            name = os.path.splitext(os.path.basename(img_path))[0]
            pkl_path = img_path + ".pkl"
            
            if os.path.exists(pkl_path):
                with open(pkl_path, 'rb') as f:
                    encoding = pickle.load(f)
            else:
                # For initial loading, we still need a single encoding. get_encodings returns a list.
                # We'll take the first one found in the file.
                img_bgr = cv2.imread(img_path)
                res_list = self.get_encodings(img_bgr) if img_bgr is not None else None
                if res_list:
                    encoding, _ = res_list[0]
                    with open(pkl_path, 'wb') as f:
                        pickle.dump(encoding, f)
                else:
                    print(f"⚠️ Could not detect face in {img_path}")
                    continue
            
            self.known_face_encodings.append(encoding)
            self.known_face_names.append(name)
            # Progress update
            if (i + 1) % 5 == 0 or i == 0:
                print(f"[VisionEngine]   ... {i+1} faces loaded")
        
        print(f"[VisionEngine] ✅ Total {len(self.known_face_names)} faces loaded.")

    def identify_teacher(self, frame=None, current_teacher_name=None, detection_threshold=0.60):
        if frame is None:
            video_capture = cv2.VideoCapture(self.camera_index)
            ret, frame = video_capture.read()
            video_capture.release()
            if not ret:
                return "Camera failed", False, 0.0, None
        
        all_results = self.get_encodings(frame)
        if not all_results or len(self.known_face_encodings) == 0:
            return "Face not clear / No face detected", False, 0.0, None
            
        zx1, zy1, zx2, zy2 = self.teaching_zone
        best_overall_sim = -1.0
        faces = [] # To help the GUI draw all detected faces
        best_match = None
        is_in_zone = False

        # Check EVERY face in the frame
        for encoding, (fx, fy) in all_results:
            is_face_in_zone = (zx1 <= fx <= zx2) and (zy1 <= fy <= zy2)
            face_result = "Unknown Face"
            max_sim = -1.0
            matched_name = "Unknown"
            best_match = None
            for i, known_enc in enumerate(self.known_face_encodings):
                # Dot product similarity (NumPy)
                sim = np.dot(encoding.flatten(), known_enc.flatten())
                if sim > max_sim:
                    max_sim = sim
                    best_match_for_this_face = self.known_face_names[i]
            
            # Update overall best match if this face is better
            if max_sim > best_overall_sim:
                best_overall_sim = max_sim
                best_match = best_match_for_this_face # Update the overall best_match
                is_in_zone = is_face_in_zone # Update overall is_in_zone based on the best match

            faces.append({"box": (fx, fy), "sim": max_sim, "name": best_match_for_this_face if max_sim > detection_threshold else "Unknown"})

            # Use the provided detection_threshold
            effective_threshold = detection_threshold
            if current_teacher_name and best_match_for_this_face == current_teacher_name:
                effective_threshold = detection_threshold - 0.10 # Hysteresis
            
            # If this specific face is a teacher and in zone, return immediately
            if max_sim > effective_threshold and is_face_in_zone:
                return best_match_for_this_face, is_face_in_zone, max_sim, faces
        
        # If no single face was strong enough to return early, return the best found so far
        return best_match if best_match else "Unknown Teacher", is_in_zone, best_overall_sim, faces
        
    def capture_board(self, save_path):
        video_capture = cv2.VideoCapture(self.camera_index)
        video_capture.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
        video_capture.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)
        for _ in range(5): video_capture.read()
        ret, frame = video_capture.read()
        if ret:
            os.makedirs(os.path.dirname(save_path), exist_ok=True)
            cv2.imwrite(save_path, frame)
            video_capture.release()
            return True
        video_capture.release()
        return False

if __name__ == "__main__":
    v = VisionEngine("data/known_faces")
    print("Testing identify:", v.identify_teacher())
