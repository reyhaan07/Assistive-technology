"""Configuration.

Only values that are actually used. Ocular thresholds below are safe defaults;
per-user calibration (Stage 2) overrides them and is stored separately.
"""

CAMERA_INDEX = 0
SPEECH_COOLDOWN_SECONDS = 1.0

HOST = "0.0.0.0"
PORT = 5000

# --- Ocular input (defaults; calibration overrides per user) ---
EAR_OPEN_THRESHOLD = 0.25         # EAR >= this -> eyes open
EAR_CLOSE_THRESHOLD = 0.18        # EAR <= this -> eyes closed (hysteresis band between)
BLINK_MIN_CLOSE_SECONDS = 0.05    # closure shorter than this is noise, ignored
BLINK_MAX_CLOSE_SECONDS = 2.0     # closure longer than this is not a command blink
INTENTIONAL_BLINK_SECONDS = 0.4   # closure >= this counts as an intentional blink
BLINK_COOLDOWN_SECONDS = 0.6      # refractory period after a blink
RELIABILITY_WINDOW = 15           # frames used for the reliability ratio
OCULAR_FPS = 15                   # processing frames per second
