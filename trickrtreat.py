import RPi.GPIO as GPIO
import vlc
import time
import os

# --- Configuration ---
PIR_PIN = 17

# --- Video Time Configuration (in seconds) ---
#--- IMPORTANT ---
# Define the time segments for your single video file.
IDLE_START_S = 0      # Start of the idle loop (e.g., 0 seconds)
IDLE_END_S = 50       # End of the idle loop (e.g., 10 seconds)
TRIGGER_START_S = 51  # Start of the motion-triggered section (e.g., 10 seconds)
TRIGGER_END_S = 76    # End of the motion-triggered section (e.g., 25 seconds)


# --- File Path ---
# --- IMPORTANT ---
# Create one video file named 'combined_video.mp4' and place it
# in the SAME directory as this Python script.
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
VIDEO_PATH = os.path.join(SCRIPT_DIR, "combined_video.mp4")

# --- Global variable to signal motion detection ---
motion_detected_flag = False

def motion_callback(channel):
    """
    Callback function executed on a PIR sensor interrupt.
    Sets a global flag to indicate motion was detected.
    """
    global motion_detected_flag
    # No need to print here, as it can slow down the interrupt handler.
    # The main loop will provide feedback.
    motion_detected_flag = True

def main():
    """
    Main function to handle video playback based on PIR sensor input.
    """
    global motion_detected_flag

    # --- Convert times from seconds to milliseconds for VLC ---
    IDLE_START_MS = IDLE_START_S * 1000
    IDLE_END_MS = IDLE_END_S * 1000
    TRIGGER_START_MS = TRIGGER_START_S * 1000
    TRIGGER_END_MS = TRIGGER_END_S * 1000

    # --- GPIO Setup ---
    GPIO.setwarnings(False)
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(PIR_PIN, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)

    # Setup interrupt for motion detection. This is non-blocking.
    # bouncetime avoids multiple rapid triggers from the same motion event.
    GPIO.add_event_detect(PIR_PIN, GPIO.RISING, callback=motion_callback, bouncetime=500)

    print("Sensor and video player initializing...")

    # --- VLC Instance Setup with Optimizations for Raspberry Pi ---
    vlc_instance = vlc.Instance(
        '--codec=h264_mmal',
        '--fullscreen',
        '--no-osd',
        '--no-video-title-show'
    )

    # Create a single media player
    player = vlc_instance.media_player_new()
    media = vlc_instance.media_new(VIDEO_PATH)
    player.set_media(media)

    # Start playing the video
    player.play()
    # Set the initial position to the start of the idle loop
    player.set_time(IDLE_START_MS)

    current_state = 'IDLE'
    print(f"Setup complete. Starting IDLE loop ({IDLE_START_S}s to {IDLE_END_S}s).")

    try:
        while True:
            # Get current video time in milliseconds
            current_time = player.get_time()

            # --- State Machine Logic ---

            # Check if motion has been detected AND we are currently in the idle state.
            # This prevents the trigger section from restarting if motion continues.
            if motion_detected_flag and current_state == 'IDLE':
                current_state = 'TRIGGER'
                player.set_time(TRIGGER_START_MS)
                print(f"Motion Detected! Playing TRIGGER section ({TRIGGER_START_S}s to {TRIGGER_END_S}s).")
                motion_detected_flag = False  # Reset the flag so we don't re-trigger immediately

            # If motion is detected while the trigger video is already playing, just ignore it.
            elif motion_detected_flag:
                motion_detected_flag = False # Reset flag and do nothing.

            # Handle the IDLE state (looping)
            if current_state == 'IDLE':
                # If playback is past the idle section's end, or somehow before its start,
                # loop it back to the beginning of the idle section.
                if current_time >= IDLE_END_MS or current_time < IDLE_START_MS:
                    player.set_time(IDLE_START_MS)

            # Handle the TRIGGER state (play once)
            elif current_state == 'TRIGGER':
                # If the trigger section has finished, return to idle
                if current_time >= TRIGGER_END_MS:
                    print(f"Trigger finished. Returning to IDLE loop.")
                    current_state = 'IDLE'
                    player.set_time(IDLE_START_MS)

            # Small delay to prevent this loop from using 100% CPU
            time.sleep(0.02)

    except KeyboardInterrupt:
        print("\nExiting program.")
    finally:
        if player.is_playing():
            player.stop()
        GPIO.cleanup()


if __name__ == '__main__':
    if not os.path.exists(VIDEO_PATH):
        print(f"Error: Make sure 'combined_video.mp4' exists in the directory:")
        print(f"{SCRIPT_DIR}")
    else:
        main()

