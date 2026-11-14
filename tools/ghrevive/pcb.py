"""Build a KiCad board from a BoardSpec. Runs under KiCad's bundled Python (pcbnew)."""
from __future__ import annotations

import os
from pathlib import Path

import pcbnew

from .model import Arc, BoardSpec, CopperZone, Hole, Keepout, Part, Point, SilkText

REPO = Path(__file__).resolve().parents[2]
PROJECT_LIB = REPO / "hardware" / "lib" / "gh_revive.pretty"
KICAD_FP_DIR = Path(os.environ.get("KICAD10_FOOTPRINT_DIR", "C:/Program Files/KiCad/10.0/share/kicad/footprints"))


def mm(value: float) -> int:
    return pcbnew.FromMM(value)


def to_page(spec: BoardSpec, x: float, y: float) -> pcbnew.VECTOR2I:
    return pcbnew.VECTOR2I(mm(spec.origin[0] + x), mm(spec.origin[1] + y))


LAYER_IDS = {
    "F.Cu": pcbnew.F_Cu, "In1.Cu": pcbnew.In1_Cu, "In2.Cu": pcbnew.In2_Cu, "B.Cu": pcbnew.B_Cu,
    "F.SilkS": pcbnew.F_SilkS, "B.SilkS": pcbnew.B_SilkS, "Edge.Cuts": pcbnew.Edge_Cuts,
    "F.Fab": pcbnew.F_Fab, "B.Fab": pcbnew.B_Fab, "Dwgs.User": pcbnew.Dwgs_User,
}


def layer_id(_board: pcbnew.BOARD, name: str) -> int:
    if name not in LAYER_IDS:
        raise ValueError(f"unknown layer {name}")
    return LAYER_IDS[name]


def load_footprint(board: pcbnew.BOARD, lib_name: str) -> pcbnew.FOOTPRINT:
    lib, name = lib_name.split(":", 1)
    lib_dir = PROJECT_LIB if lib == "gh_revive" else KICAD_FP_DIR / f"{lib}.pretty"
    footprint = pcbnew.FootprintLoad(str(lib_dir), name)
    if footprint is None:
        raise FileNotFoundError(f"footprint {lib_name} not found in {lib_dir}")
    footprint.SetFPID(pcbnew.LIB_ID(lib, name))
    return footprint


class NetTable:
    """Creates board nets on demand."""

    def __init__(self, board: pcbnew.BOARD) -> None:
        self._board = board
        self._nets: dict[str, pcbnew.NETINFO_ITEM] = {}

    def get(self, name: str) -> pcbnew.NETINFO_ITEM:
        if name not in self._nets:
            net = self._board.FindNet(name)
            if net is None:
                net = pcbnew.NETINFO_ITEM(self._board, name)
                self._board.Add(net)
            self._nets[name] = net
        return self._nets[name]

    def names(self) -> list[str]:
        return sorted(self._nets)


def create_board(spec: BoardSpec, path: Path) -> pcbnew.BOARD:
    path.parent.mkdir(parents=True, exist_ok=True)
    for stale in (path, path.with_suffix(".kicad_pro"), path.with_suffix(".kicad_prl")):
        if stale.exists():
            stale.unlink()
    board = pcbnew.NewBoard(str(path))
    board.SetCopperLayerCount(spec.layers)
    settings = board.GetDesignSettings()
    settings.SetBoardThickness(mm(1.6))
    settings.m_MinClearance = mm(0.15)
    settings.m_TrackMinWidth = mm(0.1)  # FreeRouting necks down to 0.1 mm at fine-pitch pads (JLC 4-layer min 0.09)
    settings.m_ViasMinSize = mm(0.45)
    settings.m_MinThroughDrill = mm(0.2)
    settings.m_ViasMinAnnularWidth = mm(0.1)
    settings.m_CopperEdgeClearance = mm(0.25)  # JLC: 0.2 mm min
    settings.m_HoleToHoleMin = mm(0.25)
    settings.m_HoleClearance = mm(0.2)
    return board


def apply_netclasses(board: pcbnew.BOARD, spec: BoardSpec) -> None:
    net_settings = board.GetDesignSettings().m_NetSettings
    for nc_spec in spec.netclasses:
        if nc_spec.name == "Default":
            netclass = net_settings.GetDefaultNetclass()
        else:
            netclass = pcbnew.NETCLASS(nc_spec.name)
            net_settings.SetNetclass(nc_spec.name, netclass)
        netclass.SetTrackWidth(mm(nc_spec.track))
        netclass.SetClearance(mm(nc_spec.clearance))
        netclass.SetViaDiameter(mm(nc_spec.via_dia))
        netclass.SetViaDrill(mm(nc_spec.via_drill))
        for pattern in nc_spec.patterns:
            net_settings.SetNetclassPatternAssignment(pattern, nc_spec.name)
    board.SynchronizeNetsAndNetClasses(True)


def add_outline(board: pcbnew.BOARD, spec: BoardSpec) -> None:
    edge = layer_id(board, "Edge.Cuts")
    loops: list[list[Point | Arc]] = [spec.outline] + [list(c) for c in spec.cutouts]
    for loop in loops:
        cursor = _loop_start(loop)
        for item in loop[1:] + [loop[0]]:
            shape = pcbnew.PCB_SHAPE(board)
            shape.SetLayer(edge)
            shape.SetWidth(mm(0.1))
            if isinstance(item, Arc):
                shape.SetShape(pcbnew.SHAPE_T_ARC)
                shape.SetArcGeometry(to_page(spec, *item.start), to_page(spec, *item.mid), to_page(spec, *item.end))
                cursor = item.end
            else:
                shape.SetShape(pcbnew.SHAPE_T_SEGMENT)
                shape.SetStart(to_page(spec, *cursor))
                shape.SetEnd(to_page(spec, *item))
                cursor = item
            board.Add(shape)


def _loop_start(loop: list[Point | Arc]) -> Point:
    first = loop[0]
    if isinstance(first, Arc):
        raise ValueError("an outline loop must start with a point")
    return first


def add_part(board: pcbnew.BOARD, spec: BoardSpec, part: Part, nets: NetTable) -> pcbnew.FOOTPRINT:
    footprint = load_footprint(board, part.footprint)
    footprint.SetReference(part.ref)
    footprint.SetValue(part.value)
    position = to_page(spec, part.x, part.y)
    footprint.SetPosition(position)
    footprint.SetLocalClearance(None)  # the autorouter ignores footprint overrides: board / netclass rules apply
    board.Add(footprint)  # Flip() needs the parent board
    if part.side == "B":
        footprint.Flip(position, pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
    footprint.SetOrientationDegrees(part.rot)
    if part.ref in spec.strip_footprint_keepouts:
        _strip_module_clearance(footprint)
    _assign_pad_nets(footprint, part, nets)
    _set_fields(footprint, part, part.hand)
    return footprint


def _strip_module_clearance(footprint: pcbnew.FOOTPRINT) -> None:
    """Drop a radio module's oversized antenna rule area / courtyard; keep a courtyard around its body.

    The board defines its own, tighter antenna keep-out (see BoardSpec.keepouts).
    """
    for zone in list(footprint.Zones()):
        footprint.Remove(zone)
    body = pcbnew.BOX2I()
    for item in list(footprint.GraphicalItems()):
        if item.GetLayer() == pcbnew.F_Fab and item.Type() == pcbnew.PCB_SHAPE_T:
            body.Merge(item.GetBoundingBox())
        if item.GetLayer() == pcbnew.F_CrtYd:
            footprint.Remove(item)
    for pad in footprint.Pads():
        body.Merge(pad.GetBoundingBox())
    body.Inflate(mm(0.25))
    courtyard = pcbnew.PCB_SHAPE(footprint)
    courtyard.SetShape(pcbnew.SHAPE_T_RECTANGLE)
    courtyard.SetLayer(pcbnew.F_CrtYd)
    courtyard.SetWidth(mm(0.05))
    courtyard.SetStart(pcbnew.VECTOR2I(body.GetLeft(), body.GetTop()))
    courtyard.SetEnd(pcbnew.VECTOR2I(body.GetRight(), body.GetBottom()))
    footprint.Add(courtyard)


def _assign_pad_nets(footprint: pcbnew.FOOTPRINT, part: Part, nets: NetTable) -> None:
    used: set[str] = set()
    for pad in footprint.Pads():
        number = pad.GetNumber()
        if number == "":
            if part.unnamed_pads_net and pad.GetAttribute() != pcbnew.PAD_ATTRIB_NPTH:
                pad.SetNet(nets.get(part.unnamed_pads_net))
            continue
        if number in part.nets:
            pad.SetNet(nets.get(part.nets[number]))
            used.add(number)
    missing = set(part.nets) - used
    if missing:
        raise ValueError(f"{part.ref}: pads {sorted(missing)} not found in {part.footprint}")


ASSEMBLY_FIELD = "Assembly"  # "JLCPCB" or "hand" (bought at LCSC, soldered by the user)


def _set_fields(footprint: pcbnew.FOOTPRINT, part: Part, hand: bool) -> None:
    if part.lcsc:
        footprint.SetField("LCSC", part.lcsc)
        footprint.SetField(ASSEMBLY_FIELD, "hand" if hand else "JLCPCB")
    if part.note:
        footprint.SetField("Note", part.note)
    if not part.assemble:
        footprint.SetDNP(True)
        footprint.SetExcludedFromPosFiles(True)
    for field in footprint.GetFields():
        if field.GetName() in ("LCSC", "Note", ASSEMBLY_FIELD):
            field.SetVisible(False)


def add_hole(board: pcbnew.BOARD, spec: BoardSpec, hole: Hole, nets: NetTable) -> None:
    footprint = pcbnew.FOOTPRINT(board)
    footprint.SetFPID(pcbnew.LIB_ID("gh_revive", "MountingHole"))  # an empty name breaks the Specctra round trip
    footprint.SetReference(hole.ref)
    footprint.SetValue(f"Hole_{hole.drill:g}mm")
    footprint.Reference().SetVisible(False)
    footprint.Value().SetVisible(False)
    footprint.SetAttributes(pcbnew.FP_EXCLUDE_FROM_POS_FILES | pcbnew.FP_EXCLUDE_FROM_BOM)
    footprint.SetPosition(to_page(spec, hole.x, hole.y))
    pad = pcbnew.PAD(footprint)
    pad.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
    pad.SetDrillSize(pcbnew.VECTOR2I(mm(hole.drill), mm(hole.drill)))
    if hole.pad > 0:
        pad.SetAttribute(pcbnew.PAD_ATTRIB_PTH)
        pad.SetSize(pcbnew.VECTOR2I(mm(hole.pad), mm(hole.pad)))
        pad.SetLayerSet(pcbnew.PAD.PTHMask())
        pad.SetNumber("1")
        if hole.net:
            pad.SetNet(nets.get(hole.net))
    else:
        pad.SetAttribute(pcbnew.PAD_ATTRIB_NPTH)
        pad.SetSize(pcbnew.VECTOR2I(mm(hole.drill), mm(hole.drill)))
        pad.SetLayerSet(pcbnew.PAD.UnplatedHoleMask())
    pad.SetPosition(to_page(spec, hole.x, hole.y))
    footprint.Add(pad)
    board.Add(footprint)


def _zone_outline(zone: pcbnew.ZONE, spec: BoardSpec, polygon: tuple[Point, ...]) -> None:
    outline = zone.Outline()
    outline.NewOutline()
    for x, y in polygon:
        outline.Append(mm(spec.origin[0] + x), mm(spec.origin[1] + y))


def add_keepout(board: pcbnew.BOARD, spec: BoardSpec, keepout: Keepout) -> None:
    zone = pcbnew.ZONE(board)
    zone.SetIsRuleArea(True)
    zone.SetZoneName(keepout.name)
    zone.SetDoNotAllowZoneFills(not keepout.allow_fills)
    zone.SetDoNotAllowTracks(not keepout.allow_tracks)
    zone.SetDoNotAllowVias(not (keepout.allow_tracks or keepout.allow_vias))
    zone.SetDoNotAllowPads(False)
    zone.SetDoNotAllowFootprints(False)
    layers = pcbnew.LSET()
    for name in keepout.layers:
        layers.AddLayer(layer_id(board, name))
    zone.SetLayerSet(layers)
    _zone_outline(zone, spec, keepout.polygon)
    board.Add(zone)


def set_hatch(zone: pcbnew.ZONE) -> None:
    """Hatched fill, ~40 % copper (ground behind capacitive touch electrodes)."""
    zone.SetFillMode(pcbnew.ZONE_FILL_MODE_HATCH_PATTERN)
    zone.SetHatchThickness(mm(0.3))
    zone.SetHatchGap(mm(1.2))


def add_copper_zone(board: pcbnew.BOARD, spec: BoardSpec, zone_spec: CopperZone, nets: NetTable,
                    allow_hatch: bool = True) -> pcbnew.ZONE:
    """allow_hatch=False keeps a routing-time plane solid (the autorouter cannot land vias on a hatch)."""
    zone = pcbnew.ZONE(board)
    zone.SetNet(nets.get(zone_spec.net))
    zone.SetLayer(layer_id(board, zone_spec.layer))
    zone.SetZoneName(zone_spec.name)
    zone.SetAssignedPriority(zone_spec.priority)
    zone.SetLocalClearance(mm(zone_spec.clearance))
    zone.SetMinThickness(mm(zone_spec.min_width))
    zone.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL if zone_spec.solid_pads else pcbnew.ZONE_CONNECTION_THERMAL)
    zone.SetThermalReliefGap(mm(0.25))
    zone.SetThermalReliefSpokeWidth(mm(0.4))
    zone.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
    if zone_spec.hatched and allow_hatch:
        set_hatch(zone)
    _zone_outline(zone, spec, zone_spec.polygon)
    board.Add(zone)
    return zone


def add_text(board: pcbnew.BOARD, spec: BoardSpec, text_spec: SilkText) -> None:
    text = pcbnew.PCB_TEXT(board)
    text.SetText(text_spec.text)
    text.SetLayer(layer_id(board, text_spec.layer))
    text.SetPosition(to_page(spec, text_spec.x, text_spec.y))
    text.SetTextSize(pcbnew.VECTOR2I(mm(text_spec.size), mm(text_spec.size)))
    text.SetTextThickness(mm(max(0.12, text_spec.size * 0.15)))
    text.SetTextAngleDegrees(text_spec.rot)
    if text_spec.layer.startswith("B."):
        text.SetMirrored(True)
    board.Add(text)


def fill_zones(board: pcbnew.BOARD) -> None:
    filler = pcbnew.ZONE_FILLER(board)
    filler.Fill(board.Zones())


def build_unrouted(spec: BoardSpec, path: Path) -> tuple[pcbnew.BOARD, NetTable]:
    """Create the board with outline, parts, holes, keepouts and routing-time planes."""
    board = create_board(spec, path)
    nets = NetTable(board)
    add_outline(board, spec)
    for part in spec.parts:
        add_part(board, spec, part, nets)
    for hole in spec.holes:
        add_hole(board, spec, hole, nets)
    for keepout in spec.keepouts:
        add_keepout(board, spec, keepout)
    apply_netclasses(board, spec)
    for zone_spec in spec.plane_zones:
        add_copper_zone(board, spec, zone_spec, nets, allow_hatch=False)
    for text_spec in spec.texts:
        add_text(board, spec, text_spec)
    fill_zones(board)
    pcbnew.SaveBoard(str(path), board)
    return board, nets
