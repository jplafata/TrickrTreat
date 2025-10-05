import vlc
import time
from gpiozero import MotionSensor

# === CONFIG ===
PIR_PIN = 17
IDLE_VIDEO = "/home/pi/videos/idle.mp4"
TRIGGER_VIDEO = "/home/pi/videos/trigger.mp4"

# === Setup ===
pir = MotionSensor(PIR_PIN)

# Create VLC instance
instance = vlc.Instance("--loop")   # loop for idle playback
player = instance.media_player_new()

def play_video(path, loop=False):
    """Play a video, optionally loop."""
    media = instance.media_new(path)
    player.set_media(media)
    if loop:
        player.set_playback_mode(vlc.PlaybackMode.loop)
    else:
        player.set_playback_mode(vlc.PlaybackMode.default)
    player.play()

# Start idle loop
play_video(IDLE_VIDEO, loop=True)

try:
    while True:
        pir.wait_for_motion()
        print("Motion detected!")

        # Stop idle
        player.stop()

        # Play trigger video once
        play_video(TRIGGER_VIDEO, loop=False)

        # Wait until trigger finishes
        while player.is_playing():
            time.sleep(0.1)

        # Resume idle loop
        play_video(IDLE_VIDEO, loop=True)
        pir.wait_for_no_motion()

except KeyboardInterrupt:
    print("Exiting...")
    player.stop()