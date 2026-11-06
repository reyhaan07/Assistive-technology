"""Synthetic hand poses (image coordinates, y grows downwards)."""
import numpy as np

FINGER_X = {"index": -0.06, "middle": -0.02, "ring": 0.02, "pinky": 0.06}
MCP = {"index": 5, "middle": 9, "ring": 13, "pinky": 17}


def make_hand(extended=(), thumb="folded"):
    pts = np.zeros((21, 3), dtype=np.float32)
    wrist = np.array([0.5, 0.9, 0.0])
    pts[0] = wrist
    for name, dx in FINGER_X.items():
        base = MCP[name]
        mcp = wrist + [dx, -0.2, 0]
        pts[base] = mcp
        if name in extended:
            for k in range(1, 4):
                pts[base + k] = mcp + [dx * 0.2 * k, -0.07 * k, 0]
        else:  # curled back towards the palm
            pts[base + 1] = mcp + [0, -0.05, 0]
            pts[base + 2] = mcp + [0, -0.02, 0.03]
            pts[base + 3] = mcp + [0, 0.03, 0.02]
    # thumb
    pts[1] = wrist + [-0.08, -0.05, 0]
    pts[2] = wrist + [-0.12, -0.10, 0]
    if thumb == "up":
        pts[3] = pts[2] + [0, -0.12, 0]
        pts[4] = pts[3] + [0, -0.10, 0]
    elif thumb == "down":
        pts[3] = pts[2] + [0, 0.12, 0]
        pts[4] = pts[3] + [0, 0.10, 0]
    elif thumb == "out":
        pts[3] = pts[2] + [-0.08, -0.04, 0]
        pts[4] = pts[3] + [-0.07, -0.03, 0]
    else:  # folded across palm
        pts[3] = pts[2] + [0.05, -0.04, 0]
        pts[4] = pts[3] + [0.05, 0.03, 0]
    return pts
