"""Data model shared by the board generators (no KiCad dependency)."""
from __future__ import annotations

from dataclasses import dataclass, field

Point = tuple[float, float]


@dataclass(frozen=True)
class Part:
    """One placed component: footprint, sourcing data, position and pad->net map."""

    ref: str
    value: str
    footprint: str  # "Library:Name" (KiCad lib) or "gh_revive:Name" (project lib)
    x: float
    y: float
    rot: float = 0.0
    side: str = "F"  # "F" or "B"
    nets: dict[str, str] = field(default_factory=dict)
    lcsc: str = ""
    assemble: bool = True  # False -> not a bought component (wire pads, electrode taps, reused original part)
    hand: bool = False  # True -> bought at LCSC and soldered by the user, left out of the JLCPCB BOM / CPL
    note: str = ""
    unnamed_pads_net: str = ""  # net for pads without a number (mic seal ring, ...)


@dataclass(frozen=True)
class NetClass:
    name: str
    track: float
    clearance: float
    via_dia: float
    via_drill: float
    patterns: tuple[str, ...]


@dataclass(frozen=True)
class Hole:
    """Board-level hole. Plated holes with a net become grounded screw lands."""

    x: float
    y: float
    drill: float
    pad: float = 0.0  # 0 -> non plated
    net: str = ""
    ref: str = "H"


@dataclass(frozen=True)
class Arc:
    """Outline arc through start/mid/end."""

    start: Point
    mid: Point
    end: Point


@dataclass(frozen=True)
class Keepout:
    """Rule area: no copper / tracks / vias inside the polygon."""

    polygon: tuple[Point, ...]
    layers: tuple[str, ...]
    name: str = ""
    allow_tracks: bool = False
    allow_vias: bool = False
    allow_fills: bool = False  # True -> copper pours (e.g. touch electrodes) may fill inside


@dataclass(frozen=True)
class CopperZone:
    net: str
    layer: str
    polygon: tuple[Point, ...]
    clearance: float = 0.3
    min_width: float = 0.2
    priority: int = 0
    solid_pads: bool = False
    name: str = ""
    hatched: bool = False  # hatched fill (ground behind capacitive touch electrodes)


@dataclass(frozen=True)
class SilkText:
    text: str
    x: float
    y: float
    size: float = 1.0
    layer: str = "F.SilkS"
    rot: float = 0.0


@dataclass
class BoardSpec:
    """Everything needed to generate one PCB."""

    name: str
    title: str
    layers: int
    origin: Point  # KiCad page coordinates of the board-local (0, 0)
    outline: list[Point | Arc]
    cutouts: list[list[Point]] = field(default_factory=list)
    parts: list[Part] = field(default_factory=list)
    holes: list[Hole] = field(default_factory=list)
    netclasses: list[NetClass] = field(default_factory=list)
    keepouts: list[Keepout] = field(default_factory=list)
    plane_zones: list[CopperZone] = field(default_factory=list)  # present during autorouting
    post_zones: list[CopperZone] = field(default_factory=list)  # added after autorouting
    texts: list[SilkText] = field(default_factory=list)
    signal_layers: tuple[str, ...] = ("F.Cu", "B.Cu")
    strip_footprint_keepouts: tuple[str, ...] = ()  # refs whose library rule areas are replaced
