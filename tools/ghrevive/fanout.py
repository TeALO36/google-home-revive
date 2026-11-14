"""Ground fan-out before autorouting: a short stub + through via from every SMD GND pad down to the GND plane.

FreeRouting never routes a net that owns a plane, so without this step SMD ground pads would rely on copper pours
alone and could end up isolated.
"""
from __future__ import annotations

import math

import pcbnew

from . import pcb

VIA_DIA, VIA_DRILL, STUB_WIDTH = 0.6, 0.3, 0.25
STUB_CLEARANCE = 0.15  # board minimum; lets a stub leave a 0.4 mm pitch QFN pad
CLEARANCE, EDGE_CLEARANCE = 0.2, 0.35
DISTANCES = (0.75, 0.95, 1.2, 1.5, 1.9)
DIRECTIONS = 16


class _Obstacles:
    """Copper of other nets, holes, board edge and via keep-outs, for collision tests."""

    def __init__(self, board: pcbnew.BOARD, net: str) -> None:
        self.board = board
        self.pads = [p for p in board.GetPads() if p.GetNetname() != net]
        self.holes = [p for p in board.GetPads() if p.HasHole()]
        self.vias: list[pcbnew.VECTOR2I] = []
        self.outline = pcbnew.SHAPE_POLY_SET()
        board.GetBoardPolygonOutlines(self.outline, True)
        self.keepouts = [z.Outline() for z in board.Zones() if z.GetIsRuleArea() and z.GetDoNotAllowVias()]

    def via_ok(self, point: pcbnew.VECTOR2I) -> bool:
        radius = pcb.mm(VIA_DIA / 2)
        circle = pcbnew.SHAPE_CIRCLE(point, radius)
        if any(k.Contains(point) for k in self.keepouts) or not self._inside(point, radius + pcb.mm(EDGE_CLEARANCE)):
            return False
        if any(math.hypot(v.x - point.x, v.y - point.y) < pcb.mm(VIA_DIA + CLEARANCE) for v in self.vias):
            return False
        for pad in self.pads:
            for layer in (pcbnew.F_Cu, pcbnew.B_Cu):
                if pad.IsOnLayer(layer) and pad.GetEffectiveShape(layer).Collide(circle, pcb.mm(CLEARANCE)):
                    return False
        drill = pcbnew.SHAPE_CIRCLE(point, pcb.mm(VIA_DRILL / 2))
        return not any(h.GetEffectiveHoleShape().Collide(drill, pcb.mm(0.25)) for h in self.holes)

    def stub_ok(self, start: pcbnew.VECTOR2I, end: pcbnew.VECTOR2I, layer: int) -> bool:
        segment = pcbnew.SHAPE_SEGMENT(start, end, pcb.mm(STUB_WIDTH))
        return not any(p.IsOnLayer(layer) and p.GetEffectiveShape(layer).Collide(segment, pcb.mm(STUB_CLEARANCE))
                       for p in self.pads)

    def _inside(self, point: pcbnew.VECTOR2I, radius: int) -> bool:
        probes = [pcbnew.VECTOR2I(int(point.x + radius * math.cos(a * math.pi / 4)),
                                  int(point.y + radius * math.sin(a * math.pi / 4))) for a in range(8)]
        return all(self.outline.Contains(p) for p in [point] + probes)


def _candidates(centre: pcbnew.VECTOR2I) -> list[pcbnew.VECTOR2I]:
    points = []
    for distance in DISTANCES:
        for k in range(DIRECTIONS):
            angle = 2 * math.pi * k / DIRECTIONS
            points.append(pcbnew.VECTOR2I(int(centre.x + pcb.mm(distance) * math.cos(angle)),
                                          int(centre.y + pcb.mm(distance) * math.sin(angle))))
    return points


def _add_stub_and_via(board: pcbnew.BOARD, pad: pcbnew.PAD, point: pcbnew.VECTOR2I, layer: int) -> None:
    track = pcbnew.PCB_TRACK(board)
    track.SetStart(pad.GetPosition())
    track.SetEnd(point)
    track.SetWidth(pcb.mm(STUB_WIDTH))
    track.SetLayer(layer)
    track.SetNet(pad.GetNet())
    board.Add(track)
    via = pcbnew.PCB_VIA(board)
    via.SetViaType(pcbnew.VIATYPE_THROUGH)
    via.SetPosition(point)
    via.SetWidth(pcb.mm(VIA_DIA))
    via.SetDrill(pcb.mm(VIA_DRILL))
    via.SetNet(pad.GetNet())
    board.Add(via)


def fanout(board: pcbnew.BOARD, net: str = "GND") -> tuple[int, list[str]]:
    """Returns (vias added, pads that found no room)."""
    obstacles = _Obstacles(board, net)
    added, failed = 0, []
    for pad in board.GetPads():
        if pad.GetNetname() != net or pad.HasHole():
            continue
        layer = pcbnew.B_Cu if pad.IsOnLayer(pcbnew.B_Cu) else pcbnew.F_Cu
        spot = next((p for p in _candidates(pad.GetPosition())
                     if obstacles.via_ok(p) and obstacles.stub_ok(pad.GetPosition(), p, layer)), None)
        if spot is None:
            failed.append(f"{pad.GetParentFootprint().GetReference()}:{pad.GetNumber()}")
            continue
        _add_stub_and_via(board, pad, spot, layer)
        obstacles.vias.append(spot)
        added += 1
    return added, failed
