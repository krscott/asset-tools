"""Run in Blender on a UAL pack: dump each SPEC's per-frame control transforms to OUT.json for apply.py.

    blender -b --disable-autoexec UAL1.blend --python sample.py -- OUT.json SPEC...

SPEC is an action name, or several joined with '+' (e.g. Melee_Hook+Melee_Hook_Rec) to play them back to back;
each later part's first frame is dropped because it repeats the previous part's last pose. A SPEC loops only when
it is a single *_Loop action. Root motion is left out of the samples; root_forward records how far the root has
travelled forward (pack units) at each sample instead.
"""
import json
import re
import sys

import bpy
from bpy_extras import anim_utils

arm = bpy.data.objects["Armature"]
scene = bpy.context.scene


def root_y() -> float:
    return (arm.matrix_world @ arm.pose.bones["root"].head).y


def sample(spec: str) -> dict:
    parts = spec.split("+")
    missing = [p for p in parts if p not in bpy.data.actions]
    if missing:
        raise ValueError(f"no such action(s) in this pack: {', '.join(missing)}")
    names = set()
    for p in parts:
        arm.animation_data.action = bpy.data.actions[p]
        cb = anim_utils.action_get_channelbag_for_slot(bpy.data.actions[p], arm.animation_data.action_slot)
        names |= {re.match(r'pose\.bones\["(.+?)"\]', fc.data_path).group(1)
                  for fc in cb.fcurves if fc.data_path.startswith("pose.bones")}
    names = sorted(names - {"root"})

    bones = arm.data.bones
    out = {
        "fps": scene.render.fps,
        "loop": len(parts) == 1 and parts[0].endswith("_Loop"),
        "rest": {n: list(bones[n].matrix_local.to_quaternion()) for n in names},
        "thigh_z": bones["ORG-thigh.L"].head_local.z, "ankle_z": bones["ORG-foot.L"].head_local.z,
        "thigh_x": bones["ORG-thigh.L"].head_local.x, "ankle_x": bones["ORG-foot.L"].head_local.x,
        "samples": [], "root_forward": [],
    }
    base = 0.0  # forward distance at the end of the previous part
    for i, p in enumerate(parts):
        act = bpy.data.actions[p]
        arm.animation_data.action = act
        for pb in arm.pose.bones:  # controls this part doesn't key sit at rest, not at the previous part's pose
            pb.matrix_basis.identity()
        f0, f1 = map(int, act.frame_range)
        scene.frame_set(f0)
        y0 = root_y()
        for f in range(f0 + (i > 0), f1 + 1):
            scene.frame_set(f)
            out["root_forward"].append(base + y0 - root_y())  # the mannequin faces -Y
            out["samples"].append({n: [list(arm.pose.bones[n].matrix_basis.to_translation()),
                                       list(arm.pose.bones[n].matrix_basis.to_quaternion())] for n in names})
        base = out["root_forward"][-1]
    print(f"sample: {spec}: {len(out['samples'])} frames, loop={out['loop']}, {len(names)} controls, "
          f"root forward {out['root_forward'][-1]:.3f}")
    return out


OUT, *SPECS = sys.argv[sys.argv.index("--") + 1:]
with open(OUT, "w") as fh:
    json.dump({spec: sample(spec) for spec in SPECS}, fh)
