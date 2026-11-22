"""Photo check. Usage: python check_hand.py probes/open.jpg probes/tilt.jpg ...
Saves <photo>_out.jpg (21 points drawn) and <photo>_crop.jpg (what the model saw)."""
import sys
import time

import cv2

from hand import HandTracker

LINES = [(0, 1), (1, 2), (2, 3), (3, 4), (0, 5), (5, 6), (6, 7), (7, 8), (5, 9), (9, 10),
         (10, 11), (11, 12), (9, 13), (13, 14), (14, 15), (15, 16), (13, 17), (0, 17),
         (17, 18), (18, 19), (19, 20)]

tracker = HandTracker()
for path in sys.argv[1:]:
    img = cv2.imread(path)
    if img is None:
        print(path, ": cannot read")
        continue
    tracker.reset()
    first = None
    for call in (1, 2):                      # call 2 uses the crop made from call 1
        t = time.time()
        res = tracker.process(img)
        ms = (time.time() - t) * 1000
        if call == 1:
            first = res
        if res is None:
            print(f"{path} call {call}: no hand ({ms:.0f} ms)")
        else:
            p, presence = res
            print(f"{path} call {call}: HAND presence {presence:.2f} "
                  f"| wrist ({p[0,0]:.0f},{p[0,1]:.0f}) index tip ({p[8,0]:.0f},{p[8,1]:.0f}) ({ms:.0f} ms)")
    if first is not None:
        pts = first[0]
        out = img.copy()
        for a, b in LINES:
            cv2.line(out, (int(pts[a, 0]), int(pts[a, 1])), (int(pts[b, 0]), int(pts[b, 1])), (0, 255, 0), 2)
        for x, y, _ in pts:
            cv2.circle(out, (int(x), int(y)), 4, (0, 0, 255), -1)
        stem = path.rsplit(".", 1)[0]
        cv2.imwrite(stem + "_out.jpg", out)
        cv2.imwrite(stem + "_crop.jpg", cv2.cvtColor(tracker.last_crop, cv2.COLOR_RGB2BGR))