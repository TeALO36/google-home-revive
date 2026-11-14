"""Top board ("carte du dessus"): MPR121 capacitive touch ring, 12 addressable LEDs, 2 PDM microphones.

Local frame: origin at the board centre, COMPONENT SIDE view (F.Cu, faces down into the speaker), y down.
B.Cu faces the plastic top: touch electrodes + the LED ring (LEDs shine up through the diffuser).
Angles are in degrees, measured clockwise from +x in this view (y down).
"""
from __future__ import annotations

import math

from .catalog import (ELECTRODE_TAP, LCSC_AHCT1G125, LCSC_IM69D130, LCSC_MPR121, LCSC_WS2812B_MINI_V3J, LED_MINI_V3J,
                      MIC_IM69D130, QFN20_MPR121, SOT23_5, WIRE_PADS_10, cap, cap_22u, resistor)
from .mainboard import LINK_LABELS, LINK_PINS
from .mechanical import TOP
from .model import Arc, BoardSpec, CopperZone, Keepout, NetClass, Part, Point, SilkText

SECTOR_START = -90.0  # first sector starts at 12 o'clock (component side view)
FIRST_LED_ANGLE = 90.0  # D1 sits at 6 o'clock, next to the wire pads; chain runs clockwise (component side view)
TAP_RADIUS = 15.6
CENTRE_NET = "ELE10"  # centre tap button
CENTRE_TAP: Point = (-2.9, -0.3)  # via to F.Cu, right next to MPR121 pin 18 (ELE10)
LEDS_PER_CAP = 2  # one 100 nF per 2 LEDs (+ 22 uF bulk at the wire pads)
WIRE_PADS_Y = 24.0
MIC_PORTS: tuple[Point, Point] = ((TOP.mic_radius, 0.0), (-TOP.mic_radius, 0.0))
MIC_PORT_OFFSET = 0.81  # acoustic port position in the IM69D130 footprint (local +y)


def polar(radius: float, angle_deg: float) -> Point:
    a = math.radians(angle_deg)
    return (round(radius * math.cos(a), 4), round(radius * math.sin(a), 4))


def _arc_points(radius: float, start: float, end: float, step: float = 3.0) -> list[Point]:
    count = max(2, int(abs(end - start) / step) + 1)
    return [polar(radius, start + (end - start) * i / (count - 1)) for i in range(count)]


# ---------------------------------------------------------------- outline

def _notches() -> list[tuple[float, float, float]]:
    """(centre x, side, depth): side -1 = upper edge (y < 0), +1 = lower edge."""
    notches = [(x, -1.0, TOP.notch_depth) for x in TOP.top_notch_x]
    notches.append((TOP.bottom_notch_x, 1.0, TOP.bottom_notch_depth))
    return notches


def _notch_path(xc: float, side: float, depth: float) -> tuple[float, float, list[Point]]:
    """Edge-entry angle, edge-exit angle and the points of one rectangular notch, in increasing-angle order."""
    r = TOP.radius
    half = TOP.notch_width / 2
    edges = [(x, side * math.sqrt(r * r - x * x)) for x in (xc - half, xc + half)]
    edges.sort(key=lambda p: math.atan2(p[1], p[0]))
    inner_y = side * (math.sqrt(r * r - xc * xc) - depth)
    first, last = edges
    path = [first, (first[0], inner_y), (last[0], inner_y), last]
    angle = [math.degrees(math.atan2(p[1], p[0])) for p in (first, last)]
    return angle[0], angle[1], path


def _outline() -> list[Point | Arc]:
    notches = sorted((_notch_path(*n) for n in _notches()), key=lambda n: n[0])
    items: list[Point | Arc] = []
    for index, (_start, end_angle, path) in enumerate(notches):
        items.extend(path[1:])  # inner corners and exit point; entry point is reached by the previous arc
        next_start, _end, next_path = notches[(index + 1) % len(notches)]
        if next_start <= end_angle:
            next_start += 360.0
        mid = polar(TOP.radius, (end_angle + next_start) / 2)
        items.append(Arc(path[-1], mid, next_path[0]))
    return items


# ---------------------------------------------------------------- electrodes

def _zigzag_edge(base: float, offset_mm: float) -> list[Point]:
    """One sector boundary from inner to outer radius, zig-zagging so neighbouring sectors interleave."""
    steps = 2 * TOP.sector_teeth
    points = []
    for i in range(steps + 1):
        radius = TOP.electrode_inner + (TOP.electrode_outer - TOP.electrode_inner) * i / steps
        zig = TOP.sector_zigzag_deg / 2 * (1 if i % 2 else -1)
        points.append(polar(radius, base + zig + math.degrees(offset_mm / radius)))
    return points


def sector_polygon(index: int) -> tuple[Point, ...]:
    span = 360.0 / TOP.sectors
    start = SECTOR_START + index * span
    end = start + span
    half_gap = TOP.sector_gap / 2
    left = _zigzag_edge(start, half_gap)
    right = _zigzag_edge(end, -half_gap)
    outer_a = math.degrees(math.atan2(left[-1][1], left[-1][0]))
    outer_b = math.degrees(math.atan2(right[-1][1], right[-1][0]))
    if outer_b < outer_a:
        outer_b += 360.0
    outer = _arc_points(TOP.electrode_outer, outer_a, outer_b)[1:-1]
    inner_a = math.degrees(math.atan2(left[0][1], left[0][0]))
    inner_b = math.degrees(math.atan2(right[0][1], right[0][0]))
    if inner_b < inner_a:
        inner_b += 360.0
    inner = _arc_points(TOP.electrode_inner, inner_b, inner_a)[1:-1]
    return tuple(left + outer + list(reversed(right)) + inner)


def _wedge(index: int, margin: float) -> tuple[Point, ...]:
    span = 360.0 / TOP.sectors
    start = SECTOR_START + index * span - TOP.sector_zigzag_deg
    end = SECTOR_START + (index + 1) * span
    outer = _arc_points(TOP.electrode_outer + margin, start, end)
    inner = _arc_points(TOP.electrode_inner - margin, end, start)
    return tuple(outer + inner)


def _circle(radius: float, centre: Point = (0.0, 0.0), steps: int = 48) -> tuple[Point, ...]:
    cx, cy = centre
    return tuple((round(cx + px, 4), round(cy + py, 4))
                 for px, py in (polar(radius, 360.0 * i / steps) for i in range(steps)))


def electrode_net(index: int) -> str:
    return f"ELE{index}"


def _electrode_zones() -> list[CopperZone]:
    """Ring sectors (volume, tap) and the round centre button inside the LED ring (tap).

    No track crosses the centre electrode on B.Cu (keepout), so it stays one solid disc.
    """
    zones = [CopperZone(electrode_net(k), "B.Cu", sector_polygon(k), clearance=0.3, min_width=0.25, priority=2,
                        solid_pads=True, name=f"Touch sector {k}") for k in range(TOP.sectors)]
    zones.append(CopperZone(CENTRE_NET, "B.Cu", _circle(TOP.centre_electrode_radius), clearance=0.3, min_width=0.25,
                            priority=2, solid_pads=True, name="Touch centre"))
    return zones


def _keepouts() -> list[Keepout]:
    """B.Cu: no tracks under the electrodes (vias allowed, electrodes fill around them); no copper at mic ports."""
    areas = [Keepout(_wedge(k, 0.2), ("B.Cu",), f"Electrode {k} no-track", allow_vias=True, allow_fills=True)
             for k in range(TOP.sectors)]
    areas.append(Keepout(_circle(TOP.centre_electrode_radius + 0.2), ("B.Cu",), "Centre electrode no-track",
                         allow_vias=True, allow_fills=True))
    # electrodes (B.Cu) keep 1.6 mm away from the acoustic holes; the microphone itself sits on F.Cu
    areas += [Keepout(_circle(1.6, port, 24), ("B.Cu",), f"Mic port {i + 1}", allow_vias=True)
              for i, port in enumerate(MIC_PORTS)]
    return areas


# ---------------------------------------------------------------- parts

def _touch() -> list[Part]:
    nets = {"1": "TOUCH_IRQ", "2": "I2C_SCL", "3": "I2C_SDA", "4": "+3V3", "5": "MPR_VREG", "6": "GND",
            "7": "MPR_REXT", "20": "+3V3"}
    nets.update({str(8 + k): electrode_net(k) for k in range(TOP.sectors)})  # ELE0..ELE9 = ring sectors
    nets["18"] = CENTRE_NET  # ELE10 = centre button; ELE11 unused
    parts = [
        Part("U1", "MPR121QR2", QFN20_MPR121, 0.0, 0.0, 0, nets=nets, lcsc=LCSC_MPR121,
             note="Capacitive touch controller, I2C 0x5B (ADDR = VDD). ELE0-9 = ring sectors, ELE10 = centre button."),
        cap("C1", "100nF", -2.9, 1.9, 270, "+3V3"),  # pad 1 faces VDD (pin 20)
        cap("C2", "100nF", 1.6, 3.6, 0, "MPR_VREG"),
        resistor("R1", "75k", 3.4, 0.0, 90, "MPR_REXT", "GND"),
    ]
    span = 360.0 / TOP.sectors
    for k in range(TOP.sectors):
        x, y = polar(TAP_RADIUS, SECTOR_START + (k + 0.5) * span)
        parts.append(Part(f"TE{k}", f"TAP_{k}", ELECTRODE_TAP, x, y, nets={"1": electrode_net(k)}, assemble=False))
    parts.append(Part(f"TE{TOP.sectors}", "TAP_CENTRE", ELECTRODE_TAP, *CENTRE_TAP, nets={"1": CENTRE_NET},
                      assemble=False))
    return parts


def _led_angle(index: int) -> float:
    return FIRST_LED_ANGLE + index * 360.0 / TOP.led_count


def _leds() -> list[Part]:
    parts: list[Part] = []
    for i in range(TOP.led_count):
        angle = _led_angle(i)
        x, y = polar(TOP.led_radius, angle)
        nets = {"1": "+5V", "3": "GND", "4": f"LED_D{i}"}
        if i + 1 < TOP.led_count:
            nets["2"] = f"LED_D{i + 1}"
        # long axis (J-leads) radial so that 12 LEDs fit on the ring; soldered by the user (iron-friendly leads)
        parts.append(Part(f"D{i + 1}", "WS2812B-MINI-V3J", LED_MINI_V3J, x, y, (90.0 - angle) % 360, side="B",
                          nets=nets, lcsc=LCSC_WS2812B_MINI_V3J, hand=True,
                          note="Addressable RGB LED on the top face (towards the diffuser), hand soldered"))
        if i % LEDS_PER_CAP == 0:  # sparser decoupling leaves routing gaps through the ring on 2 layers
            parts.append(cap(f"C{10 + i // LEDS_PER_CAP}", "100nF", x, y, (-angle) % 360, "+5V"))
    return parts


def _power_and_link() -> list[Part]:
    pads = {str(i + 1): net for i, net in enumerate(LINK_PINS)}
    return [
        Part("J1", "MAIN_LINK", WIRE_PADS_10, 0.0, WIRE_PADS_Y, 0, nets=pads, assemble=False,
             note="10 wires from the main board (same order as J4 on the main board)"),
        Part("U2", "SN74AHCT1G125DBVR", SOT23_5, 6.0, 19.5, 0, lcsc=LCSC_AHCT1G125,
             nets={"1": "GND", "2": "LED_DATA", "3": "GND", "4": "LED_D0", "5": "+5V"},
             hand=True, note="3.3 V -> 5 V level shifter for the LED data line, hand soldered"),
        cap("C3", "100nF", 6.0, 16.6, 0, "+5V"),
        cap_22u("C4", -6.0, 19.5, 0, "+5V"),
        cap("C5", "1uF", -6.0, 17.2, 0, "+3V3"),
    ]


def _mics() -> list[Part]:
    parts: list[Part] = []
    for i, ((px, py), select) in enumerate(zip(MIC_PORTS, ("GND", "VMIC"))):
        nets = {"1": "PDM_DAT", "2": "VMIC", "3": "PDM_CLK", "4": select, "5": "GND"}
        channel = "left (SELECT = GND)" if select == "GND" else "right (SELECT = VDD)"
        parts.append(Part(f"MK{i + 1}", "IM69D130", MIC_IM69D130, px, py - MIC_PORT_OFFSET, 0, nets=nets,
                          lcsc=LCSC_IM69D130, note=f"Bottom-port PDM microphone, {channel}; port drilled through"))
        cap_x = px - 3.46 if px > 0 else px + 3.46
        parts.append(cap(f"C{6 + i}", "100nF", cap_x, py - MIC_PORT_OFFSET, 90, "VMIC"))
    return parts


def _texts() -> list[SilkText]:
    start = -2.54 * (len(LINK_PINS) - 1) / 2
    texts = [SilkText(label, start + i * 2.54, WIRE_PADS_Y + 2.9, 0.8, "F.SilkS", rot=90.0)
             for i, label in enumerate(LINK_LABELS)]
    texts += [
        SilkText("GH-REVIVE TOP v1.0", 0.0, -27.0, 1.2, "F.SilkS"),
        SilkText("L", MIC_PORTS[0][0] - 4.0, 3.0, 1.0, "F.SilkS"),
        SilkText("R", MIC_PORTS[1][0] + 4.0, 3.0, 1.0, "F.SilkS"),
        SilkText("GH-REVIVE TOP", 0.0, 0.0, 1.0, "B.SilkS"),
    ]
    return texts


def build_spec() -> BoardSpec:
    everything = _circle(TOP.radius + 1.0)
    return BoardSpec(
        name="gh_topboard",
        title="GH-Revive top board",
        layers=2,  # F parts + signals + hatched GND (shield behind the electrodes), B electrodes + LEDs
        origin=(100.0, 100.0),
        outline=_outline(),
        parts=_touch() + _leds() + _power_and_link() + _mics(),
        netclasses=[
            NetClass("Default", 0.2, 0.15, 0.6, 0.3, ()),  # 0.2 mm enters the 0.4 mm pitch MPR121 pads
            NetClass("Power", 0.3, 0.15, 0.6, 0.3, ("+5V",)),  # LED supply, < 0.25 A
        ],
        keepouts=_keepouts(),
        post_zones=_electrode_zones() + [
            CopperZone("GND", "F.Cu", everything, clearance=0.3, solid_pads=True, name="GND hatched F", hatched=True),
        ],
        texts=_texts(),
        signal_layers=("F.Cu", "B.Cu"),
    )
