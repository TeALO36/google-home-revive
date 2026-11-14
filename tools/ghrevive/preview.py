"""Placement checks and a quick PNG preview of a board (pads, courtyards, tracks, outline)."""
from __future__ import annotations

import math
from pathlib import Path

import pcbnew
from PIL import Image, ImageDraw, ImageFont

SCALE = 14.0  # pixels per millimetre
LAYER_COLOURS = {"F.Cu": (200, 40, 40), "In1.Cu": (60, 160, 60), "In2.Cu": (200, 150, 30), "B.Cu": (50, 80, 220)}


def courtyard_overlaps(board: pcbnew.BOARD) -> list[tuple[str, str]]:
    """Pairs of footprints whose courtyards intersect on the same side."""
    overlaps: list[tuple[str, str]] = []
    for layer in (pcbnew.F_CrtYd, pcbnew.B_CrtYd):
        shapes = []
        for footprint in board.GetFootprints():
            poly = footprint.GetCourtyard(layer)
            if poly.OutlineCount() > 0:
                shapes.append((footprint.GetReference(), pcbnew.SHAPE_POLY_SET(poly)))
        for i, (ref_a, poly_a) in enumerate(shapes):
            for ref_b, poly_b in shapes[i + 1:]:
                if not poly_a.BBox().Intersects(poly_b.BBox()):
                    continue
                common = pcbnew.SHAPE_POLY_SET(poly_a)
                common.BooleanIntersection(poly_b)
                if common.OutlineCount() > 0 and common.Area() > 1e6:  # > 0.001 mm2 (areas are in nm2)
                    overlaps.append((ref_a, ref_b))
    return overlaps


class _Canvas:
    def __init__(self, board: pcbnew.BOARD, margin: float = 3.0) -> None:
        box = board.GetBoardEdgesBoundingBox()
        self.x0 = pcbnew.ToMM(box.GetLeft()) - margin
        self.y0 = pcbnew.ToMM(box.GetTop()) - margin
        width = int((pcbnew.ToMM(box.GetWidth()) + 2 * margin) * SCALE)
        height = int((pcbnew.ToMM(box.GetHeight()) + 2 * margin) * SCALE)
        self.image = Image.new("RGB", (width, height), (18, 22, 28))
        self.draw = ImageDraw.Draw(self.image, "RGBA")

    def px(self, point: pcbnew.VECTOR2I) -> tuple[float, float]:
        return ((pcbnew.ToMM(point.x) - self.x0) * SCALE, (pcbnew.ToMM(point.y) - self.y0) * SCALE)

    def polygon(self, poly: pcbnew.SHAPE_POLY_SET, fill: tuple[int, ...] | None, outline: tuple[int, ...] | None) -> None:
        for index in range(poly.OutlineCount()):
            chain = poly.Outline(index)
            points = [self.px(chain.CPoint(i)) for i in range(chain.PointCount())]
            if len(points) >= 3:
                self.draw.polygon(points, fill=fill, outline=outline)


def _draw_footprint(canvas: _Canvas, footprint: pcbnew.FOOTPRINT, show_back: bool) -> None:
    back = footprint.GetLayer() == pcbnew.B_Cu
    if back != show_back:
        return
    yard = footprint.GetCourtyard(pcbnew.B_CrtYd if back else pcbnew.F_CrtYd)
    canvas.polygon(yard, None, (120, 120, 255, 255) if back else (230, 230, 230, 255))
    for pad in footprint.Pads():
        poly = pcbnew.SHAPE_POLY_SET()
        layer = pcbnew.B_Cu if pad.IsOnLayer(pcbnew.B_Cu) and not pad.IsOnLayer(pcbnew.F_Cu) else pcbnew.F_Cu
        pad.TransformShapeToPolygon(poly, layer, 0, pcbnew.FromMM(0.02), pcbnew.ERROR_INSIDE)
        colour = (90, 120, 255, 230) if layer == pcbnew.B_Cu else (235, 180, 60, 230)
        canvas.polygon(poly, colour, None)
    x, y = canvas.px(footprint.GetPosition())
    canvas.draw.text((x - 8, y - 5), footprint.GetReference(), fill=(120, 255, 160, 255))


def _draw_tracks(canvas: _Canvas, board: pcbnew.BOARD) -> None:
    for track in board.GetTracks():
        if track.Type() == pcbnew.PCB_VIA_T:
            x, y = canvas.px(track.GetPosition())
            radius = pcbnew.ToMM(track.GetWidth(pcbnew.F_Cu)) * SCALE / 2
            canvas.draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=(210, 210, 210, 255))
            continue
        colour = LAYER_COLOURS.get(board.GetLayerName(track.GetLayer()), (150, 150, 150))
        width = max(1, int(pcbnew.ToMM(track.GetWidth()) * SCALE))
        canvas.draw.line([canvas.px(track.GetStart()), canvas.px(track.GetEnd())], fill=colour + (220,), width=width)


def _edge_points(shape: pcbnew.PCB_SHAPE) -> list[pcbnew.VECTOR2I]:
    """Polyline of an outline shape; arcs are sampled every ~2 degrees."""
    if shape.GetShape() != pcbnew.SHAPE_T_ARC:
        return [shape.GetStart(), shape.GetEnd()]
    centre = shape.GetCenter()
    radius = shape.GetRadius()
    start = math.atan2(shape.GetStart().y - centre.y, shape.GetStart().x - centre.x)
    sweep = math.radians(shape.GetArcAngle().AsDegrees())
    steps = max(2, int(abs(math.degrees(sweep)) / 2))
    return [pcbnew.VECTOR2I(int(centre.x + radius * math.cos(start + sweep * i / steps)),
                            int(centre.y + radius * math.sin(start + sweep * i / steps))) for i in range(steps + 1)]


HAND_FILL, FACTORY_FILL, PAPER, INK = (240, 140, 30, 255), (175, 180, 186, 255), (250, 249, 246), (30, 30, 30, 255)


def _footprint_polygons(footprint: pcbnew.FOOTPRINT, back: bool) -> list[pcbnew.SHAPE_POLY_SET]:
    yard = footprint.GetCourtyard(pcbnew.B_CrtYd if back else pcbnew.F_CrtYd)
    if yard.OutlineCount() > 0:
        return [yard]
    pads = []
    for pad in footprint.Pads():
        poly = pcbnew.SHAPE_POLY_SET()
        pad.TransformShapeToPolygon(poly, pcbnew.B_Cu if back else pcbnew.F_Cu, 0, pcbnew.FromMM(0.02), pcbnew.ERROR_INSIDE)
        pads.append(poly)
    return pads


def render_hand_map(board: pcbnew.BOARD, path: Path, parts: list[tuple[pcbnew.FOOTPRINT, bool]],
                    show_back: bool = False) -> None:
    """Soldering map of one face: parts to solder by hand in orange with their reference, factory parts in grey.

    `parts` = (footprint, soldered by hand) of every bought part; only those of the drawn face are used.
    The back face is mirrored, as seen when the board is turned over.
    """
    canvas = _Canvas(board)
    canvas.image.paste(PAPER, (0, 0, canvas.image.width, canvas.image.height))
    for drawing in board.GetDrawings():
        if drawing.GetLayer() == pcbnew.Edge_Cuts and drawing.Type() == pcbnew.PCB_SHAPE_T:
            canvas.draw.line([canvas.px(p) for p in _edge_points(drawing)], fill=INK, width=3)
    side = pcbnew.B_Cu if show_back else pcbnew.F_Cu
    parts = [(footprint, hand) for footprint, hand in parts if footprint.GetLayer() == side]
    for footprint, hand in parts:
        for poly in _footprint_polygons(footprint, show_back):
            canvas.polygon(poly, HAND_FILL if hand else FACTORY_FILL, INK if hand else None)
    image = canvas.image.transpose(Image.Transpose.FLIP_LEFT_RIGHT) if show_back else canvas.image
    draw, font = ImageDraw.Draw(image, "RGBA"), ImageFont.load_default(size=22)
    for footprint, hand in parts:
        if hand:
            x, y = canvas.px(footprint.GetPosition())
            draw.text((image.width - x if show_back else x, y), footprint.GetReference(), fill=INK, font=font,
                      anchor="mm", stroke_width=3, stroke_fill=PAPER)
    image.save(str(path))


def render_preview(board: pcbnew.BOARD, path: Path, show_back: bool = False) -> None:
    canvas = _Canvas(board)
    _draw_tracks(canvas, board)
    for drawing in board.GetDrawings():
        if drawing.GetLayer() == pcbnew.Edge_Cuts and drawing.Type() == pcbnew.PCB_SHAPE_T:
            points = [canvas.px(p) for p in _edge_points(drawing)]
            canvas.draw.line(points, fill=(255, 255, 0, 255), width=2)
    side_layer = pcbnew.B_Cu if show_back else pcbnew.F_Cu
    for zone in board.Zones():
        if zone.GetIsRuleArea():
            canvas.polygon(zone.Outline(), (255, 0, 255, 25), (255, 0, 255, 160))
        elif zone.IsOnLayer(side_layer) and zone.IsFilled():
            outline = (60, 200, 200, 200) if zone.GetNetname() != "GND" else (90, 90, 90, 160)
            canvas.polygon(zone.GetFilledPolysList(side_layer), None, outline)
    for footprint in board.GetFootprints():
        _draw_footprint(canvas, footprint, show_back)
    canvas.image.save(str(path))
