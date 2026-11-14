"""JLCPCB fabrication outputs: zipped Gerbers + Excellon drills, BOM and CPL (pick & place) in JLC's column format."""
from __future__ import annotations

import csv
import shutil
import subprocess
import zipfile
from collections import defaultdict
from pathlib import Path

import pcbnew

from .model import BoardSpec
from .routing import KICAD_CLI

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


def _assembled(board: pcbnew.BOARD) -> list[pcbnew.FOOTPRINT]:
    parts = [fp for fp in board.GetFootprints()
             if not fp.IsDNP() and not fp.IsExcludedFromPosFiles() and fp.HasField("LCSC")]
    return sorted(parts, key=lambda fp: fp.GetReference())


def export_bom(board: pcbnew.BOARD, path: Path) -> int:
    groups: dict[tuple[str, str, str], list[str]] = defaultdict(list)
    for fp in _assembled(board):
        key = (fp.GetValue(), str(fp.GetFPID().GetLibItemName()), fp.GetFieldText("LCSC"))
        groups[key].append(fp.GetReference())
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["Comment", "Designator", "Footprint", "LCSC Part #"])
        for (value, footprint, lcsc), refs in sorted(groups.items(), key=lambda item: item[1][0]):
            writer.writerow([value, ",".join(refs), footprint, lcsc])
    return len(groups)


def export_cpl(board: pcbnew.BOARD, path: Path) -> int:
    """Centroids in KiCad page coordinates with Y up (same frame as the Gerbers, as JLC expects)."""
    rows = []
    for fp in _assembled(board):
        position = fp.GetPosition()
        bottom = fp.GetLayer() == pcbnew.B_Cu
        rows.append([fp.GetReference(), f"{pcbnew.ToMM(position.x):.4f}mm", f"{-pcbnew.ToMM(position.y):.4f}mm",
                     "Bottom" if bottom else "Top", f"{fp.GetOrientationDegrees() % 360:.1f}"])
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["Designator", "Mid X", "Mid Y", "Layer", "Rotation"])
        writer.writerows(rows)
    return len(rows)


def export_all(spec: BoardSpec, board_path: Path) -> dict[str, Path]:
    fab_dir = board_path.parent / "fab"
    fab_dir.mkdir(exist_ok=True)
    archive = export_gerbers(spec, board_path, fab_dir)
    board = pcbnew.LoadBoard(str(board_path))
    bom = fab_dir / f"{spec.name}_bom.csv"
    cpl = fab_dir / f"{spec.name}_cpl.csv"
    lines = export_bom(board, bom)
    placed = export_cpl(board, cpl)
    print(f"[{spec.name}] fab: {archive.name}, BOM {lines} lines, CPL {placed} parts")
    return {"gerbers": archive, "bom": bom, "cpl": cpl}
