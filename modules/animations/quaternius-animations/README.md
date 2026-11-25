# quaternius-animations

Copy actions from Quaternius' Universal Animation Library packs onto a Rigify character, and restyle them.

```sh
quaternius-animations animations.toml character.blend
```

The character's rig must be a Rigify rig object named `rig`. Packs are read from your vendor checkout at
`$VENDOR_DIR`. The .blend is saved in place; actions it has that the config doesn't name are left alone. Each run
rebuilds every action in the config from the packs, so the config is the whole record of how they were made.

## Config

```toml
active = "Jog_Feminine"  # the action left on the rig; the scene's frame range is set to it

# Pack actions to copy. "A+B" plays A then B (an attack and its recovery) and is applied as A.
[actions]
UAL1 = ["Idle_Loop", "Jog_Fwd_Loop", "Punch_Jab"]
UAL2 = ["NinjaJump_Start", "Melee_Hook+Melee_Hook_Rec"]

# A restyled copy of an action above. Transforms apply in the order written.
[styles.Jog_Feminine]
source = "Jog_Fwd_Loop"
narrow_feet = { offset = 0.045 }
lighter_steps = { stride = 0.85, bob = 0.8 }
```

Packs (Source tier, in the vendor repo): `UAL1`
([Universal Animation Library](https://quaternius.itch.io/universal-animation-library)), `UAL2`
([Universal Animation Library 2](https://quaternius.itch.io/universal-animation-library-2)). Browse their actions in
the [Animation Viewer](https://quaternius.com/animviewer.html).

## What copying does

The packs key the same Rigify control names, so actions are copied control by control:

- **Retimed** from the pack's 30 fps to the scene's, ending on a whole frame.
- **Scaled** by the ratio of leg lengths (hip to ankle), so steps fit the character.
- **Rotations converted** into each control's rest orientation, where its bone roll differs from the pack's.
- **Feet kept under the hips.** The pack mannequin's rest pose has the feet under the hips; when the character's
  rest pose stands wider, the feet are shifted in to keep the pack's stance.
- **Root motion kept as data, not keys:** the action plays in place, and its `root_forward` property holds the
  forward distance from frame 1 at each frame (scaled like the keys). `sprite-sheet` turns it into screen pixels.
- Legs use IK, arms FK. Controls the action doesn't animate are keyed at rest, so switching actions never leaves
  a stale pose. Controls the rig lacks (the pack has fingers) are skipped.
- `*_Loop` actions loop (the last key repeats the first); others play once.

## Transforms

Parameters are scale factors (1 keeps the motion) unless marked as distances or degrees.

| Transform | Parameters | Effect |
|---|---|---|
| `narrow_feet` | `offset` (distance) | Plant each foot this much closer to the centre line. |
| `hips_not_shoulders` | `chest_twist`, `hip_twist`, `hip_tilt` | Keep `chest_twist` of the shoulders' twist; counter-rotate the pelvis by `hip_twist` of it; scale the side-to-side hip drop. |
| `arms_in` | `swing`, `elbows_in_deg` (degrees) | Scale the arm swing about its mean pose; turn the upper arms toward the body (negative: away). |
| `flick_wrists` | `deg` (degrees) | Bend the wrists back so the hands flare out. |
| `lighter_steps` | `stride`, `bob` | Scale the feet's forward/back travel and the ground covered; scale the torso's bounce. |
