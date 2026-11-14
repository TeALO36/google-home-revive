"""Mechanical dimensions of the original Google Home (2016) boards, in millimetres.

Every value below was measured on iFixit / FCC photographs (photogrammetry), not on a physical unit:
  * main board scale calibrated on the Samsung K4B4G1646E DDR3 package (7.5 x 13.3 mm),
  * top board scale calibrated on the ATSAMD21 QFN-48 (7 x 7 mm) and INMP621 (4 x 3 mm).
Expected accuracy: +/-0.5 mm. CHECK WITH A CALIPER (or the 1:1 template PDF) BEFORE ORDERING, then edit
the values here and re-run `tools/build.py`: both boards are regenerated from this single file.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class MainBoardDims:
    """T-shaped main board. Local frame: x from the top end (antennas) to the jack end, y across, front view."""

    length: float = 107.6
    width: float = 49.0  # across the antenna wings, at x = wing_end
    left_edge_height: float = 39.2  # height of the edge at x = 0
    wing_end: float = 40.5  # x where the antenna wings stop
    mid_width: float = 36.0
    mid_end: float = 65.5  # x where the narrow stem starts
    stem_width: float = 14.0
    corner: float = 0.75  # inner corner relief
    hole_drill: float = 2.4  # original ~2.3 mm
    hole_land: float = 4.2
    # screw holes (x, offset from the centre line; negative = upper side in front view)
    holes: tuple[tuple[float, float], ...] = ((6.2, -17.75), (6.2, 17.75), (60.45, -15.05), (60.45, 15.05), (84.1, -3.65))
    mute_switch: tuple[float, float] = (10.2, 0.0)
    usb_port: tuple[float, float] = (93.2, 0.0)  # vertical connector, long axis across the stem
    speaker_connector_x: float = 84.2  # JST ZH 2-pin, opening on the lower stem edge

    @property
    def centre_y(self) -> float:
        return self.width / 2


@dataclass(frozen=True)
class JackTab:
    depth: float  # pad centre distance from the stem end edge
    back_y: float  # offset from the stem axis as seen from the BACK of the board (+ = down in the back photo)
    length: float  # along the stem
    width: float


@dataclass(frozen=True)
class JackDims:
    """Original SMD DC jack (3.5 x 1.35 mm plug, centre positive, 16.5 V), soldered on the back side."""

    peg_depths: tuple[float, float] = (2.65, 6.75)
    peg_drill: float = 1.6
    tabs: dict[str, JackTab] = field(default_factory=lambda: {
        "TIP": JackTab(depth=10.1, back_y=0.66, length=3.2, width=1.9),  # rear tab next to the axis: centre pin (+)
        "SLV": JackTab(depth=10.0, back_y=-1.9, length=3.4, width=1.9),  # rear tab, sleeve (-)
        "SW": JackTab(depth=8.47, back_y=3.55, length=2.4, width=2.8),  # side switch contact
        "MP1": JackTab(depth=2.63, back_y=-4.45, length=2.0, width=3.0),  # shell tab
        "MP2": JackTab(depth=2.63, back_y=4.1, length=2.0, width=3.0),  # shell tab
    })


@dataclass(frozen=True)
class TopBoardDims:
    """Round touch / LED / microphone board. Local frame: origin at the centre, component side view (y down)."""

    diameter: float = 74.8  # measured 75.0-75.2 including the board edge wall; kept slightly under
    led_count: int = 12
    led_radius: float = 10.48
    led_first_angle: float = 0.0  # degrees; LEDs every 30 deg
    mic_radius: float = 34.46  # acoustic ports on the horizontal axis, left and right
    mic_port_drill: float = 0.6  # through-hole under each bottom-port microphone (see footprints.py)
    notch_width: float = 1.5
    notch_depth: float = 2.6
    top_notch_x: tuple[float, float] = (-8.17, 8.17)  # two slots on the upper edge
    bottom_notch_x: float = 7.4  # one slot on the lower edge (component side view)
    bottom_notch_depth: float = 2.3
    electrode_inner: float = 14.8  # clears the outer J-leads of the 3.5 mm LEDs (r = 10.48 + 3.6)
    electrode_outer: float = 35.6
    centre_electrode_radius: float = 4.3  # tap button inside the LED ring (inner LED pads at r = 6.9)
    sectors: int = 10
    sector_gap: float = 0.8
    sector_zigzag_deg: float = 9.0
    sector_teeth: int = 3

    @property
    def radius(self) -> float:
        return self.diameter / 2


MAIN = MainBoardDims()
JACK = JackDims()
TOP = TopBoardDims()
