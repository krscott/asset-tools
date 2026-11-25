"""The build config: which pack actions to copy onto a character, how to restyle them, and which to leave active.

Plain Python (no bpy), so the command can check a config before starting Blender.
"""
import os
import tomllib
from dataclasses import dataclass
from typing import Any

# Pack name -> .blend, relative to the vendor checkout.
PACKS = {
    "UAL1": "quaternius/universal-animation-library/files/UAL1.blend",
    "UAL2": "quaternius/universal-animation-library-2/files/UAL2.blend",
}


@dataclass(frozen=True, kw_only=True)
class Style:
    name: str
    source: str
    transforms: list[tuple[str, dict[str, Any]]]  # applied in order


@dataclass(frozen=True, kw_only=True)
class Config:
    active: str
    actions: dict[str, list[str]]  # pack -> specs ("Name" or "Name+Recovery")
    styles: list[Style]


def action_name(spec: str) -> str:
    """A spec joining several pack actions is applied under the first one's name."""
    return spec.split("+")[0]


def load(path: str) -> Config:
    """Read and check a config; raises ValueError naming the problem."""
    with open(path, "rb") as fh:
        d = tomllib.load(fh)

    def check(ok: bool, msg: str) -> None:
        if not ok:
            raise ValueError(f"{path}: {msg}")

    check(not (extra := set(d) - {"active", "actions", "styles"}), f"unknown keys {sorted(extra)}")
    actions = d.get("actions", {})
    check(isinstance(actions, dict) and actions, "[actions] must map pack names to lists of action specs")
    for pack, specs in actions.items():
        check(pack in PACKS, f"unknown pack {pack!r}; known packs: {', '.join(PACKS)}")
        check(isinstance(specs, list) and all(isinstance(s, str) and s for s in specs),
              f"actions.{pack} must be a list of action names")
    names = [action_name(s) for specs in actions.values() for s in specs]
    check(len(names) == len(set(names)), "an action name is listed twice")

    styles = []
    for name, st in d.get("styles", {}).items():
        check(isinstance(st, dict) and isinstance(st.get("source"), str), f"styles.{name} needs source = \"ACTION\"")
        check(st["source"] in names, f"styles.{name}.source {st['source']!r} is not one of the [actions]")
        check(name not in names, f"style {name!r} has the same name as an action")
        transforms = [(t, kw) for t, kw in st.items() if t != "source"]
        check(all(isinstance(kw, dict) for _, kw in transforms),
              f"styles.{name}: each transform takes a table of parameters, e.g. narrow_feet = {{ offset = 0.05 }}")
        styles.append(Style(name=name, source=st["source"], transforms=transforms))

    active = d.get("active")
    check(isinstance(active, str), "active = \"ACTION\" is required (the action left on the rig)")
    check(active in names or active in {s.name for s in styles}, f"active {active!r} is not an action or style")
    return Config(active=active, actions=actions, styles=styles)


def pack_path(vendor_dir: str, pack: str) -> str:
    """The pack's .blend in the vendor checkout; raises ValueError if it is missing or not pulled from LFS."""
    path = os.path.join(vendor_dir, PACKS[pack])
    if not os.path.isfile(path):
        raise ValueError(f"{path} not found; is VENDOR_DIR your vendor checkout, pulled?")
    with open(path, "rb") as fh:
        if fh.read(40).startswith(b"version https://git-lfs"):
            raise ValueError(f"{path} is a Git LFS pointer; run `git lfs pull` in the vendor checkout")
    return path
