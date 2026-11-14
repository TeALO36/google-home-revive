"""Autoroute a placed board with FreeRouting (Specctra DSN/SES round trip), add the copper pours and run the DRC."""
from __future__ import annotations

import itertools
import json
import math
import os
import re
import subprocess
from collections import Counter
from pathlib import Path

import pcbnew

from . import fanout, pcb, preview
from .model import BoardSpec

FREEROUTING = Path(os.environ.get("FREEROUTING_EXE", Path.home() / "AppData/Local/freerouting/freerouting.exe"))
KICAD_CLI = Path(os.environ.get("KICAD_CLI", "C:/Program Files/KiCad/10.0/bin/kicad-cli.exe"))
MAX_PASSES = 100
ROUTER_TIMEOUT_S = 1800
CLEARANCE_MARGIN_UM = 2.0
# FreeRouting results vary from run to run: strategies are cycled until nothing is left or MAX_RETRIES is reached
RETRY_STRATEGIES = (("-is", "random"), ("-us", "hybrid", "-hr", "1:1"), ("-is", "prioritized"))
MAX_RETRIES = 9


def _mark_plane_layers(dsn: Path, spec: BoardSpec) -> None:
    """Copper layers that are not signal layers become Specctra power layers: FreeRouting will not route on them."""
    text = dsn.read_text(encoding="utf-8")
    for layer in ("F.Cu", "In1.Cu", "In2.Cu", "B.Cu"):
        if layer in spec.signal_layers:
            continue
        pattern = re.compile(rf"(\(layer {re.escape(layer)}\s*\(type )signal\)")
        text = pattern.sub(r"\1power)", text)
    # FreeRouting rounds to the micron and can land 1-2 um under the rule: route with a small margin
    text = re.sub(r"\(clearance ([\d.]+)\)",
                  lambda m: f"(clearance {float(m.group(1)) + CLEARANCE_MARGIN_UM:g})", text)
    dsn.write_text(text, encoding="utf-8")


def _run_freerouting(dsn: Path, ses: Path, extra: tuple[str, ...] = ()) -> None:
    if not FREEROUTING.exists():
        raise FileNotFoundError(f"FreeRouting not found at {FREEROUTING} (set FREEROUTING_EXE)")
    if ses.exists():
        ses.unlink()
    command = [str(FREEROUTING), "-de", str(dsn), "-do", str(ses), "-mp", str(MAX_PASSES), *extra]
    result = subprocess.run(command, capture_output=True, text=True, timeout=ROUTER_TIMEOUT_S, check=False)
    if not ses.exists():
        raise RuntimeError(f"FreeRouting produced no session file (exit {result.returncode}):\n{result.stdout[-3000:]}"
                           f"\n{result.stderr[-3000:]}")


def _add_pours(board: pcbnew.BOARD, spec: BoardSpec) -> None:
    nets = pcb.NetTable(board)
    for zone_spec in spec.post_zones:
        pcb.add_copper_zone(board, spec, zone_spec, nets, allow_hatch=False)
    pcb.fill_zones(board)


def _apply_hatch(board: pcbnew.BOARD, spec: BoardSpec) -> None:
    """Hatching is applied last: stitching vias are placed on the solid fills, where clearance is guaranteed."""
    hatched = {z.name for z in spec.plane_zones + spec.post_zones if z.hatched}
    for zone in board.Zones():
        if zone.GetZoneName() in hatched:
            pcb.set_hatch(zone)
    pcb.fill_zones(board)


def _via_forbidden(board: pcbnew.BOARD, point: pcbnew.VECTOR2I) -> bool:
    return any(zone.GetIsRuleArea() and zone.GetDoNotAllowVias() and zone.Outline().Contains(point)
               for zone in board.Zones())


def _fits_everywhere(fills: list[pcbnew.SHAPE_POLY_SET], point: pcbnew.VECTOR2I, radius: int) -> bool:
    probes = [point] + [pcbnew.VECTOR2I(int(point.x + radius * math.cos(a * math.pi / 4)),
                                        int(point.y + radius * math.sin(a * math.pi / 4))) for a in range(8)]
    return all(fill.Contains(probe) for fill in fills for probe in probes)


class _Stitcher:
    """Places GND through vias only where every GND pour layer has copper around the via (clearance kept)."""

    VIA_DIA, VIA_DRILL, PROBE, MIN_SPACING = 0.6, 0.3, 0.35, 1.0  # fills already keep the zone clearance

    def __init__(self, board: pcbnew.BOARD) -> None:
        self.board = board
        self.zones = [z for z in board.Zones() if not z.GetIsRuleArea() and z.GetNetname() == "GND"]
        self.fills = [z.GetFilledPolysList(z.GetLayer()) for z in self.zones]
        self.net = board.FindNet("GND")
        self.anchors = [t.GetPosition() for t in board.GetTracks()
                        if t.Type() == pcbnew.PCB_VIA_T and t.GetNetname() == "GND"]
        self.anchors += [pad.GetPosition() for pad in board.GetPads()
                         if pad.GetNetname() == "GND" and pad.GetAttribute() == pcbnew.PAD_ATTRIB_PTH]
        self.added = 0

    def usable(self) -> bool:
        # every copper layer must carry a GND pour, otherwise a through via could hit a track there
        return len({z.GetLayer() for z in self.zones}) == self.board.GetCopperLayerCount()

    def try_add(self, point: pcbnew.VECTOR2I) -> bool:
        spacing = pcb.mm(self.MIN_SPACING)
        if any(abs(a.x - point.x) < spacing and abs(a.y - point.y) < spacing for a in self.anchors):
            return False
        if _via_forbidden(self.board, point) or not _fits_everywhere(self.fills, point, pcb.mm(self.PROBE)):
            return False
        via = pcbnew.PCB_VIA(self.board)
        via.SetViaType(pcbnew.VIATYPE_THROUGH)
        via.SetPosition(point)
        via.SetWidth(pcb.mm(self.VIA_DIA))
        via.SetDrill(pcb.mm(self.VIA_DRILL))
        via.SetNet(self.net)
        self.board.Add(via)
        self.anchors.append(point)
        self.added += 1
        return True

    def grid(self, pitch_mm: float) -> None:
        box = self.board.GetBoardEdgesBoundingBox()
        step = pcb.mm(pitch_mm)
        for x in range(box.GetLeft() + step // 2, box.GetRight(), step):
            for y in range(box.GetTop() + step // 2, box.GetBottom(), step):
                self.try_add(pcbnew.VECTOR2I(x, y))

    def islands(self, pitch_mm: float = 0.4) -> None:
        """One via inside every pour fragment that holds no GND via / plated GND hole yet."""
        step = pcb.mm(pitch_mm)
        for fill in self.fills:
            for index in range(fill.OutlineCount()):
                fragment = pcbnew.SHAPE_POLY_SET()
                fragment.AddOutline(fill.Outline(index))
                if any(fragment.Contains(a) for a in self.anchors):
                    continue
                box = fragment.BBox()
                points = (pcbnew.VECTOR2I(x, y) for x in range(box.GetLeft(), box.GetRight(), step)
                          for y in range(box.GetTop(), box.GetBottom(), step))
                next((p for p in points if fragment.Contains(p) and self.try_add(p)), None)


def stitch_ground(board: pcbnew.BOARD, pitch_mm: float = 3.0) -> int:
    """Grid of GND stitching vias, then one via per isolated pour fragment."""
    stitcher = _Stitcher(board)
    if not stitcher.usable():
        return 0
    stitcher.grid(pitch_mm)
    stitcher.islands()
    pcb.fill_zones(board)
    return stitcher.added


def run_drc(board_path: Path) -> dict[str, int]:
    """Run KiCad's DRC; returns violation counts by type (plus 'unconnected')."""
    report = board_path.with_name(f"{board_path.stem}_drc.json")
    command = [str(KICAD_CLI), "pcb", "drc", "--format", "json", "--severity-error", "--output", str(report),
               str(board_path)]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if not report.exists():
        raise RuntimeError(f"kicad-cli drc failed (exit {result.returncode}): {result.stderr}")
    data = json.loads(report.read_text(encoding="utf-8"))
    counts = Counter(str(item.get("type", "unknown")) for item in data.get("violations", []))
    counts["unconnected"] = len(data.get("unconnected_items", []))
    return dict(counts)


def _sanitize_ses(ses: Path) -> None:
    """KiCad refuses a session whose component image name is empty (footprints without a library id)."""
    text = ses.read_text(encoding="utf-8")
    fixed = re.sub(r"\(component\s*\n", '(component "MountingHole"\n', text)
    if fixed != text:
        ses.write_text(fixed, encoding="utf-8")


def _unrouted(board: pcbnew.BOARD) -> int:
    board.BuildConnectivity()
    return board.GetConnectivity().GetUnconnectedCount(True)


def _route_pass(board: pcbnew.BOARD, spec: BoardSpec, paths: tuple[Path, Path], extra: tuple[str, ...],
                run: bool) -> int:
    """Export the board (with any wiring already on it), route, import; returns the unrouted connection count."""
    dsn, ses = paths
    if not pcbnew.ExportSpecctraDSN(board, str(dsn)):
        raise RuntimeError(f"DSN export failed for {dsn}")
    _mark_plane_layers(dsn, spec)
    if run:
        _run_freerouting(dsn, ses, extra)
    _sanitize_ses(ses)
    if not pcbnew.ImportSpecctraSES(board, str(ses)):
        raise RuntimeError(f"SES import failed for {ses}")
    return _unrouted(board)


def route_board(spec: BoardSpec, board_path: Path, reuse: bool = False) -> dict[str, int]:
    """Autoroute; with reuse=True an existing .ses (same placement) is imported instead of routing again.

    When FreeRouting stalls with connections left, the partly routed board goes back to it with another
    item-selection strategy (it keeps the existing wiring and works on what is missing).
    """
    paths = (board_path.with_suffix(".dsn"), board_path.with_suffix(".ses"))
    board = pcbnew.LoadBoard(str(board_path))
    if any(z.net == "GND" for z in spec.plane_zones):
        added, failed = fanout.fanout(board, "GND")
        print(f"[{spec.name}] GND fan-out: {added} vias; no room for {failed if failed else 'none'}")
    left = _route_pass(board, spec, paths, (), not (reuse and paths[1].exists()))
    for extra in itertools.islice(itertools.cycle(RETRY_STRATEGIES), MAX_RETRIES):
        if left == 0:
            break
        print(f"[{spec.name}] {left} connections left, rerouting with {' '.join(extra)}")
        left = _route_pass(board, spec, paths, extra, True)
    _add_pours(board, spec)
    stitched = stitch_ground(board)
    _apply_hatch(board, spec)
    pcbnew.SaveBoard(str(board_path), board)
    print(f"[{spec.name}] {stitched} GND stitching vias")
    preview.render_preview(board, board_path.with_name(f"{spec.name}_routed_top.png"))
    preview.render_preview(board, board_path.with_name(f"{spec.name}_routed_bottom.png"), show_back=True)
    counts = run_drc(board_path)
    print(f"[{spec.name}] routed: {len(board.GetTracks())} track items; DRC errors: {counts}")
    return counts
