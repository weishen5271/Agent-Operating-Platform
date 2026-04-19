import sys
from pathlib import Path


API_SRC_PATH = Path(__file__).resolve().parents[1] / "src"
if str(API_SRC_PATH) not in sys.path:
    sys.path.insert(0, str(API_SRC_PATH))
