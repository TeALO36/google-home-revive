"""Generate the project-specific footprints (hardware/lib/gh_revive.pretty)."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .mechanical import JACK


@dataclass(frozen=True)
class PadDef:
    number: str
    kind: str  # "smd", "thru", "npth"
    x: float
    y: float
    w: float
    h: float
    drill: float = 0.0
    layer: str = "F"


def _pad_sexpr(pad: PadDef) -> str:
    if pad.kind == "smd":
        layers = f'"{pad.layer}.Cu" "{pad.layer}.Paste" "{pad.layer}.Mask"'
        return (f'\t(pad "{pad.number}" smd roundrect (at {pad.x:.3f} {pad.y:.3f}) (size {pad.w:.3f} {pad.h:.3f}) '
                f"(layers {layers}) (roundrect_rratio 0.2))")
    if pad.kind == "ring":  # annular SMD pad (microphone acoustic seal): w = outer diameter, drill = inner diameter
        mid = (pad.w + pad.drill) / 4
        width = (pad.w - pad.drill) / 2
        return (f'\t(pad "{pad.number}" smd custom (at {pad.x:.3f} {pad.y - mid:.3f}) (size {width:.3f} {width:.3f}) '
                f'(layers "F.Cu" "F.Paste" "F.Mask") (options (clearance outline) (anchor circle)) '
                f'(primitives (gr_circle (center 0 {mid:.3f}) (end {mid:.3f} {mid:.3f}) (width {width:.3f}) (fill no))))')
    if pad.kind == "thru":
        return (f'\t(pad "{pad.number}" thru_hole circle (at {pad.x:.3f} {pad.y:.3f}) (size {pad.w:.3f} {pad.h:.3f}) '
                f'(drill {pad.drill:.3f}) (layers "*.Cu" "*.Mask"))')
    return (f'\t(pad "" np_thru_hole circle (at {pad.x:.3f} {pad.y:.3f}) (size {pad.drill:.3f} {pad.drill:.3f}) '
            f'(drill {pad.drill:.3f}) (layers "*.Cu" "*.Mask"))')


def _rect_sexpr(layer: str, x0: float, y0: float, x1: float, y1: float, width: float) -> str:
    return (f'\t(fp_rect (start {x0:.3f} {y0:.3f}) (end {x1:.3f} {y1:.3f}) '
            f'(stroke (width {width}) (type solid)) (fill no) (layer "{layer}"))')


def _footprint_sexpr(name: str, description: str, pads: list[PadDef], side: str, attr: str) -> str:
    xs = [p.x - p.w / 2 for p in pads] + [p.x + p.w / 2 for p in pads]
    ys = [p.y - p.h / 2 for p in pads] + [p.y + p.h / 2 for p in pads]
    x0, x1, y0, y1 = min(xs) - 0.25, max(xs) + 0.25, min(ys) - 0.25, max(ys) + 0.25
    lines = [
        f'(footprint "{name}"',
        '\t(version 20240108)',
        '\t(generator "ghrevive")',
        f'\t(layer "{side}.Cu")',
        f'\t(descr "{description}")',
        f'\t(property "Reference" "REF**" (at 0 {y0 - 1.0:.3f} 0) (layer "{side}.SilkS") '
        '(effects (font (size 0.8 0.8) (thickness 0.12))))',
        f'\t(property "Value" "{name}" (at 0 {y1 + 1.0:.3f} 0) (layer "{side}.Fab") '
        '(effects (font (size 0.8 0.8) (thickness 0.12))))',
        f'\t(attr {attr})',
        _rect_sexpr(f"{side}.CrtYd", x0, y0, x1, y1, 0.05),
        _rect_sexpr(f"{side}.Fab", x0 + 0.15, y0 + 0.15, x1 - 0.15, y1 - 0.15, 0.1),
    ]
    lines += [_pad_sexpr(p) for p in pads]
    lines.append(")")
    return "\n".join(lines) + "\n"


def _jack_pads() -> list[PadDef]:
    """Land pattern of the original SMD DC jack, in front-view coordinates, pads on the back copper.

    Origin = centre of the stem end edge. x grows towards the board interior (negative), y as on the board front.
    """
    pads = [PadDef(name, "smd", -tab.depth, -tab.back_y, tab.length, tab.width, layer="B") for name, tab in JACK.tabs.items()]
    pads += [PadDef("", "npth", -depth, 0.0, 0.0, 0.0, drill=JACK.peg_drill) for depth in JACK.peg_depths]
    return pads


def _wire_pads(count: int, pitch: float, width: float, height: float) -> list[PadDef]:
    start = -pitch * (count - 1) / 2
    return [PadDef(str(i + 1), "smd", start + i * pitch, 0.0, width, height) for i in range(count)]


def _qfn20_pads() -> list[PadDef]:
    """MPR121 UQFN-20 3 x 3 mm, 0.4 mm pitch, no exposed pad. Pin 1 bottom-left, counter-clockwise (top view)."""
    pads: list[PadDef] = []
    offsets = (-0.8, -0.4, 0.0, 0.4, 0.8)
    for i, offset in enumerate(offsets):
        pads.append(PadDef(str(1 + i), "smd", offset, 1.4, 0.2, 0.8))  # bottom, left -> right
        pads.append(PadDef(str(6 + i), "smd", 1.4, -offset, 0.8, 0.2))  # right, bottom -> top
        pads.append(PadDef(str(11 + i), "smd", -offset, -1.4, 0.2, 0.8))  # top, right -> left
        pads.append(PadDef(str(16 + i), "smd", -1.4, offset, 0.8, 0.2))  # left, top -> bottom
    return pads


def _im69d130_pads() -> list[PadDef]:
    """Infineon IM69D130 (4 x 3 mm, bottom port). Acoustic port at (0, 0.81), drilled 0.6 mm through the board."""
    signal = [("1", 0.85, -1.37), ("2", 0.85, -0.67), ("3", -0.85, -1.37), ("4", -0.85, -0.67)]
    pads = [PadDef(n, "smd", x, y, 0.75, 0.45) for n, x, y in signal]
    pads.append(PadDef("5", "ring", 0.0, 0.81, 1.9, 1.9, drill=1.1))
    pads.append(PadDef("", "npth", 0.0, 0.81, 0.0, 0.0, drill=0.6))
    return pads


def write_project_footprints(lib_dir: Path) -> list[Path]:
    lib_dir.mkdir(parents=True, exist_ok=True)
    definitions = {
        "GH_DCJack_Original": ("Land pattern replicating the original Google Home DC jack (reuse the original part)",
                               _jack_pads(), "B", "smd exclude_from_pos_files"),
        "GH_WirePads_1x10_P2.54mm": ("10 solder pads for the main-board link wires", _wire_pads(10, 2.54, 1.6, 3.4),
                                     "F", "smd exclude_from_pos_files exclude_from_bom"),
        "GH_SpeakerPads": ("2 solder pads for speaker wires", _wire_pads(2, 2.7, 2.0, 2.4),
                           "F", "smd exclude_from_pos_files exclude_from_bom"),
        "GH_ElectrodeTap": ("Through connection from a touch electrode to the component side",
                            [PadDef("1", "thru", 0.0, 0.0, 0.7, 0.7, drill=0.3)], "F",
                            "through_hole exclude_from_pos_files exclude_from_bom"),
        "GH_TestPad_1.5mm": ("Round test / solder pad", [PadDef("1", "smd", 0.0, 0.0, 1.5, 1.5)], "F",
                             "smd exclude_from_pos_files exclude_from_bom"),
        "GH_QFN20_MPR121": ("MPR121QR2 UQFN-20 3x3 mm P0.4 mm", _qfn20_pads(), "F", "smd"),
        "GH_MIC_IM69D130": ("IM69D130 bottom-port PDM microphone, port hole 0.6 mm", _im69d130_pads(), "F", "smd"),
    }
    written = []
    for name, (description, pads, side, attr) in definitions.items():
        path = lib_dir / f"{name}.kicad_mod"
        path.write_text(_footprint_sexpr(name, description, pads, side, attr), encoding="utf-8")
        written.append(path)
    return written

