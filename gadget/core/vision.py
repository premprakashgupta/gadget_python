import cv2
import os
import glob
import pickle
import time
import subprocess
from PIL import Image
import numpy as np

# Optimized for Raspberry Pi using Haar Cascades + MobileNetV3 (OpenCV DNN)

class VisionEngine:
    def __init__(self, known_faces_dir, camera_index=0, use_fswebcam=True):
        self.known_faces_dir = known_faces_dir
        self.camera_index = camera_index
        self.use_fswebcam = use_fswebcam
        self.known_face_encodings = []
        self.known_face_names = []
        
        # Ensure temp directory for fswebcam
        self.temp_dir = "data/temp_frames"
        os.makedirs(self.temp_dir, exist_ok=True)
        
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
        
        # 2. Init Face Recognition (SFace) via OpenCV DNN
        onnx_model_path = 'models/face_recognition_sface_2021dec.onnx'
        if not os.path.exists(onnx_model_path):
             onnx_model_path = os.path.join(os.path.dirname(__file__), '../../models/face_recognition_sface_2021dec.onnx')
             
        print(f"[VisionEngine] Loading SFace model from {onnx_model_path}")
        try:
            # OpenCV 4.5.4+ has built-in FaceRecognizerSF
            self.face_recognizer = cv2.FaceRecognizerSF.create(onnx_model_path, "")
            self.use_sface = True
        except Exception as e:
            print(f"⚠️ [VisionEngine] Could not init FaceRecognizerSF: {e}")
            print("Fallback to generic DNN loading...")
            self.net = cv2.dnn.readNetFromONNX(onnx_model_path)
            self.use_sface = False
        
        # Preprocessing constants (Matching torchvision.transforms.Normalize)
        self.mean = np.array([0.485, 0.456, 0.406]).reshape(1, 1, 3).astype(np.float32)
        self.std = np.array([0.229, 0.224, 0.225]).reshape(1, 1, 3).astype(np.float32)
        
        # 3. Teaching Zone (Normalized: x1, y1, x2, y2)
        # Default: 10% margin on all sides (center 80%)
        self.teaching_zone = (0.1, 0.1, 0.9, 0.9)
            
        self.load_known_faces()
        
        # 4. Persistent Camera Connection
        self.cap = None
        self._init_camera()

    def _init_camera(self):
        """Initializes or re-initializes the persistent camera connection."""
        if self.cap and self.cap.isOpened():
            self.cap.release()
            
        # Try configured index first, then 0-5
        indices_to_try = [self.camera_index, 0, 1, 2, 3, 4, 5]
        seen_indices = []
        
        for idx in indices_to_try:
            if idx in seen_indices: continue
            seen_indices.append(idx)
            
            # Try V4L2 backend first
            cap = cv2.VideoCapture(idx, cv2.CAP_V4L2)
            if cap.isOpened():
                ret, _ = cap.read()
                if ret:
                    print(f"[VisionEngine] 🎥 Connected to camera {idx} (V4L2)")
                    self.cap = cap
                    return
            cap.release()
            
            # Default backend
            cap = cv2.VideoCapture(idx)
            if cap.isOpened():
                ret, _ = cap.read()
                if ret:
                    print(f"[VisionEngine] 🎥 Connected to camera {idx} (Default)")
                    self.cap = cap
                    return
            cap.release()
            
        print("⚠️ [VisionEngine] Could not find any working camera.")
        self.cap = None

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
            
            # --- SFace / DNN Inference ---
            if self.use_sface:
                # SFace expects 112x112
                face_resize = cv2.resize(face_crop, (112, 112))
                # SFace alignCrop normally needs landmarks, but we can try direct feature extraction
                # or just use generic DNN if alignCrop fails. 
                # For Haar results, we use the generic DNN path or SFace.feature on the crop.
                try:
                    # SFace expects BGR 112x112
                    embedding = self.face_recognizer.feature(face_resize)
                except:
                    self.net.setInput(cv2.dnn.blobFromImage(face_resize, 1.0, (112, 112), (0, 0, 0), swapRB=True))
                    embedding = self.net.forward()
            else:
                # Legacy MobileNet / Generic Path
                face_resize = cv2.resize(face_crop, (224, 224))
                face_rgb = cv2.cvtColor(face_resize, cv2.COLOR_BGR2RGB)
                face_norm = face_rgb.astype(np.float32) / 255.0
                face_norm = (face_norm - self.mean) / self.std
                face_input = np.transpose(face_norm, (2, 0, 1))[np.newaxis, :]
                
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
                try:
                    with open(pkl_path, 'rb') as f:
                        encoding = pickle.load(f)
                except Exception as e:
                    print(f"⚠️ [VisionEngine] Pickling error for {pkl_path} ({e}). This is likely a legacy PyTorch tensor. Deleting and regenerating with newer model...")
                    os.remove(pkl_path)
                    img_bgr = cv2.imread(img_path)
                    res_list = self.get_encodings(img_bgr) if img_bgr is not None else None
                    if res_list:
                        encoding, _ = res_list[0]
                        with open(pkl_path, 'wb') as f:
                            pickle.dump(encoding, f)
                    else:
                        print(f"⚠️ Could not detect face in {img_path} for fallback regeneration.")
                        continue
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

    def _capture_fswebcam(self, output_path):
        """Captures a frame using fswebcam command line tool."""
        dev_path = f"/dev/video{self.camera_index}"
        try:
            # We use a slight delay (-S 1) for auto-exposure to settle if needed
            cmd = ["fswebcam", "-d", dev_path, "-r", "1280x720", "--no-banner", output_path]
            # Redirecting output to avoid cluttering logs
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return os.path.exists(output_path)
        except Exception as e:
            print(f"⚠️ [VisionEngine] fswebcam failed: {e}")
            return False

    def _init_camera(self):
        """Initializes or re-initializes the persistent camera connection (for OpenCV path)."""
        if self.use_fswebcam: return # Not used in fswebcam mode
        
        if self.cap and self.cap.isOpened():
            self.cap.release()
            
        indices_to_try = [self.camera_index] + list(range(6))
        for idx in set(indices_to_try):
            cap = cv2.VideoCapture(idx, cv2.CAP_V4L2)
            if cap.isOpened():
                ret, _ = cap.read()
                if ret:
                    print(f"[VisionEngine] 🎥 Connected to camera {idx} (V4L2)")
                    self.cap = cap
                    return
            cap.release()
        
        print("⚠️ [VisionEngine] Could not find any working camera for OpenCV.")
        self.cap = None

    def identify_teacher(self, frame=None, current_teacher_name=None, detection_threshold=0.60):
        if frame is None:
            if self.use_fswebcam:
                temp_frame_path = os.path.join(self.temp_dir, f"frame_{int(time.time())}.jpg")
                if self._capture_fswebcam(temp_frame_path):
                    frame = cv2.imread(temp_frame_path)
                    try: os.remove(temp_frame_path) 
                    except: pass
                
                if frame is None:
                    return "Camera failed (fswebcam error)", False, 0.0, None
            else:
                if not self.cap or not self.cap.isOpened():
                    self._init_camera()
                
                if not self.cap or not self.cap.isOpened():
                    return "Camera failed (Not opened)", False, 0.0, None
                
                ret, frame = self.cap.read()
                if not ret:
                    return "Camera failed (No frame)", False, 0.0, None
        
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
        if self.use_fswebcam:
            return self._capture_fswebcam(save_path)
        
        if not self.cap or not self.cap.isOpened():
            self._init_camera()
            
        if not self.cap or not self.cap.isOpened():
            return False
            
        # Temporarily increase resolution for snapshot
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)
        
        # Flush buffer
        for _ in range(5): self.cap.read()
        ret, frame = self.cap.read()
        
        # Reset resolution for faster monitoring
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        
        if ret:
            os.makedirs(os.path.dirname(save_path), exist_ok=True)
            cv2.imwrite(save_path, frame)
            return True
        return False

    def __del__(self):
        if hasattr(self, 'cap') and self.cap:
            self.cap.release()

if __name__ == "__main__":
    v = VisionEngine("data/known_faces")
    print("Testing identify:", v.identify_teacher())
