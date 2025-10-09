#!/usr/bin/env python3
import RPi.GPIO as GPIO
import subprocess
import os
import time
import signal

# ---------------- GPIO ----------------
PIR_PIN = 17
GPIO.setmode(GPIO.BCM)
GPIO.setup(PIR_PIN, GPIO.IN)

# ---------------- Videos & Image ----------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
IDLE_VIDEO = os.path.join(BASE_DIR, "idle.mp4")
TRIGGER_VIDEO = os.path.join(BASE_DIR, "trigger.mp4")
BLACK_IMAGE = os.path.join(BASE_DIR, "black.png")  # fullscreen black image

# ---------------- Audio ----------------
AUDIO_DEVICE = "alsa/plughw:CARD=vc4hdmi0"  # change if needed

# ---------------- MPV Options ----------------
MPV_BASE = [
    "mpv",
    "--no-terminal",
    "--no-config",
    "--fs",
    "--really-quiet",
    "--vo=gpu",
    f"--audio-device={AUDIO_DEVICE}",
]

def play_file(path, loop=False):
    """Play a file in background with optional loop"""
    args = MPV_BASE + [path]
    if loop:
        args.insert(-1, "--loop")  # loop before the file path
    env = os.environ.copy()
    env["DISPLAY"] = ":0"
    return subprocess.Popen(args, preexec_fn=os.setsid, env=env)

def play_trigger_blocking():
    """Play trigger video once (blocking)"""
    env = os.environ.copy()
    env["DISPLAY"] = ":0"
    subprocess.run(MPV_BASE + [TRIGGER_VIDEO], env=env)

# ---------------- MAIN LOOP ----------------
def main():
    print("Waiting 5 seconds for PIR to stabilize...")
    time.sleep(5)

    print("Showing black screen...")
    black_proc = play_file(BLACK_IMAGE, loop=True)

    print("Starting idle video loop...")
    idle_proc = play_file(IDLE_VIDEO, loop=True)

    try:
        while True:
            if GPIO.input(PIR_PIN):
                print("Motion detected! Playing trigger video...")

                # Stop idle video
                if idle_proc.poll() is None:
                    os.killpg(os.getpgid(idle_proc.pid), signal.SIGTERM)
                    time.sleep(0.1)  # brief pause

                # Trigger video
                play_trigger_blocking()

                # Resume idle video
                idle_proc = play_file(IDLE_VIDEO, loop=True)

                # Ignore PIR for 30 seconds to prevent retriggers
                print("Ignoring PIR for 30 seconds...")
                time.sleep(30)

            time.sleep(0.1)

    except KeyboardInterrupt:
        print("Exiting...")
    finally:
        if idle_proc.poll() is None:
            os.killpg(os.getpgid(idle_proc.pid), signal.SIGTERM)
        if black_proc.poll() is None:
            os.killpg(os.getpgid(black_proc.pid), signal.SIGTERM)
        GPIO.cleanup()
        print("Clean exit.")

if __name__ == "__main__":
    main()
