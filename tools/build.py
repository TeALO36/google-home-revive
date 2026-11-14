"""Regenerate the GH-Revive boards.

Run with KiCad's Python:
    "C:/Program Files/KiCad/10.0/bin/python.exe" tools/build.py [main|top|all] [--stage place|route|fab]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ghrevive import footprints, mainboard, pcb, preview  # noqa: E402
from ghrevive.model import BoardSpec  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
BOARD_DIRS = {"gh_mainboard": REPO / "hardware" / "mainboard", "gh_topboard": REPO / "hardware" / "topboard"}


def _specs(which: str) -> list[BoardSpec]:
    specs: list[BoardSpec] = []
    if which in ("main", "all"):
        specs.append(mainboard.build_spec())
    if which in ("top", "all"):
        from ghrevive import topboard
        specs.append(topboard.build_spec())
    return specs


def _place(spec: BoardSpec) -> Path:
    board_path = BOARD_DIRS[spec.name] / f"{spec.name}.kicad_pcb"
    board, _nets = pcb.build_unrouted(spec, board_path)
    overlaps = preview.courtyard_overlaps(board)
    preview.render_preview(board, board_path.with_name(f"{spec.name}_placement.png"))
    print(f"[{spec.name}] {len(board.GetFootprints())} footprints, {board.GetNetCount()} nets")
    print(f"[{spec.name}] courtyard overlaps: {overlaps if overlaps else 'none'}")
    return board_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("which", nargs="?", default="all", choices=("main", "top", "all"))
    parser.add_argument("--stage", default="fab", choices=("place", "route", "fab"))
    parser.add_argument("--reuse-routing", action="store_true",
                        help="import the existing FreeRouting session (.ses) instead of routing again")
    args = parser.parse_args()
    footprints.write_project_footprints(pcb.PROJECT_LIB)
    for spec in _specs(args.which):
        board_path = _place(spec)
        if args.stage == "place":
            continue
        from ghrevive import routing
        routing.route_board(spec, board_path, reuse=args.reuse_routing)
        if args.stage == "fab":
            from ghrevive import fab
            fab.export_all(spec, board_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
