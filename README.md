# asset-tools

Tools that turn purchased asset packs into game-ready files, as a flake.

- [quaternius-animations](modules/animations/quaternius-animations/README.md): copy Universal Animation Library actions
  onto a Rigify character and restyle them, from a TOML config.
- [sprite-sheet](modules/sprites/sprite-sheet/README.md): render a character's actions to a pixel-art sprite sheet, and a
  demo video of it.

## Use

A game repo takes the tools as a flake input, and commits its configs and the tools' outputs:

```nix
inputs.asset-tools.url = "github:krscott/asset-tools";
# devShell: packages = [ inputs.asset-tools.packages.${system}.quaternius-animations ... ];
```

Tools that read packs find them at `$VENDOR_DIR`, a checkout of the vendor repo with its Git LFS files pulled. Only
running those tools needs it: anyone can enter the dev shell and build the game from the committed outputs. Set it
once in your environment, e.g. with Home Manager:

```nix
home.sessionVariables.VENDOR_DIR = "/path/to/vendor";
```

Packs are append-only, so a pinned tool version and a pack path always give the same result. A tool names the exact
pack directory it uses; a vendor's update to a pack is a new directory.

`nix develop` here gives every tool, plus Blender.

## Conventions

- **Every `.nix` file under `modules/` is a flake-parts module** ([import-tree](https://github.com/denful/import-tree)
  imports them all, except paths containing `/_`). A new tool is a directory with its module, README and scripts.
- **Tools run outside the Nix sandbox.** Blender's EEVEE renderer needs a GPU, which builds don't have, so outputs
  are made by running the tools, not as Nix builds.
