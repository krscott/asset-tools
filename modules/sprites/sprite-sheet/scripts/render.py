"""Render a Rigify character's actions from the side into one sprite sheet: one row per action, one column per frame.

    blender -b CHARACTER.blend --python render.py -- OUT.png ACTION... [--cell 64] [--step 1] [--turn 25]
        [--frame-height 2.6] [--ground-margin 0.26] [--forward-shift 0.32]

The rig must be an object named 'rig', and every action needs root_forward (written by quaternius-animations).
The character faces right, turned --turn degrees from profile toward the camera so the face reads; mirror the
sheet for left. Loops leave out their last frame (it repeats the first); one-shots keep every frame. Shorter
rows leave their trailing cells empty. OUT.json lists each row's action, frame count and whether it loops, plus
the anchor: the pixel (x right, y down from a cell's top-left) where the character stands on the ground.
Each row's root is the action's root motion as screen pixels: how far forward of its frame-1 position the
character should be drawn at each frame. Loops also give root_cycle, the distance per loop, so moving the
sprite by root keeps the feet planted.
Every row uses the same orthographic framing (world units), so the character's size and ground line match across
actions. The framing defaults fit a character about 2 units tall; a warning names any frame that touches the cell
border. Only meshes skinned to the rig are rendered. Pixels are hard-edged (no anti-aliasing): each cell is
rendered at SUPERSAMPLE x resolution and reduced so every pixel is either fully transparent or an actual rendered
colour. Nothing is saved back to the .blend.
"""
import argparse
import json
import math
import os
import sys
import tempfile

import bpy
import numpy as np

ap = argparse.ArgumentParser(prog="sprite-sheet render", allow_abbrev=False)
ap.add_argument("out_png")
ap.add_argument("actions", nargs="+", help="one row per action, in this order")
ap.add_argument("--cell", type=int, default=64, help="cell size in pixels")
ap.add_argument("--step", type=int, default=1, help="render every Nth frame of each action")
ap.add_argument("--turn", type=float, default=25, help="degrees to turn the character from profile toward the camera")
ap.add_argument("--frame-height", type=float, default=2.6, help="world height (and width) a cell shows")
ap.add_argument("--ground-margin", type=float, default=0.26, help="world space below the ground line")
ap.add_argument("--forward-shift", type=float, default=0.32,
                help="how far left of centre the character stands, leaving room for forward reaches")
args = ap.parse_args(sys.argv[sys.argv.index("--") + 1:])
FRAME_HEIGHT, GROUND_MARGIN, FORWARD_SHIFT = args.frame_height, args.ground_margin, args.forward_shift
SUPERSAMPLE = 4  # render each cell at this multiple of its size before reducing it to hard-edged pixels


def pixelate(hi, k):
    """Reduce a (n*k, n*k, 4) straight-alpha image to (n, n, 4) without blending.

    A pixel is opaque when at least half its k*k block is covered; it takes the colour of the covered sample
    nearest the block centre, so outlines and colour boundaries stay hard.
    """
    n = hi.shape[0] // k
    blocks = hi.reshape(n, k, n, k, 4).transpose(0, 2, 1, 3, 4).reshape(n, n, k * k, 4)
    covered = blocks[..., 3] >= 0.5
    yy, xx = np.mgrid[0:k, 0:k] - (k - 1) / 2
    dist = np.where(covered, (yy ** 2 + xx ** 2).ravel(), np.inf)
    pick = np.take_along_axis(blocks, dist.argmin(axis=-1)[..., None, None], axis=2)[:, :, 0]
    out = np.zeros((n, n, 4), dtype=np.float32)
    opaque = covered.mean(axis=-1) >= 0.5
    out[opaque, :3] = pick[opaque, :3]
    out[opaque, 3] = 1
    return out


scene = bpy.context.scene
if 'rig' not in bpy.data.objects:
    sys.exit("sprite-sheet render: the character's Rigify rig must be an object named 'rig'")
rig = bpy.data.objects['rig']
missing = [a for a in args.actions if a not in bpy.data.actions]
if missing:
    sys.exit(f"sprite-sheet render: no such action(s): {', '.join(missing)}")
no_root = [a for a in args.actions if "root_forward" not in bpy.data.actions[a]]
if no_root:
    sys.exit(f"sprite-sheet render: no root motion on {', '.join(no_root)}; rebuild them with quaternius-animations")

# Render only the character: meshes deformed by the rig.
for o in scene.objects:
    if o.type == 'MESH':
        o.hide_render = o.parent is not rig


def images(meshes):
    """Image files the meshes' materials sample, including inside node groups."""
    trees = [slot.material.node_tree for o in meshes for slot in o.material_slots
             if slot.material and slot.material.node_tree]
    seen, found = set(), set()
    while trees:
        tree = trees.pop()
        if tree in seen:
            continue
        seen.add(tree)
        for node in tree.nodes:
            if node.type == 'TEX_IMAGE' and node.image:
                found.add(node.image)
            elif node.type == 'GROUP' and node.node_tree:
                trees.append(node.node_tree)
    return found


# A missing image file renders as solid magenta, so refuse to render without it.
lost = sorted(img.filepath for img in images(o for o in scene.objects if o.type == 'MESH' and not o.hide_render)
              if img.source == 'FILE' and not img.packed_file
              and not os.path.isfile(bpy.path.abspath(img.filepath, library=img.library)))
if lost:
    sys.exit(f"sprite-sheet render: missing texture file(s), relative to the .blend: {', '.join(lost)}")

r = scene.render
r.engine = 'BLENDER_EEVEE'
r.resolution_x = r.resolution_y = args.cell * SUPERSAMPLE
r.resolution_percentage = 100
r.film_transparent = True
r.use_stamp = False
r.image_settings.file_format = 'PNG'
r.image_settings.color_mode = 'RGBA'

cam_data = bpy.data.cameras.new("SpriteCam")
cam_data.type = 'ORTHO'
cam_data.ortho_scale = FRAME_HEIGHT
cam = bpy.data.objects.new("SpriteCam", cam_data)
scene.collection.objects.link(cam)
scene.camera = cam
# The character faces -Y. Looking along +X from her left side puts -Y on screen right;
# turning her clockwise (seen from above) swings her face toward the camera.
rig.rotation_euler.z -= math.radians(args.turn)
cam.location = (-10, -FORWARD_SHIFT, FRAME_HEIGHT / 2 - GROUND_MARGIN)
cam.rotation_euler = (math.pi / 2, 0, -math.pi / 2)

# Light from the camera side, independent of the scene's lights (the background is transparent anyway).
world = bpy.data.worlds.new("SpriteWorld")
world.node_tree.nodes['Background'].inputs['Color'].default_value = (0.6, 0.6, 0.6, 1)
scene.world = world
key = bpy.data.objects.new("SpriteKey", bpy.data.lights.new("SpriteKey", 'SUN'))
key.data.energy = 3
key.rotation_euler = (math.radians(50), 0, math.radians(-60))  # from above, the camera side and slightly in front
scene.collection.objects.link(key)

c = args.cell
cell_path = os.path.join(tempfile.mkdtemp(prefix="sprites_"), "cell.png")
rows = []
for name in args.actions:
    act = bpy.data.actions[name]
    rig.animation_data.action = act
    last = int(act.frame_end) - act.use_cyclic  # a loop's last key repeats its first
    frames = range(int(act.frame_start), last + 1, args.step)
    strip = []
    # Root motion seen from the camera: the character walks across the screen while turned toward it.
    root = [d * c / FRAME_HEIGHT * math.cos(math.radians(args.turn)) for d in act["root_forward"]]
    for f in frames:
        scene.frame_set(f)
        r.filepath = cell_path
        bpy.ops.render.render(write_still=True)
        img = bpy.data.images.load(cell_path, check_existing=False)
        hi = np.array(img.pixels[:], dtype=np.float32).reshape(c * SUPERSAMPLE, c * SUPERSAMPLE, 4)[::-1]  # Blender rows are bottom-up
        px = pixelate(hi, SUPERSAMPLE)
        bpy.data.images.remove(img)
        edge = np.concatenate([px[0, :, 3], px[-1, :, 3], px[:, 0, 3], px[:, -1, 3]])
        if edge.any():
            print(f"sprite-sheet render: warning: {name} frame {f} touches the cell border and may be cropped")
        strip.append(px)
    row = {"action": name, "frames": len(strip), "loop": act.use_cyclic,
           "root": [round(root[f - frames.start], 2) for f in frames]}
    if act.use_cyclic:
        row["root_cycle"] = round(root[-1], 2)
    rows.append((row, strip))
    print(f"sprite-sheet render: {name}: {len(strip)} frames")

cols = max(len(strip) for _, strip in rows)
sheet = np.zeros((len(rows) * c, cols * c, 4), dtype=np.float32)
for i, (_, strip) in enumerate(rows):
    for j, px in enumerate(strip):
        sheet[i * c:(i + 1) * c, j * c:(j + 1) * c] = px

out_png = os.path.abspath(args.out_png)  # Blender can't save to a bare relative path
os.makedirs(os.path.dirname(out_png), exist_ok=True)
img = bpy.data.images.new("sprite_sheet", cols * c, len(rows) * c, alpha=True)
img.pixels.foreach_set(sheet[::-1].ravel())
img.filepath_raw = out_png
img.file_format = 'PNG'
img.save()
bpy.data.images.remove(img)
with open(os.path.splitext(args.out_png)[0] + ".json", "w") as fh:
    json.dump({
        "image": os.path.basename(args.out_png), "cell": c, "fps": scene.render.fps / args.step,
        "facing": "right", "turn": args.turn,
        "anchor": [round(c / 2 - FORWARD_SHIFT * c / FRAME_HEIGHT, 2), round(c - GROUND_MARGIN * c / FRAME_HEIGHT, 2)],
        "rows": [row for row, _ in rows],
    }, fh, indent=2)
print(f"sprite-sheet render: {len(rows)} rows x {cols} columns -> {args.out_png}")
