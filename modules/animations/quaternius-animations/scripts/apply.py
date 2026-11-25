"""Run in Blender on the character: apply sampled pack actions to its Rigify rig, restyle them, save in place.

    blender -b CHARACTER.blend --python apply.py -- CONFIG.toml SAMPLES.json...

Each action replaces any action of the same name. *_Loop actions become cyclic loops (the last key repeats the
first); others play once, keeping every frame. An action's root_forward property holds the dropped root motion:
forward distance from frame 1 at each frame.
"""
import json
import os
import sys

import bpy
from bpy_extras import anim_utils
from mathutils import Quaternion as Q, Vector as V

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config  # noqa: E402
import transforms  # noqa: E402

CONFIG, *SAMPLE_FILES = sys.argv[sys.argv.index("--") + 1:]
cfg = config.load(CONFIG)
for style in cfg.styles:
    for name, params in style.transforms:
        transforms.check(name, params)
samples = {}
for path in SAMPLE_FILES:
    with open(path) as fh:
        samples |= json.load(fh)

if "rig" not in bpy.data.objects:
    raise ValueError("the character's Rigify rig must be an object named 'rig'")
rig = bpy.data.objects["rig"]
pb = rig.pose.bones
B = rig.data.bones
scene = bpy.context.scene
FPS = scene.render.fps
skipped: set[str] = set()  # pack controls the rig lacks (e.g. fingers)


def apply(name: str, d: dict) -> bpy.types.Action:
    n_src = len(d["samples"]) - 1
    step = round(n_src * FPS / d["fps"]) / n_src  # retime to the scene fps, ending on a whole frame
    scale = (B["ORG-thigh.L"].head_local.z - B["ORG-foot.L"].head_local.z) / (d["thigh_z"] - d["ankle_z"])
    # Map each control's rest-relative motion into our bone's local axes (they differ only where bone rolls differ).
    conv = {n: B[n].matrix_local.to_quaternion().inverted() @ Q(r) for n, r in d["rest"].items() if n in B}
    skipped.update(set(d["rest"]) - set(conv))
    # Foot positions are keyed relative to the pack mannequin's rest stance (feet under the hips). If the
    # character's rest pose has the feet further out, shift them to keep the pack's foot-to-hip relation.
    stance = (d["ankle_x"] - d["thigh_x"]) * scale - (B["ORG-foot.L"].head_local.x - B["ORG-thigh.L"].head_local.x)
    stance_fix = {f"foot_ik.{s}": B[f"foot_ik.{s}"].matrix_local.to_quaternion().inverted() @ V((sign * stance, 0, 0))
                  for s, sign in (("L", 1), ("R", -1))}

    if name in bpy.data.actions:
        bpy.data.actions.remove(bpy.data.actions[name])
    act = bpy.data.actions.new(name)
    act.use_fake_user = True
    rig.animation_data_create()
    rig.animation_data.action = act
    for p in pb:
        p.matrix_basis.identity()
    for s in "LR":  # legs IK (feet placed directly), arms FK (driven by joint rotations)
        pb[f"thigh_parent.{s}"]["IK_FK"] = 0.0
        pb[f"thigh_parent.{s}"].keyframe_insert('["IK_FK"]', frame=1)
        pb[f"upper_arm_parent.{s}"]["IK_FK"] = 1.0
        pb[f"upper_arm_parent.{s}"].keyframe_insert('["IK_FK"]', frame=1)
    prev = {}
    for i, smp in enumerate(d["samples"]):
        fr = 1 + i * step
        for n, (loc, q) in smp.items():
            if n not in conv:
                continue
            c = conv[n]
            p = pb[n]
            p.rotation_mode = "QUATERNION"
            rq = c @ Q(q) @ c.inverted()
            if n in prev:
                rq.make_compatible(prev[n])
            prev[n] = rq
            p.rotation_quaternion = rq
            p.keyframe_insert("rotation_quaternion", frame=fr)
            if not all(p.lock_location):
                p.location = c @ V(loc) * scale + stance_fix.get(n, V())
                p.keyframe_insert("location", frame=fr)
    # Key every other control at rest, so this action fully defines the pose whichever action played before it.
    for p in pb:
        if p.name in conv or p.name.startswith(("ORG-", "DEF-", "MCH-", "VIS-")):
            continue
        p.matrix_basis.identity()
        p.location = stance_fix.get(p.name, V())
        rot = {"QUATERNION": "rotation_quaternion", "AXIS_ANGLE": "rotation_axis_angle"}.get(p.rotation_mode,
                                                                                            "rotation_euler")
        for path, locked in (("location", p.lock_location), (rot, p.lock_rotation), ("scale", p.lock_scale)):
            if not all(locked):
                p.keyframe_insert(path, frame=1)
    N = round(n_src * step)
    if d["loop"]:
        for fc in anim_utils.action_get_channelbag_for_slot(act, rig.animation_data.action_slot).fcurves:
            fc.modifiers.new("CYCLES")
    act.use_cyclic = d["loop"]
    act.use_frame_range = True
    act.frame_start = 1
    act.frame_end = 1 + N
    src = d["root_forward"]

    def root_at(t: float) -> float:  # t in source samples
        i = min(int(t), n_src - 1)
        return (src[i] + (src[i + 1] - src[i]) * (t - i)) * scale

    act["root_forward"] = [root_at(min(k / step, n_src)) for k in range(N + 1)]
    kind = f"loop of {N}" if d["loop"] else f"one-shot of {N + 1}"
    print(f"apply: {name}: {len(d['samples'])} src frames -> {kind} frames @ {FPS}fps, loc scale {scale:.3f}, "
          f"stance shift {stance:+.3f}, root forward {act['root_forward'][-1]:.3f}")
    return act


def restyle(style: config.Style) -> None:
    if style.name in bpy.data.actions:
        bpy.data.actions.remove(bpy.data.actions[style.name])
    act = bpy.data.actions[style.source].copy()
    act.name = style.name
    act.use_fake_user = True
    rig.animation_data.action = act
    ch = transforms.Channels(rig, act)
    for name, params in style.transforms:
        transforms.TRANSFORMS[name](ch, **params)
        print(f"apply: {style.name}: {name} {params}")


for specs in cfg.actions.values():
    for spec in specs:
        apply(config.action_name(spec), samples[spec])
for style in cfg.styles:
    restyle(style)
act = rig.animation_data.action = bpy.data.actions[cfg.active]
scene.frame_start, scene.frame_end = 1, int(act.frame_end) - act.use_cyclic  # a loop's last key repeats its first
scene.frame_set(1)
if skipped:
    print(f"apply: {len(skipped)} pack controls are not in the rig and were skipped: {', '.join(sorted(skipped))}")
bpy.ops.wm.save_mainfile()
