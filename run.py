"""
Launcher script for Gesture Mouse.
Allows running the project with: python run.py
"""

import os
import sys
from pathlib import Path

# Silence internal MediaPipe / TFLite C++ messages on startup
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"
os.environ["GLOG_minloglevel"] = "3"
os.environ["ABSL_LOG_MIN_LEVEL"] = "3"

# Ensure src is on Python path
src_dir = Path(__file__).resolve().parent / "src"
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

from gesture_mouse.presentation.main import main

if __name__ == "__main__":
    main()
