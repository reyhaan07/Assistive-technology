"""Central configuration for GestureTalk."""
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.environ.get("GESTURETALK_DATA_DIR", BASE_DIR)

# Persistent files (both git-ignored)
GESTURES_FILE = os.path.join(DATA_DIR, "gestures.json")
PHRASES_FILE = os.path.join(DATA_DIR, "phrases.json")

# Contexts the user can switch between
CONTEXTS = ["cafe", "hospital", "college", "bank"]
DEFAULT_CONTEXT = "cafe"

# Recognition
RECOGNITION_THRESHOLD = 0.30      # max mean landmark distance for a trained match
STABLE_FRAMES = 4                 # frames a gesture must persist before it is reported
ENABLE_BUILTIN_GESTURES = True    # rule-based thumbs_up / stop / peace / ... without training
CAPTURE_SAMPLES = 5               # landmark samples recorded per training capture
CAPTURE_TIMEOUT_SECONDS = 3.0

# Speech
SPEECH_COOLDOWN_SECONDS = 2.0     # min gap between two utterances of the same phrase
REPEAT_SPEECH_SECONDS = 5.0       # re-speak a gesture that is held this long
HISTORY_SIZE = 15

# Camera
CAMERA_INDEX = int(os.environ.get("GESTURETALK_CAMERA", "0"))
FRAME_WIDTH = 480
FRAME_HEIGHT = 360
MAX_NUM_HANDS = 1
MIN_DETECTION_CONFIDENCE = 0.6
MIN_TRACKING_CONFIDENCE = 0.5

# Server
HOST = os.environ.get("GESTURETALK_HOST", "0.0.0.0")
PORT = int(os.environ.get("GESTURETALK_PORT", "5000"))
