import cv2

with open('cam_logs.txt', 'w') as f:
    f.write('Starting camera test\n')
    for i in range(6):
        f.write(f'Testing index {i}\n')
        # V4L2
        try:
            cap = cv2.VideoCapture(i, cv2.CAP_V4L2)
            if cap.isOpened():
                ret, _ = cap.read()
                f.write(f'  V4L2 {i}: Opened={cap.isOpened()} Read={ret}\n')
            cap.release()
        except Exception as e:
            f.write(f'  V4L2 {i} error: {e}\n')
        
        # Default
        try:
            cap = cv2.VideoCapture(i)
            if cap.isOpened():
                ret, _ = cap.read()
                f.write(f'  Default {i}: Opened={cap.isOpened()} Read={ret}\n')
            cap.release()
        except Exception as e:
            f.write(f'  Default {i} error: {e}\n')
