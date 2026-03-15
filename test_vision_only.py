import cv2
import time

print("Testing camera index 0 with V4L2...")
cap = cv2.VideoCapture(0, cv2.CAP_V4L2)
if cap.isOpened():
    print("✅ Successfully opened camera with V4L2!")
    ret, frame = cap.read()
    print(f"✅ Read frame: {ret}")
    cap.release()
else:
    print("❌ Failed to open camera with V4L2.")

print("\nTesting camera index 0 with Default backend...")
cap = cv2.VideoCapture(0)
if cap.isOpened():
    print("✅ Successfully opened camera with Default backend!")
    ret, frame = cap.read()
    print(f"✅ Read frame: {ret}")
    cap.release()
else:
    print("❌ Failed to open camera with Default backend.")
