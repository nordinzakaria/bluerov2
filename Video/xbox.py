
import time
import keyboard
import vgamepad as vg

import sys
import cv2
import csv
import datetime

#VIDEO_SRC     = 'rtsp://192.168.2.2:8554/video_rtsp_stream_0'
VIDEO_SRC     ="rtsp://localhost:8554/video_rtsp_stream_0"

# tested on https://hardwaretester.com/gamepad
gamepad = vg.VX360Gamepad()

# Maximum stick value
MAX_AXIS = 1.0

# Rate of change per second
RAMP_RATE = 2.5

# Current stick positions
lx = 0.0
ly = 0.0
rx = 0.0
ry = 0.0

def saveSession():
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"output_{timestamp}.csv"
    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        # optional header:
        writer.writerow(["lx", "ly", "rx", "ry", "frame"])
        # write rows
        writer.writerows(data)

def target_axis(negative_key, positive_key):
    if keyboard.is_pressed(negative_key):
        return -MAX_AXIS
    elif keyboard.is_pressed(positive_key):
        return MAX_AXIS
    return 0.0

def ramp(current, target, rate, dt):
    step = rate * dt

    if current < target:
        return min(current + step, target)

    if current > target:
        return max(current - step, target)

    return current

cap = cv2.VideoCapture(VIDEO_SRC)
if not cap.isOpened():
    print("Video open failed")
    sys.exit(1)
print("Video opened")

data=[]
last_time = time.time()

while True:

    now = time.time()
    dt = now - last_time
    last_time = now

    # Emergency stop
    if keyboard.is_pressed('esc'):
        lx = ly = rx = ry = 0.0

    # Targets

    target_lx = target_axis('a', 'd')      # sway
    target_ly = target_axis('s', 'w')      # surge

    target_rx = target_axis('left', 'right')  # yaw
    target_ry = target_axis('down', 'up')     # heave

    # Smooth ramp

    lx = ramp(lx, target_lx, RAMP_RATE, dt)
    ly = ramp(ly, target_ly, RAMP_RATE, dt)

    rx = ramp(rx, target_rx, RAMP_RATE, dt)
    ry = ramp(ry, target_ry, RAMP_RATE, dt)

    # Send to virtual controller
    ret = cap.grab()
    if ret:
        ok, frame = cap.retrieve()  # retrieve actual frame
        if ok and frame is not None:
            cv2.imshow("Video", frame)
            fname = "frame-" + str(len(data)) + ".jpg"
            cv2.imwrite(fname, frame)
            data.append((lx, ly, rx, ry, fname))

            if cv2.waitKey(1) & 0xFF == 27:
                break
        else:
            print('failed')


    gamepad.left_joystick_float(
        x_value_float=lx,
        y_value_float=ly
    )

    gamepad.right_joystick_float(
        x_value_float=rx,
        y_value_float=ry
    )

    if keyboard.is_pressed('esc'):
        break

    # Buttons
    if keyboard.is_pressed('shift+1'):
        gamepad.press_button(vg.XUSB_BUTTON.XUSB_GAMEPAD_Y)
        print('stabilize mode')
    else:
        gamepad.release_button(vg.XUSB_BUTTON.XUSB_GAMEPAD_Y)

    if keyboard.is_pressed('shift+2'):
        gamepad.press_button(vg.XUSB_BUTTON.XUSB_GAMEPAD_X)
        print('depth hold mode')
    else:
        gamepad.release_button(vg.XUSB_BUTTON.XUSB_GAMEPAD_X)


    if keyboard.is_pressed('shift+9'):
        gamepad.press_button(vg.XUSB_BUTTON.XUSB_GAMEPAD_START)
        print('arm')
    else:
        gamepad.release_button(vg.XUSB_BUTTON.XUSB_GAMEPAD_START)

    if keyboard.is_pressed('shift+0'):
        gamepad.press_button(vg.XUSB_BUTTON.XUSB_GAMEPAD_BACK)
        print('disarm')
    else:
        gamepad.release_button(vg.XUSB_BUTTON.XUSB_GAMEPAD_BACK)


    if keyboard.is_pressed('shift+3'):
        gamepad.press_button(vg.XUSB_BUTTON.XUSB_GAMEPAD_LEFT_SHOULDER)
        print('cam down')
    else:
        gamepad.release_button(vg.XUSB_BUTTON.XUSB_GAMEPAD_LEFT_SHOULDER)

    if keyboard.is_pressed('shift+4'):
        gamepad.press_button(vg.XUSB_BUTTON.XUSB_GAMEPAD_RIGHT_SHOULDER)
        print('cam up')
    else:
        gamepad.release_button(vg.XUSB_BUTTON.XUSB_GAMEPAD_RIGHT_SHOULDER)


    gamepad.update()

    time.sleep(0.02)

saveSession()
