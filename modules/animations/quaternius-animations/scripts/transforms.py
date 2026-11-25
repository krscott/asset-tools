"""Style transforms: edit a copied action's keys to change how the motion reads.

Each transform takes the action's Channels plus keyword parameters, which come from the config. They are written
for Rigify controls as the Universal Animation Library keys them (foot_ik, torso, chest, hips, upper_arm_fk,
hand_fk) and assume the character faces -Y.
"""
import inspect
import math
from typing import Any, Callable

import bpy
from bpy_extras import anim_utils
from mathutils import Quaternion as Q, Vector as V

X, Y, Z = V((1, 0, 0)), V((0, 1, 0)), V((0, 0, 1))  # world axes: right, back, up


class Channels:
    """Read and rewrite the keys of one action on the rig, keeping their frames."""

    def __init__(self, rig: bpy.types.Object, action: bpy.types.Action):
        self.rig = rig
        self.action = action
        self.fcurves = anim_utils.action_get_channelbag_for_slot(action, rig.animation_data.action_slot).fcurves

    def _curves(self, bone: str, prop: str) -> list:
        path = f'pose.bones["{bone}"].{prop}'
        fcs = sorted((fc for fc in self.fcurves if fc.data_path == path), key=lambda fc: fc.array_index)
        assert fcs, f"{bone}.{prop} is not keyed"
        return fcs

    def get(self, bone: str, prop: str, cls: type) -> list:
        fcs = self._curves(bone, prop)
        return [cls([fc.keyframe_points[i].co[1] for fc in fcs]) for i in range(len(fcs[0].keyframe_points))]

    def put(self, bone: str, prop: str, values: list) -> None:
        for j, fc in enumerate(self._curves(bone, prop)):
            for kp, v in zip(fc.keyframe_points, values):
                kp.co[1] = v[j]
            fc.update()

    def local_axis(self, bone: str, world_axis: V) -> V:
        """A world-space direction expressed in the bone's rest (local) frame."""
        return self.rig.data.bones[bone].matrix_local.to_quaternion().inverted() @ world_axis


def twist(q: Q, axis: V) -> float:
    """Signed twist angle of q about a unit axis (swing-twist decomposition)."""
    a = 2 * math.atan2(V((q.x, q.y, q.z)).dot(axis), q.w)
    return (a + math.pi) % (2 * math.pi) - math.pi


def scale_twist(q: Q, axis: V, k: float) -> Q:
    a = twist(q, axis)
    return q @ Q(axis, a).inverted() @ Q(axis, k * a)


def mean(qs: list[Q]) -> Q:
    m = Q((0, 0, 0, 0))
    for q in qs:
        m = m + (q if q.dot(qs[0]) >= 0 else -q)
    return m.normalized()


def narrow_feet(ch: Channels, *, offset: float) -> None:
    """Plant each foot `offset` closer to the centre line."""
    for side, inward in (("L", -1), ("R", 1)):
        bone = f"foot_ik.{side}"
        d = ch.local_axis(bone, X) * (inward * offset)
        ch.put(bone, "location", [loc + d for loc in ch.get(bone, "location", V)])


def hips_not_shoulders(ch: Channels, *, chest_twist: float, hip_twist: float, hip_tilt: float) -> None:
    """Move the step's twist from the shoulders to the pelvis and deepen the side-to-side hip drop.

    The chest keeps chest_twist of its twist; the pelvis counter-rotates by hip_twist of the original chest twist,
    so it stays in step; the hip drop is scaled by hip_tilt.
    """
    chest, hips = ch.get("chest", "rotation_quaternion", Q), ch.get("hips", "rotation_quaternion", Q)
    assert len(chest) == len(hips)
    c_up = ch.local_axis("chest", Z)
    angles = [twist(q, c_up) for q in chest]
    ch.put("chest", "rotation_quaternion", [scale_twist(q, c_up, chest_twist) for q in chest])
    h_up, h_fwd = ch.local_axis("hips", Z), ch.local_axis("hips", Y)
    ch.put("hips", "rotation_quaternion",
           [Q(h_up, -hip_twist * a) @ scale_twist(q, h_fwd, hip_tilt) for q, a in zip(hips, angles)])


def arms_in(ch: Channels, *, swing: float, elbows_in_deg: float) -> None:
    """Scale the arm swing about its mean pose and turn the upper arms toward the body (negative: away)."""
    for side, inward in (("L", 1), ("R", -1)):
        bone = f"upper_arm_fk.{side}"
        qs = ch.get(bone, "rotation_quaternion", Q)
        m = mean(qs)
        tuck = Q(ch.local_axis(bone, Y), inward * math.radians(elbows_in_deg))
        ch.put(bone, "rotation_quaternion", [tuck @ m.slerp(q, swing) for q in qs])


def flick_wrists(ch: Channels, *, deg: float) -> None:
    """Bend the wrists back so the hands flare away from the body."""
    for side, sign in (("L", -1), ("R", 1)):
        bone = f"hand_fk.{side}"
        bend = Q(ch.local_axis(bone, Y), sign * math.radians(deg))
        ch.put(bone, "rotation_quaternion", [q @ bend for q in ch.get(bone, "rotation_quaternion", Q)])


def lighter_steps(ch: Channels, *, stride: float, bob: float) -> None:
    """Scale the feet's forward/back travel and the ground covered by stride, and the torso's bounce by bob."""
    for bone, axis, k in (("foot_ik.L", Y, stride), ("foot_ik.R", Y, stride), ("torso", Z, bob)):
        a = ch.local_axis(bone, axis)
        locs = ch.get(bone, "location", V)
        c = sum(l.dot(a) for l in locs) / len(locs)
        ch.put(bone, "location", [l + a * ((k - 1) * (l.dot(a) - c)) for l in locs])
    ch.action["root_forward"] = [r * stride for r in ch.action["root_forward"]]


TRANSFORMS: dict[str, Callable[..., None]] = {
    f.__name__: f for f in (narrow_feet, hips_not_shoulders, arms_in, flick_wrists, lighter_steps)
}


def check(name: str, params: dict[str, Any]) -> None:
    """Raise ValueError unless name is a transform that takes exactly these parameters."""
    if name not in TRANSFORMS:
        raise ValueError(f"unknown transform {name!r}; known: {', '.join(TRANSFORMS)}")
    try:
        inspect.signature(TRANSFORMS[name]).bind(None, **params)
    except TypeError as e:
        raise ValueError(f"{name}: {e} (parameters: {inspect.signature(TRANSFORMS[name])})") from e
