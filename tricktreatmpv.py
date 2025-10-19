import RPi.GPIO as GPIO
import time
import os
import subprocess
import socket
import json

# --- Configuration ---
PIR_PIN = 17

# --- Video Time Configuration (in seconds) ---
IDLE_START_S = 0
IDLE_END_S = 50
TRIGGER_START_S = 53
TRIGGER_END_S = 76

# --- File Paths ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
VIDEO_PATH = os.path.join(SCRIPT_DIR, "trickrtreatdoor.mp4")
# A temporary file used for communication between this script and MPV
SOCKET_PATH = "/tmp/mpv.sock"

# --- Global variable to signal motion detection ---
motion_detected_flag = False

def motion_callback(channel):
    """Callback function executed on PIR sensor interrupt."""
    global motion_detected_flag
    motion_detected_flag = True

def send_mpv_command(command):
    """Sends a command to the MPV socket."""
    try:
        # Create a Unix domain socket
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client_socket:
            client_socket.connect(SOCKET_PATH)
            # MPV commands are newline-terminated JSON strings
            client_socket.sendall(json.dumps(command).encode('utf-8') + b'\n')
            # Read the response
            response = client_socket.recv(4096)
            return json.loads(response)
    except (ConnectionRefusedError, FileNotFoundError):
        # This can happen briefly at startup before MPV is ready
        return None
    except Exception as e:
        print(f"Error communicating with MPV: {e}")
        return None

def main():
    """Main function to launch MPV and handle video playback."""
    global motion_detected_flag

    # --- GPIO Setup ---
    GPIO.setwarnings(False)
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(PIR_PIN, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
    GPIO.add_event_detect(PIR_PIN, GPIO.RISING, callback=motion_callback, bouncetime=500)

    # --- Clean up old socket if it exists ---
    if os.path.exists(SOCKET_PATH):
        os.remove(SOCKET_PATH)

    print("Launching MPV media player...")

    # --- Command to launch MPV ---
    mpv_command = [
        'mpv',
        VIDEO_PATH,
        '--fs',  # Fullscreen
        '--keep-open=yes', # Keep open after video finishes
        '--no-osc', # Disable the on-screen controller
        '--no-osd-bar', # Disable the on-screen display bar for seeking
        '--loop-file=inf', # Loop the whole file if it ever reaches the end
        f'--input-ipc-server={SOCKET_PATH}' # IPC socket for control
    ]

    # Launch MPV as a separate, non-blocking process
    mpv_process = subprocess.Popen(mpv_command)

    # Wait a moment for MPV to start and create the socket
    time.sleep(2)
    print("MPV started. Initializing control loop.")

    current_state = 'IDLE'
    send_mpv_command({"command": ["seek", IDLE_START_S, "absolute"]})
    print(f"Starting IDLE loop ({IDLE_START_S}s to {IDLE_END_S}s).")

    try:
        while True:
            # --- Get current video time from MPV ---
            response = send_mpv_command({"command": ["get_property", "time-pos"]})
            current_time = response.get('data', 0) if response else 0

            # --- State Machine Logic ---
            if motion_detected_flag and current_state == 'IDLE':
                print(f"Motion Detected! Playing TRIGGER section ({TRIGGER_START_S}s to {TRIGGER_END_S}s).")
                current_state = 'TRIGGER'
                send_mpv_command({"command": ["seek", TRIGGER_START_S, "absolute"]})
                motion_detected_flag = False

            elif motion_detected_flag:
                motion_detected_flag = False # Ignore motion if not in IDLE state

            # --- Handle States ---
            if current_state == 'IDLE':
                if current_time >= IDLE_END_S or current_time < IDLE_START_S:
                    send_mpv_command({"command": ["seek", IDLE_START_S, "absolute"]})
            
            elif current_state == 'TRIGGER':
                if current_time >= TRIGGER_END_S:
                    print("Trigger finished. Returning to IDLE loop.")
                    current_state = 'IDLE'
                    send_mpv_command({"command": ["seek", IDLE_START_S, "absolute"]})

            time.sleep(0.02) # Prevent 100% CPU usage

    except KeyboardInterrupt:
        print("\nExiting program.")
    finally:
        # Cleanly shut down MPV and GPIO
        send_mpv_command({"command": ["quit"]})
        mpv_process.wait()
        GPIO.cleanup()
        if os.path.exists(SOCKET_PATH):
            os.remove(SOCKET_PATH)

if __name__ == '__main__':
    if not os.path.exists(VIDEO_PATH):
        print(f"Error: Make sure 'combined_video.mp4' exists in the directory:")
        print(f"{SCRIPT_DIR}")
    else:
        main()

