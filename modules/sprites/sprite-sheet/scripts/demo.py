"""Render a platformer-style demo video of a sprite sheet from `sprite-sheet render`.

    python3 demo.py SHEET.png OUT.mp4 --idle ACTION --run ACTION

Needs numpy, pillow and ffmpeg. Plays the idle, the run, a ninja jump with a double jump when the sheet has all
four NinjaJump_* rows, then every other row once as an attack, in sheet order. The sprite moves by each row's
root motion, so the feet stay planted. Drawn at sprite resolution on a 320x180 stage and scaled up 4x without
smoothing. The jump's height and gravity are made up; a game would set its own.
"""
import argparse
import json
import math
import os
import subprocess
import sys
from dataclasses import dataclass

import numpy as np
from PIL import Image, ImageDraw, ImageFont

W, H, ZOOM, GROUND = 320, 180, 4, 150  # stage size and ground row, in sprite pixels
JUMP = ["NinjaJump_Start", "NinjaJump_Idle_Loop", "NinjaJump_Double", "NinjaJump_Land"]
# Jump tuning for the Universal Animation Library's ninja jump (sprite pixels per frame): launch on the frame the
# feet leave the ground, kick again on the frame the legs are fully extended in the double jump, and start landing just before touchdown, since the landing
# sprite begins with the feet still tucked.
GRAVITY, JUMP_V, DOUBLE_V = 0.42, 5.8, 5.4
TAKEOFF_FRAME, DOUBLE_KICK_FRAME, DOUBLE_EARLIEST = 2, 4, 12


@dataclass(frozen=True)
class Frame:
    action: str
    j: int  # frame within the action
    x: float  # ground position of the anchor, sprite px
    y: float  # height above the ground
    label: str


class Sheet:
    def __init__(self, png: str):
        self.meta = json.load(open(os.path.splitext(png)[0] + ".json"))
        self.pixels = np.array(Image.open(png).convert("RGBA"))
        self.cell = self.meta["cell"]
        self.rows = {r["action"]: (i, r) for i, r in enumerate(self.meta["rows"])}

    def frames(self, action: str) -> int:
        return self.rows[action][1]["frames"]

    def wrap(self, action: str, j: int) -> int:
        n = self.frames(action)
        return j % n if self.rows[action][1]["loop"] else min(j, n - 1)

    def sprite(self, action: str, j: int) -> np.ndarray:
        i, c = self.rows[action][0], self.cell
        j = self.wrap(action, j)
        return self.pixels[i * c:(i + 1) * c, j * c:(j + 1) * c]

    def root(self, action: str, j: int) -> float:
        return self.rows[action][1]["root"][self.wrap(action, j)]

    def speed(self, action: str) -> float:
        """Ground speed of a loop, px per frame."""
        return self.rows[action][1]["root_cycle"] / self.frames(action)


def timeline(sheet: Sheet, *, idle: str, run: str) -> list[Frame]:
    out: list[Frame] = []
    x = 40.0

    def hold(action: str, count: int, label: str, vx: float = 0.0) -> None:
        nonlocal x
        for j in range(count):
            out.append(Frame(action, j, x, 0.0, label))
            x += vx

    run_v = sheet.speed(run)
    hold(idle, 30, "Idle")
    hold(run, 44, "Run", run_v)
    if all(a in sheet.rows for a in JUMP):
        x = jump(sheet, out, x, run_v * 0.8)
        hold(idle, 12, "Idle")

    for action in sheet.rows:
        if action in (idle, run) or action in JUMP:
            continue
        x0 = x
        label = action.rsplit("_", 1)[-1]  # Punch_Jab -> Jab
        for j in range(sheet.frames(action)):
            x = x0 + sheet.root(action, j)
            out.append(Frame(action, j, x, 0.0, label))
        hold(idle, 10, label)
    hold(idle, 24, "")
    return out


def jump(sheet: Sheet, out: list[Frame], x: float, vx: float) -> float:
    """Append a jump with a double jump near the apex, landing on the frame the feet touch down; return the end x."""
    y = 0.0
    anim, j, vy, label, doubled = "NinjaJump_Start", 0, 0.0, "Jump", False
    while True:
        if anim == "NinjaJump_Start" and j == TAKEOFF_FRAME:
            vy = JUMP_V
        if anim == "NinjaJump_Double" and j == DOUBLE_KICK_FRAME:
            vy = DOUBLE_V
        if anim == "NinjaJump_Start" and not doubled and j >= DOUBLE_EARLIEST and vy < 0.5:
            anim, j, label, doubled = "NinjaJump_Double", 0, "Double jump", True
        if anim in ("NinjaJump_Start", "NinjaJump_Double") and j >= sheet.frames(anim):
            anim, j = "NinjaJump_Idle_Loop", 0
        airborne = y > 0 or vy > 0
        if airborne and vy < 0 and anim != "NinjaJump_Land" and y + 2 * vy - 3 * GRAVITY <= 0:
            anim, j, label = "NinjaJump_Land", 0, "Land"
        if anim == "NinjaJump_Land" and not airborne:
            break
        out.append(Frame(anim, j, x, y, label))
        x += vx
        j += 1
        if airborne:
            y += vy
            vy -= GRAVITY
            if y <= 0:
                y, vy = 0.0, 0.0
    for k in range(sheet.frames("NinjaJump_Land") - j):  # skid to a stop
        out.append(Frame("NinjaJump_Land", j + k, x, 0.0, "Land"))
        x += vx * max(0.0, 1 - (k + 1) / 6)
    return x


def hill(u: float) -> float:
    """Rolling skyline height above the ground, px."""
    return 12 + 6 * math.sin(u / 23) + 4 * math.sin(u / 9.7 + 1) + 2 * math.sin(u / 4.3 + 2)


def render(sheet: Sheet, frames: list[Frame], out_mp4: str) -> None:
    ax, ay = sheet.meta["anchor"]
    c = sheet.cell
    font = ImageFont.load_default(size=36)
    small = ImageFont.load_default(size=18)
    text = dict(fill=(255, 255, 255), stroke_width=3, stroke_fill=(40, 44, 56))
    ffmpeg = subprocess.Popen(
        ["ffmpeg", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W * ZOOM}x{H * ZOOM}",
         "-r", str(sheet.meta["fps"]), "-i", "-", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", out_mp4],
        stdin=subprocess.PIPE)
    assert ffmpeg.stdin
    cam = frames[0].x - 110
    for f in frames:
        cam += ((f.x - 110) - cam) * 0.15  # ease the camera after the character
        img = np.empty((H, W, 3), np.uint8)
        img[:] = (168, 190, 214)
        for sx in range(W):
            img[GROUND - int(hill(sx + cam * 0.5)):GROUND, sx] = (130, 150, 170)  # half-speed parallax
        img[GROUND:] = (92, 104, 120)
        for sx in range(W):
            if int((sx + cam) // 16) % 2:
                img[GROUND:GROUND + 4, sx] = (110, 124, 140)
        spr = sheet.sprite(f.action, f.j)
        px, py = round(f.x - cam - ax), round(GROUND - f.y - ay)
        x0, y0, x1, y1 = max(px, 0), max(py, 0), min(px + c, W), min(py + c, H)
        if x1 > x0 and y1 > y0:
            s = spr[y0 - py:y1 - py, x0 - px:x1 - px]
            img[y0:y1, x0:x1] = np.where(s[..., 3:] > 0, s[..., :3], img[y0:y1, x0:x1])
        big = Image.fromarray(img).resize((W * ZOOM, H * ZOOM), Image.NEAREST)
        d = ImageDraw.Draw(big)
        if f.label:
            d.text((28, 24), f.label, font=font, **text)
        d.text((28, 76), f"{f.action}  frame {sheet.wrap(f.action, f.j) + 1}", font=small,
               **{**text, "fill": (230, 234, 240), "stroke_width": 2})
        ffmpeg.stdin.write(big.tobytes())
    ffmpeg.stdin.close()
    assert ffmpeg.wait() == 0, "ffmpeg failed"


def main() -> None:
    ap = argparse.ArgumentParser(prog="sprite-sheet demo", allow_abbrev=False)
    ap.add_argument("sheet_png")
    ap.add_argument("out_mp4")
    ap.add_argument("--idle", required=True, help="looping row played between moves")
    ap.add_argument("--run", required=True, help="looping row played moving forward")
    args = ap.parse_args()
    sheet = Sheet(args.sheet_png)
    for action in (args.idle, args.run):
        if action not in sheet.rows or not sheet.rows[action][1]["loop"]:
            sys.exit(f"sprite-sheet demo: {action!r} is not a looping row of {args.sheet_png}")
    frames = timeline(sheet, idle=args.idle, run=args.run)
    render(sheet, frames, args.out_mp4)
    print(f"sprite-sheet demo: {len(frames)} frames ({len(frames) / sheet.meta['fps']:.1f} s) -> {args.out_mp4}")


if __name__ == "__main__":
    main()
