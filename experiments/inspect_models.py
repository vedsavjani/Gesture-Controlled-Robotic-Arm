"""
Stage 1: print the inputs and outputs of both hand models.
Read-only - changes nothing. Its output decides how stages 2 and 3 are written.

Run (from ~/gesture-arm, with venv-tflite active):
    python inspect_models.py
"""
from ai_edge_litert.interpreter import Interpreter

for path in ("models/hand_detector.tflite", "models/hand_landmarks_detector.tflite"):
    interp = Interpreter(model_path=path)
    interp.allocate_tensors()
    print(f"\n=== {path} ===")
    for kind, details in (("INPUT", interp.get_input_details()),
                          ("OUTPUT", interp.get_output_details())):
        for i, d in enumerate(details):
            print(f"{kind} {i}: name={d['name']}  shape={list(d['shape'])}  dtype={d['dtype'].__name__}")