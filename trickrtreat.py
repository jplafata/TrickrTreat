import subprocess
import time
from gpiozero import MotionSensor

# === CONFIG ===
PIR_PIN = 17
IDLE_VIDEO = "idle-loop.mp4"            # Pi-friendly idle video
TRIGGER_VIDEO = "/home/pi/videos/trigger_pi.mp4"  # Pi-friendly trigger video

# === Setup ===
pir = MotionSensor(PIR_PIN)

# Helper function to start a video with mpv
def play_video(path, loop=False):
    """Play a video fullscreen on Pi Desktop using mpv."""
    args = [
        "mpv",
        path,
        "--no-terminal",                  # suppress console output
        "--vo=x11",                       # X11 video output for Desktop
        "--fullscreen",                   # force fullscreen
        "--autofit=100%x100%",            # scale video to fill display
        "--hwdec=mmal",                   # Pi GPU hardware decoding
        "--no-input-default-bindings",    # do not capture keyboard/mouse
        "--loop" if loop else "--loop=no"
    ]
    return subprocess.Popen(
        args,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )

# Start idle video loop
idle_process = play_video(IDLE_VIDEO, loop=True)

try:
    while True:
        pir.wait_for_motion()
        print("Motion detected!")

        # Stop idle video
        idle_process.terminate()
        idle_process.wait()

        # Play trigger video once
        trigger_process = play_video(TRIGGER_VIDEO, loop=False)
        trigger_process.wait()  # wait until trigger finishes

        # Resume idle video loop
        idle_process = play_video(IDLE_VIDEO, loop=True)

        pir.wait_for_no_motion()

except KeyboardInterrupt:
    print("Exiting...")
    idle_process.terminate()
    idle_process.wait()
