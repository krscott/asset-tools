"""quaternius-animations CONFIG.toml CHARACTER.blend

Copy Universal Animation Library actions onto a Rigify character and restyle them, as CONFIG describes. Packs
are read from the vendor checkout at $VENDOR_DIR. CHARACTER is saved in place; actions it has that CONFIG does
not name are left alone.
"""
import argparse
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)  # run with python -I, which leaves the script's directory off the path
import config  # noqa: E402


def blender(blend: str, script: str, *args: str) -> None:
    cmd = ["blender", "-b", "--factory-startup", "--disable-autoexec", "--python-exit-code", "1",
           blend, "--python", script, "--", *args]
    if subprocess.run(cmd).returncode:
        sys.exit(f"quaternius-animations: Blender failed running {os.path.basename(script)} on {blend}; "
                 "see its output above")


def main() -> None:
    ap = argparse.ArgumentParser(prog="quaternius-animations", allow_abbrev=False,
                                 description=__doc__.split("\n\n", 1)[1])
    ap.add_argument("config")
    ap.add_argument("character")
    args = ap.parse_args()

    vendor_dir = os.environ.get("VENDOR_DIR")
    if not vendor_dir:
        sys.exit("quaternius-animations: set VENDOR_DIR to your checkout of the vendor repo")
    try:
        cfg = config.load(args.config)
        packs = {pack: config.pack_path(vendor_dir, pack) for pack in cfg.actions}
    except ValueError as e:
        sys.exit(f"quaternius-animations: {e}")

    with tempfile.TemporaryDirectory(prefix="quaternius-animations-") as tmp:
        samples = []
        for pack, specs in cfg.actions.items():
            out = os.path.join(tmp, f"{pack}.json")
            blender(packs[pack], os.path.join(HERE, "sample.py"), out, *specs)
            samples.append(out)
        blender(args.character, os.path.join(HERE, "apply.py"), args.config, *samples)


if __name__ == "__main__":
    main()
