import cv2
import numpy as np
import subprocess

w, h = 800, 640

ffmpeg = subprocess.Popen([
    "ffmpeg",
    "-y",
    "-f", "rawvideo",
    "-pix_fmt", "bgr24",
    "-s", f"{w}x{h}",
    "-r", "30",
    "-i", "-",
    "-c:v", "libx264",
    "-f", "rtsp",
    "rtsp://localhost:8554/video_rtsp_stream_0"
], stdin=subprocess.PIPE)

x = 0

while True:
    frame = np.zeros((h, w, 3), dtype=np.uint8)

    cv2.circle(frame, (x, 360), 40, (0, 255, 0), -1)

    cv2.putText(
        frame,
        "BlueROV2 Camera Simulator",
        (50, 100),
        cv2.FONT_HERSHEY_SIMPLEX,
        1,
        (255, 255, 255),
        2
    )

    ffmpeg.stdin.write(frame.tobytes())

    x = (x + 5) % w
