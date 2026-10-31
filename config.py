import os

# Override without editing: CAMERA_URL=http://<ip>:8080/video python main.py
CAMERA_URL = os.environ.get("CAMERA_URL", "http://10.190.11.91:8080/video")
MODEL_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models")
THREADS = 4
