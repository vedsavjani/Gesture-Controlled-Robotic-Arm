"""
Quick experiment: how much faster do the two hand models run with more threads?
Runs each .tflite model with 1, 2 and 4 threads and prints the average time per run.
No camera needed - feeds random input of the right shape (timing doesn't depend on content).

Run (from repo root, with venv active):
    python experiments/bench_tflite.py
"""
import os
import sys
import time
from pathlib import Path

import numpy as np
from ai_edge_litert.interpreter import Interpreter

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
import config  # noqa: E402

MODELS = {
    "palm detector": os.path.join(config.MODEL_DIR, "hand_detector.tflite"),
    "landmark model": os.path.join(config.MODEL_DIR, "hand_landmarks_detector.tflite"),
}
WARMUP, RUNS = 5, 50


def main():
    for name, path in MODELS.items():
        print(f"\n{name} ({path})")
        base = None
        for threads in (1, 2, 4):
            interp = Interpreter(model_path=path, num_threads=threads)
            interp.allocate_tensors()
            inp = interp.get_input_details()[0]
            data = np.random.rand(*inp["shape"]).astype(inp["dtype"])

            for _ in range(WARMUP):          # first runs are slow (caches, memory setup)
                interp.set_tensor(inp["index"], data)
                interp.invoke()

            t = time.perf_counter()
            for _ in range(RUNS):
                interp.set_tensor(inp["index"], data)
                interp.invoke()
            ms = 1000 * (time.perf_counter() - t) / RUNS

            if threads == 1:
                print(f"  input shape {list(inp['shape'])}")
                base = ms
            print(f"  {threads} thread(s): {ms:6.1f} ms/run  ({base / ms:.2f}x vs 1 thread)")


if __name__ == "__main__":
    main()
