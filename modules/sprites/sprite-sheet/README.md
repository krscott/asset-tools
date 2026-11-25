# sprite-sheet

Render a Rigify character's actions to a side-view, pixel-art sprite sheet, and a demo video of the sheet.

```sh
sprite-sheet render character.blend sheet.png Idle_Feminine Jog_Feminine Punch_Jab ... \
  [--cell 64] [--step 1] [--turn 25] [--frame-height 2.6] [--ground-margin 0.26] [--forward-shift 0.32]
sprite-sheet demo sheet.png demo.mp4 --idle Idle_Feminine --run Jog_Feminine
```

## render

One row per action, one column per frame, facing right and turned `--turn` degrees toward the camera. Pixels are
hard-edged: each cell is rendered at 4x and reduced so every pixel is fully transparent or an actual rendered
colour. Every row shares one orthographic framing, in world units: the cell shows `--frame-height` square,
`--ground-margin` of it below the ground, with the character `--forward-shift` left of centre to leave room for
forward reaches. A warning names any frame that touches the cell border. The rig must be an object named `rig`;
only meshes parented to it are rendered, and the render stops if one of their texture files is missing.

`sheet.json` describes the sheet:

- `cell`, `fps`, `facing` (`"right"`), `turn`
- `anchor`: the pixel (x right, y down from a cell's top-left) where the character stands on the ground
- `rows`: per action, `frames`, `loop`, and `root`: how many screen pixels forward of its frame-1 position to draw
  the character on each frame. Loops also have `root_cycle`, the distance per loop. Moving the sprite by these
  keeps the feet planted. Every action needs `root_forward`, as `quaternius-animations` writes.

## demo

Plays the idle, the run, a jump with a double jump (when the sheet has the four `NinjaJump_*` rows), then every
other row as an attack, in sheet order, on a small parallax stage at 4x. The jump's height and gravity are made
up; a game would set its own.
