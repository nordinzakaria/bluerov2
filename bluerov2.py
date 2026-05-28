#!/usr/bin/env python3

import sys
import cv2
import csv
import time
from math import radians
from threading import Event, Thread
from pymavlink import mavutil
import pygame
from datetime import datetime

# Config (safe defaults)
CONN_STR = sys.argv[1] if len(sys.argv) > 1 else "udpin:0.0.0.0:14550"
RATE_HZ = 30  #  controls responsiveness vs. CPU/network/load
MAX_V = 0.3           # m/s (reduced)
MAX_Z_V = 0.2         # m/s (down positive in NED)
MAX_YAW_RATE_DEG = 15 # deg/s (reduced)
HEARTBEAT_TIMEOUT = 10.0  # seconds before considering connection lost
ARM_TIMEOUT = 10.0       # seconds to wait for arming

# NOTE: Video capture is independent of MAVLink messaging.
VIDEO_SRC     = 'rtsp://192.168.2.2:8554/video_rtsp_stream_0' 


# Helpers

def saveSession():
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"output_{timestamp}.csv"
    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        # optional header:
        writer.writerow(["v0", "v1", "v2", "yaw_rate_deg", "frame"])
        # write rows
        writer.writerows(data)

def connect(connection):
    print("Connecting to", connection)
    if connection.startswith("tcp:") or connection.startswith("udp:") or connection.startswith("udpin:"):
        master = mavutil.mavlink_connection(connection)
    else:
        return None
    return master

def wait_for_heartbeat(master, timeout=5, retries=3):
    for i in range(retries):
        hb = master.wait_heartbeat(timeout=timeout)
        if hb is not None:
            if master.target_system > 0 and master.target_component > 0:
                print("Heartbeat from sys=%u comp=%u" % (master.target_system, master.target_component))
                return hb
            else:
                for j in range(retries):
                    print("Heartbeat received but target IDs not set yet")
                    master.target_system = hb.get_srcSystem() 
                    master.target_component = hb.get_srcComponent()
                    if master.target_system > 0 and master.target_component > 0:
                        print("Yeay..Received heartbeat from sys=%u comp=%u" % (master.target_system, master.target_component))
                        return hb
                    time.sleep(0.5)
                return None
        print(f"Heartbeat wait attempt {i+1}/{retries} timed out")
        time.sleep(0.5)
    return None

def set_mode_and_arm(master, mode="GUIDED"):
    # set mode (helper) then arm
    try:
        mavutil.set_mode(master, mode)
    except Exception:
        # fallback: try MAV_CMD_DO_SET_MODE
        base_mode = mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED
        master.mav.command_long_send(
            master.target_system,
            master.target_component,
            mavutil.mavlink.MAV_CMD_DO_SET_MODE,
            0,
            base_mode, 0, 0, 0, 0, 0, 0
        )
    # arm
    print("Arming...")
    master.arducopter_arm()
    # wait for armed state
    start = time.time()
    while time.time() - start < ARM_TIMEOUT:
        msg = master.recv_match(type='HEARTBEAT', blocking=True, timeout=1)
        if msg is not None and (msg.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED):
            print("Armed")
            return True
    print("Failed to arm within timeout")
    return False

# Main

# initiate video connection
cap = cv2.VideoCapture(VIDEO_SRC)
if not cap.isOpened():
    print("Video open failed")

# initiate mavlink connection
master = connect(CONN_STR)
hb = wait_for_heartbeat(master, timeout=3, retries=5)
if hb is None:
    print("No heartbeat - exiting")
    sys.exit(1)

# Start watchdog thread to track last heartbeat time
last_hb_time = time.time()
stop_event = Event()

def hb_watcher():
    nonlocal_last = {"t": last_hb_time}
    while not stop_event.is_set():
        msg = master.recv_match(type='HEARTBEAT', blocking=True, timeout=1)
        if msg is not None:
            nonlocal_last["t"] = time.time()
        # update global last_hb_time
        # globals() is a built-in Python function that returns a dictionary
        globals()['last_hb_time'] = nonlocal_last["t"]

watch_thread = Thread(target=hb_watcher, daemon=True)
watch_thread.start()

# Attempt to set mode and arm
if not set_mode_and_arm(master, mode="GUIDED"):
    print("Could not set mode and arm - exiting")
    stop_event.set()
    sys.exit(1)

# pygame init
pygame.init()
screen = pygame.display.set_mode((320, 240))
pygame.display.set_caption("pymavlink teleop (safe)")
clock = pygame.time.Clock()

vx = vy = vz = yaw_rate_deg = 0.0

def stop_motion():
    # Send zero velocity setpoint (safe stop)
    send_velocity(0.0, 0.0, 0.0, 0.0)


def send_velocity(vx, vy, vz, yaw_rate_deg_s):

    # type_mask: ignore position (1+2+4)=7, ignore acceleration (8+16+32)=56, ignore yaw position (512)
    # => type_mask = 7 + 56 + 512 = 575  (enable velocity and yaw_rate)

    # alternative 0b0000010111000111: accept velocity fields and a yaw angle, 
    # while ignoring position, acceleration, and yaw-rate fields.


    # time_boot_ms is the MAVLink field that should contain the time (in milliseconds) since 
    # the autopilot/system boot (uint32). 
    # Purpose: give receivers a common time base for the message (ordering, latency measures, replay protection).

    time_boot_ms = int(time.time() * 1000) & 0xFFFFFFFF
    yaw_rate_rad_s = radians(yaw_rate_deg_s)
    type_mask = 0b1111000111  #967  # use vx,vy,vz and yaw_rate

    '''
    type_mask = 0b0000010111000111 #575
    time_boot_ms = int(time.time() * 1000) & 0xFFFFFFFF
    yaw_rate_rad_s = radians(yaw_rate_deg_s)
    '''
    try:
        master.mav.set_position_target_local_ned_send(
            time_boot_ms,
            master.target_system,
            master.target_component,
            mavutil.mavlink.MAV_FRAME_LOCAL_NED,
            type_mask,
            0, 0, 0,
            float(vx), float(vy), float(vz),
            0, 0, 0,
            0.0, float(yaw_rate_rad_s)
        )
    except Exception as e:
        print("Failed to send setpoint:", e)


print("Controls: arrows/WASD = move, Q/E = up/down, Z/X = yaw left/right, Space = stop, Esc = quit")

data=[]

running = True
try:
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key == pygame.K_SPACE:
                    vx = vy = vz = yaw_rate_deg = 0.0
                    send_velocity(0,0,0,0)

        if cv2.waitKey(1) & 0xFF == ord('q'):
            running = False


        keys = pygame.key.get_pressed()
        # Forward/back (vx forward positive)
        if keys[pygame.K_UP] or keys[pygame.K_w]:
            vx = MAX_V
        elif keys[pygame.K_DOWN] or keys[pygame.K_s]:
            vx = -MAX_V
        else:
            vx = 0.0
        # Left/right (vy right positive)
        if keys[pygame.K_RIGHT] or keys[pygame.K_d]:
            vy = MAX_V
        elif keys[pygame.K_LEFT] or keys[pygame.K_a]:
            vy = -MAX_V
        else:
            vy = 0.0
        # Up/down (NED: down positive)
        if keys[pygame.K_q]:
            vz = -MAX_Z_V
        elif keys[pygame.K_e]:
            vz = MAX_Z_V
        else:
            vz = 0.0
        # Yaw
        if keys[pygame.K_z]:
            yaw_rate_deg = -MAX_YAW_RATE_DEG
        elif keys[pygame.K_x]:
            yaw_rate_deg = MAX_YAW_RATE_DEG
        else:
            yaw_rate_deg = 0.0

        # Heartbeat watchdog: stop if no heartbeat recently
        # get('last_hb_time', time.time()) looks up the name 'last_hb_time' in the module globals 
        # returns its value if present; 
        # otherwise it returns the second argument (time.time()).
        if time.time() - globals().get('last_hb_time', time.time()) > HEARTBEAT_TIMEOUT:
            print("Heartbeat lost - sending stop and waiting for reconnection")
            stop_motion()
            # wait and try to re-establish heartbeat
            hb = wait_for_heartbeat(master, timeout=2, retries=5)
            if hb is None:
                print("Still no heartbeat - exiting")
                running = False
                break
            else:
                print("Heartbeat restored")


        # capture video frame
        # tells the VideoCapture to advance to the next frame and buffer it
        # but it does not return or decode the image for you
        ret = cap.grab()  
        if ret:
            ok, frame = cap.retrieve() # retrieve actual frame
            if ok and frame is not None:
                cv2.imshow("Video", frame)
                fname = "frame-"+str(len(data))+".jpg"
                cv2.imwrite(fname, frame) 
                data.append((vx, vy, vz, yaw_rate_deg, fname))

        print('Sending <', vx, ',', vy, ',', vz, '>')
        send_velocity(vx, vy, vz, yaw_rate_deg)

        clock.tick(RATE_HZ)
finally:
    print("Stopping vehicle and cleaning up")
    cap.release()
    cv2.destroyAllWindows()

    saveSession()
    stop_motion()
    # disarm if desired (comment out if you prefer manual disarm)
    try:
        master.arducopter_disarm()
    except Exception:
        pass
    stop_event.set()
    pygame.quit()
    print("Exited")

