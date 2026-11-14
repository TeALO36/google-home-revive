"""JLCPCB fabrication outputs: zipped Gerbers + Excellon drills, BOM and CPL (pick & place) in JLC's column format."""
from __future__ import annotations

import csv
import re
import shutil
import subprocess
import zipfile
from collections import defaultdict
from pathlib import Path
from typing import Callable

import pcbnew

from . import preview
from .model import BoardSpec
from .pcb import ASSEMBLY_FIELD
from .routing import KICAD_CLI

HAND_MAP_DIR = Path(__file__).resolve().parents[2] / "docs" / "img"

COMMON_LAYERS = ("F.Cu", "B.Cu", "F.Paste", "B.Paste", "F.SilkS", "B.SilkS", "F.Mask", "B.Mask", "Edge.Cuts")
INNER_LAYERS = ("In1.Cu", "In2.Cu")


def _cli(*args: str) -> None:
    result = subprocess.run([str(KICAD_CLI), *args], capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"kicad-cli {' '.join(args[:3])} failed ({result.returncode}): {result.stderr or result.stdout}")


def _layers(spec: BoardSpec) -> str:
    layers = list(COMMON_LAYERS)
    if spec.layers == 4:
        layers[1:1] = INNER_LAYERS
    return ",".join(layers)


def export_gerbers(spec: BoardSpec, board_path: Path, fab_dir: Path) -> Path:
    plot_dir = fab_dir / "gerbers"
    if plot_dir.exists():
        shutil.rmtree(plot_dir)
    plot_dir.mkdir(parents=True)
    _cli("pcb", "export", "gerbers", "--output", str(plot_dir) + "/", "--layers", _layers(spec),
         "--subtract-soldermask", "--check-zones", str(board_path))
    _cli("pcb", "export", "drill", "--output", str(plot_dir) + "/", "--format", "excellon", "--excellon-units", "mm",
         "--excellon-separate-th", "--generate-map", "--map-format", "gerberx2", str(board_path))
    archive = fab_dir / f"{spec.name}_gerbers.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
        for item in sorted(plot_dir.iterdir()):
            bundle.write(item, item.name)
    return archive


def _populated(board: pcbnew.BOARD, hand: bool) -> list[pcbnew.FOOTPRINT]:
    """Bought parts soldered by JLCPCB (hand=False) or by the user (hand=True)."""
    parts = [fp for fp in board.GetFootprints()
             if not fp.IsDNP() and not fp.IsExcludedFromPosFiles() and fp.HasField("LCSC")
             and (fp.GetFieldText(ASSEMBLY_FIELD) == "hand") == hand]
    return sorted(parts, key=lambda fp: fp.GetReference())


def export_bom(parts: list[pcbnew.FOOTPRINT], path: Path) -> int:
    groups: dict[tuple[str, str, str], list[str]] = defaultdict(list)
    for fp in parts:
        key = (fp.GetValue(), str(fp.GetFPID().GetLibItemName()), fp.GetFieldText("LCSC"))
        groups[key].append(fp.GetReference())
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["Comment", "Designator", "Footprint", "LCSC Part #"])
        for (value, footprint, lcsc), refs in sorted(groups.items(), key=lambda item: item[1][0]):
            writer.writerow([value, ",".join(refs), footprint, lcsc])
    return len(groups)


# KiCad draws these packages with the pin rows vertical and pin 1 top-left; the JLCPCB models lie horizontal with pin 1
# bottom-left (seen on the JLC placement check, SOT-23-6, 2026-11-14): their rotation needs a quarter turn clockwise.
JLC_ROTATION_FIXES: tuple[tuple[re.Pattern[str], float], ...] = (
    (re.compile(r"^(SOT-23|TSOT-23|TSSOP-|HTSSOP-|MSOP-|SOIC-)"), 270.0),
)


def jlc_rotation(fp: pcbnew.FOOTPRINT) -> float:
    """Rotation for the JLCPCB CPL: KiCad orientation plus the package correction (mirrored on the back face)."""
    name = str(fp.GetFPID().GetLibItemName())
    fix = next((angle for pattern, angle in JLC_ROTATION_FIXES if pattern.match(name)), 0.0)
    bottom = fp.GetLayer() == pcbnew.B_Cu
    return (fp.GetOrientationDegrees() + (-fix if bottom else fix)) % 360


def export_cpl(parts: list[pcbnew.FOOTPRINT], path: Path) -> int:
    """Centroids in KiCad page coordinates with Y up (same frame as the Gerbers, as JLC expects)."""
    rows = []
    for fp in parts:
        position = fp.GetPosition()
        bottom = fp.GetLayer() == pcbnew.B_Cu
        rows.append([fp.GetReference(), f"{pcbnew.ToMM(position.x):.4f}mm", f"{-pcbnew.ToMM(position.y):.4f}mm",
                     "Bottom" if bottom else "Top", f"{jlc_rotation(fp):.1f}"])
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["Designator", "Mid X", "Mid Y", "Layer", "Rotation"])
        writer.writerows(rows)
    return len(rows)


Exporter = Callable[[list[pcbnew.FOOTPRINT], Path], int]


def _write_or_remove(parts: list[pcbnew.FOOTPRINT], path: Path, writer: Exporter) -> int:
    if parts:
        return writer(parts, path)
    path.unlink(missing_ok=True)  # no stale file from an earlier assembly split
    return 0


def export_all(spec: BoardSpec, board_path: Path) -> dict[str, Path]:
    """Gerbers; JLCPCB BOM + CPL for the factory-soldered parts; LCSC shopping list for the hand-soldered ones."""
    fab_dir = board_path.parent / "fab"
    fab_dir.mkdir(exist_ok=True)
    archive = export_gerbers(spec, board_path, fab_dir)
    board = pcbnew.LoadBoard(str(board_path))
    factory, hand = _populated(board, hand=False), _populated(board, hand=True)
    paths = {"gerbers": archive, "bom": fab_dir / f"{spec.name}_bom.csv", "cpl": fab_dir / f"{spec.name}_cpl.csv",
             "hand_bom": fab_dir / f"{spec.name}_hand_bom.csv"}
    lines = _write_or_remove(factory, paths["bom"], export_bom)
    placed = _write_or_remove(factory, paths["cpl"], export_cpl)
    hand_lines = _write_or_remove(hand, paths["hand_bom"], export_bom)
    print(f"[{spec.name}] fab: {archive.name}, JLC BOM {lines} lines / CPL {placed} parts, "
          f"hand-soldered list {hand_lines} lines ({len(hand)} parts)")
    paths.update(export_hand_maps(spec, board, factory, hand))
    return paths


def export_hand_maps(spec: BoardSpec, board: pcbnew.BOARD, factory: list[pcbnew.FOOTPRINT],
                     hand: list[pcbnew.FOOTPRINT]) -> dict[str, Path]:
    """docs/img/<board>_hand_<face>.png for each face that has parts to solder by hand."""
    HAND_MAP_DIR.mkdir(parents=True, exist_ok=True)
    parts = [(fp, False) for fp in factory] + [(fp, True) for fp in hand]
    written: dict[str, Path] = {}
    for face, back in (("top", False), ("bottom", True)):
        side = pcbnew.B_Cu if back else pcbnew.F_Cu
        path = HAND_MAP_DIR / f"{spec.name}_hand_{face}.png"
        if any(fp.GetLayer() == side for fp in hand):
            preview.render_hand_map(board, path, parts, show_back=back)
            written[f"hand_map_{face}"] = path
        elif path.exists():
            path.unlink()
    return written
