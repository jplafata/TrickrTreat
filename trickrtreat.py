# Python Script for MPV Video Trigger on Raspberry Pi (Bookworm Desktop)
#
# This version uses a single persistent MPV process and IPC (Inter-Process Communication)
# to switch videos, which prevents desktop flickering and window layering issues.
#
# CRITICAL NOTE: You MUST set the TRIGGER_DURATION_SECONDS below to match the exact
# duration of your 'trigger.mp4' video for the seamless switch back to work.
#
# FIX: Updated to use '--vo=x11' as the video output driver, which is more reliable
# in certain Raspberry Pi desktop environments than '--vo=gpu'.
#
# PREREQUISITES:
# 1. Install RPi.GPIO: sudo pip3 install RPi.GPIO
# 2. Install mpv: sudo apt install mpv
# 3. Ensure 'idle.mp4' and 'trigger.mp4' are in the same directory as this script.

import RPi.GPIO as GPIO
import subprocess
import time
import os
import signal
import json
import fcntl

# --- Configuration ---
PIR_PIN = 17                    # GPIO pin connected to the PIR sensor output
IDLE_VIDEO = "idle.mp4"
TRIGGER_VIDEO = "trigger.mp4"
MPV_SOCKET_PATH = "/tmp/mpv-trigger-socket" # The path for the IPC socket

# IMPORTANT: SET THIS DURATION to match the length of your trigger.mp4 file!
TRIGGER_DURATION_SECONDS = 26.0

# Base mpv command configuration.
# ADDED: "--input-ipc-server" to enable control via the socket.
# UPDATED: Using "--vo=x11" as requested.
MPV_COMMAND = [
    "mpv",
    "--fs",
    "--no-audio-display",
    "--quiet",
    "--vo=x11", # Using X11 video output driver
    f"--input-ipc-server={MPV_SOCKET_PATH}"
]

# Get the directory of the script to find the video files
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
IDLE_PATH = os.path.join(SCRIPT_DIR, IDLE_VIDEO)
TRIGGER_PATH = os.path.join(SCRIPT_DIR, TRIGGER_VIDEO)

# Global variable to hold the single, persistent mpv process
mpv_process = None

def setup_gpio():
    """Sets up the GPIO pin for the PIR sensor."""
    print("Setting up GPIO...")
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(PIR_PIN, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
    print(f"PIR sensor is ready on GPIO {PIR_PIN}.")

def send_mpv_command(command_list):
    """Sends a JSON command to the mpv IPC socket."""
    # Build the JSON command string
    command = {"command": command_list}
    command_str = json.dumps(command) + "\n" # mpv IPC requires a newline

    # Use a non-blocking write to the socket file
    try:
        # Open the socket file
        fd = os.open(MPV_SOCKET_PATH, os.O_WRONLY | os.O_NONBLOCK)
        try:
            # Set a non-blocking flag (necessary for Python's write on pipes/sockets)
            flags = fcntl.fcntl(fd, fcntl.F_GETFL)
            fcntl.fcntl(fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)
            
            # Write the command to the socket
            os.write(fd, command_str.encode('utf-8'))
        finally:
            os.close(fd)
        
        # print(f"IPC Command sent: {command_str.strip()}")
        return True
    except FileNotFoundError:
        print("ERROR: MPV socket not found. Is mpv running?")
        return False
    except BlockingIOError:
        print("WARN: MPV socket busy. Command skipped.")
        return False
    except Exception as e:
        print(f"ERROR sending IPC command: {e}")
        return False

def start_mpv_process():
    """Starts the single persistent mpv process and loads the idle video loop."""
    global mpv_process
    if mpv_process and mpv_process.poll() is None:
        # mpv is already running
        return

    # 1. Clean up old socket if it exists
    if os.path.exists(MPV_SOCKET_PATH):
        os.remove(MPV_SOCKET_PATH)
        os.environ["DISPLAY"] = ":0"
        os.environ["XDG_RUNTIME_DIR"] = "/run/user/1000"

    # 2. Build the initial command: loop idle.mp4
    initial_command = MPV_COMMAND + [IDLE_PATH, "--loop=inf"]
    
    print(f"Starting persistent MPV process: {IDLE_VIDEO}")
    try:
        # Use Popen to run mpv in the background
        mpv_process = subprocess.Popen(initial_command, preexec_fn=os.setsid, 
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except FileNotFoundError:
        print(f"FATAL ERROR: mpv not found. Ensure it is installed.")
        cleanup_and_exit()
    except Exception as e:
        print(f"FATAL ERROR starting MPV process: {e}")
        cleanup_and_exit()

    # Give mpv a moment to start and create the socket file
    time.sleep(2)
    print("MPV is running and idle video is looping.")


def switch_to_idle():
    """Sends commands to load idle.mp4 and re-enable looping."""
    print(f"Switching back to IDLE video: {IDLE_VIDEO}")
    
    # 1. Load the idle video, replacing whatever is currently playing (the trigger video's last frame)
    # The 'noidx' argument tells it not to change the playlist, just replace the current file.
    send_mpv_command(["loadfile", IDLE_PATH, "replace", "noidx"])
    
    # 2. Re-enable infinite looping for the idle video
    send_mpv_command(["set_property", "loop-file", "inf"])


def switch_to_trigger():
    """Sends commands to stop the idle loop and play trigger.mp4 once."""
    print(f"MOTION DETECTED! Switching to TRIGGER video: {TRIGGER_VIDEO}")
    
    # 1. Temporarily disable looping on the current file (idle.mp4)
    send_mpv_command(["set_property", "loop-file", "no"])
    
    # 2. Load the trigger video, replacing the current file (idle.mp4)
    send_mpv_command(["loadfile", TRIGGER_PATH, "replace", "noidx"])

    # NOTE: Since the trigger video is not explicitly set to loop, it will play once
    # and then freeze on the last frame. We rely on the time.sleep below to know when
    # to load the idle video back.


def motion_detected_callback(channel):
    """Callback function executed when motion is detected."""
    # Ensure this only runs if the mpv process is still active
    if mpv_process and mpv_process.poll() is None:
        
        # 1. Switch to the trigger video instantly
        switch_to_trigger()

        # 2. Wait for the trigger video to finish playing
        print(f"Waiting {TRIGGER_DURATION_SECONDS} seconds for trigger video to complete...")
        time.sleep(TRIGGER_DURATION_SECONDS)

        # 3. Switch back to the idle video loop
        switch_to_idle()


def cleanup_and_exit(signum=None, frame=None):
    """Cleans up GPIO and stops the mpv process before exiting."""
    print("\nCleaning up and exiting...")
    
    # 1. Terminate the persistent mpv process
    global mpv_process
    if mpv_process and mpv_process.poll() is None:
        print(f"Stopping MPV process (PID: {mpv_process.pid}).")
        try:
            # Send SIGTERM to the process group to ensure mpv window closes
            os.killpg(os.getpgid(mpv_process.pid), signal.SIGTERM)
            mpv_process.wait(timeout=5)
        except Exception:
            pass
    
    # 2. Clean up GPIO
    GPIO.cleanup()
    
    # 3. Clean up the socket file
    if os.path.exists(MPV_SOCKET_PATH):
        os.remove(MPV_SOCKET_PATH)
        
    print("Cleanup complete. Goodbye.")
    if signum is not None:
        exit(0)

def main():
    """Main application loop."""
    signal.signal(signal.SIGINT, cleanup_and_exit)
    signal.signal(signal.SIGTERM, cleanup_and_exit)

    # 1. Setup GPIO
    setup_gpio()
    print("Warming up PIR sensor (5s)...")
    time.sleep(5)

    # 2. Start the single persistent mpv process
    start_mpv_process()
    
    # 3. Start the event listener
    GPIO.add_event_detect(PIR_PIN, GPIO.RISING, callback=motion_detected_callback, bouncetime=5000)

    # 4. Keep the main script running indefinitely
    print("Script running. Waiting for motion...")
    try:
        while True:
            # Check if MPV process died unexpectedly
            if mpv_process.poll() is not None:
                print("MPV process stopped unexpectedly. Restarting...")
                start_mpv_process()
            time.sleep(1)

    except Exception as e:
        print(f"Main loop error: {e}")
    finally:
        cleanup_and_exit()

if __name__ == "__main__":
    main()
    