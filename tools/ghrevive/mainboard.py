"""Main board ("carte mere"): ESP32-S3 + ESP32 Bluetooth co-processor + TAS5805M amplifier + power.

Local frame (front view, mm): x = 0 at the top end (antennas / link to the top board), x = 107.6 at the DC jack end,
y across the board. The front (F.Cu) faces the rear shell: mute switch, USB-C and speaker connector are there.
"""
from __future__ import annotations

from .catalog import (CAP_220UF_ELEC, CP_ELEC, D_SMA, D_SOD123, SOT23, SOT23_5, SOT23_6, TAS5805_FP, TSSOP8, cap,
                      cap_10u_50v, cap_22u, inductor, resistor, test_pad)
from .mechanical import MAIN
from .model import BoardSpec, CopperZone, Hole, Keepout, NetClass, Part, Point, SilkText

YC = MAIN.centre_y
AMP_Y = YC + 0.6  # amplifier centre, pushed down to clear the bulk capacitor
LINK_PINS = ("+5V", "GND", "LED_DATA", "+3V3", "I2C_SDA", "I2C_SCL", "VMIC", "PDM_DAT", "GND", "PDM_CLK")
LINK_LABELS = ("5V", "GND", "LED", "3V3", "SDA", "SCL", "VMIC", "DAT", "GND", "CLK")
LINK_X, LINK_Y0, LINK_PITCH = 2.6, YC - 11.43, 2.54

S3_NETS = {
    "1": "GND", "40": "GND", "41": "GND", "2": "+3V3", "3": "S3_EN",
    "4": "PDM_CLK_S3", "5": "PDM_DAT", "6": "LED_DATA_S3", "7": "MUTE_STATE", "8": "MUTE_SET_N",
    "9": "I2C_SDA", "10": "I2C_SCL", "13": "USB_DN", "14": "USB_DP",
    "17": "I2S_BCLK", "18": "I2S_LRCK", "19": "I2S_DOUT", "20": "I2S_REF", "21": "AMP_PDN", "22": "AMP_FAULT",
    "23": "BT_GPIO", "24": "SPARE_IO47", "25": "SPARE_IO48", "27": "S3_BOOT",
    "31": "BT_BCLK", "32": "BT_LRCK", "33": "BT_DATA", "34": "BT_TXD", "35": "BT_RXD",
    "36": "S3_RXD0", "37": "S3_TXD0", "38": "BT_EN_CTL", "39": "BT_BOOT_CTL",
}
BT_NETS = {
    "1": "GND", "15": "GND", "38": "GND", "39": "GND", "2": "+3V3", "3": "BT_EN", "25": "BT_BOOT",
    "30": "BT_BCLK", "31": "BT_LRCK", "33": "BT_DATA", "34": "BT_RXD", "35": "BT_TXD", "36": "BT_GPIO",
}
AMP_NETS = {
    "1": "GND", "5": "GND", "14": "GND", "19": "GND", "24": "GND", "29": "GND",
    "2": "+3V3", "3": "AMP_FAULT", "4": "AMP_VR_DIG", "6": "I2S_LRCK", "7": "I2S_BCLK", "8": "I2S_DOUT",
    "9": "I2S_REF", "10": "I2C_SDA", "11": "I2C_SCL", "12": "AMP_PDN", "13": "AMP_AVDD",
    "15": "PVDD", "16": "PVDD", "27": "PVDD", "28": "PVDD",
    "17": "OUT_B_P", "18": "BST_B_P", "20": "OUT_B_N", "21": "BST_B_N",
    "22": "BST_A_N", "23": "OUT_A_N", "25": "BST_A_P", "26": "OUT_A_P",
}
USB_NETS = {
    "A1": "GND", "B12": "GND", "A12": "GND", "B1": "GND", "1": "GND", "2": "GND", "3": "GND", "4": "GND",
    "A4": "VBUS", "B9": "VBUS", "A9": "VBUS", "B4": "VBUS", "A5": "USB_CC1", "B5": "USB_CC2",
    "A6": "USB_DP", "B6": "USB_DP", "A7": "USB_DN", "B7": "USB_DN",
}


def _outline() -> list[Point]:
    d = MAIN
    left = (d.width - d.left_edge_height) / 2
    mid = (d.width - d.mid_width) / 2
    stem = (d.width - d.stem_width) / 2
    c = d.corner
    return [
        (0.0, left), (d.wing_end, 0.0), (d.wing_end, mid - c), (d.wing_end + c, mid), (d.mid_end, mid),
        (d.mid_end, stem - c), (d.mid_end + c, stem), (d.length, stem), (d.length, d.width - stem),
        (d.mid_end + c, d.width - stem), (d.mid_end, d.width - stem + c), (d.mid_end, d.width - mid),
        (d.wing_end + c, d.width - mid), (d.wing_end, d.width - mid + c), (d.wing_end, d.width),
        (0.0, d.width - left),
    ]


def _mcu() -> list[Part]:
    return [
        Part("U1", "ESP32-S3-WROOM-1-N16R8", "RF_Module:ESP32-S3-WROOM-1", 24.5, 16.0, nets=S3_NETS, lcsc="C2913202",
             note="Wi-Fi, voice pipeline, mixing. Any ESP32-S3-WROOM-1 variant with PSRAM fits."),
        cap_22u("C15", 13.3, 19.6, 90, "+3V3"),
        cap("C16", "100nF", 13.6, 11.4, 90, "+3V3"),
        resistor("R7", "10k", 13.2, 14.3, 180, "S3_EN", "+3V3"),
        cap("C17", "1uF", 13.2, 15.9, 180, "S3_EN"),
        resistor("R11", "4.7k", 27.2, 37.4, 0, "+3V3", "AMP_FAULT"),
        resistor("R12", "10k", 27.2, 38.9, 0, "GND", "AMP_PDN"),
        test_pad("TP1", "EN", 17.0, 41.0, "S3_EN"),
        test_pad("TP2", "BOOT", 20.0, 41.0, "S3_BOOT"),
        test_pad("TP3", "TX", 23.0, 41.0, "S3_TXD0"),
        test_pad("TP4", "RX", 26.0, 41.0, "S3_RXD0"),
        test_pad("TP5", "GND", 29.0, 41.0, "GND"),
        test_pad("TP6", "3V3", 32.0, 41.0, "+3V3"),
        test_pad("TP7", "5V", 35.0, 41.0, "+5V"),
        test_pad("TP8", "IO47", 32.0, 37.6, "SPARE_IO47"),
        test_pad("TP9", "IO48", 35.0, 37.6, "SPARE_IO48"),
    ]


def _bluetooth() -> list[Part]:
    return [
        Part("U2", "ESP32-WROOM-32E-N4", "RF_Module:ESP32-WROOM-32E", 46.0, 29.5, 180, nets=BT_NETS, lcsc="C701341",
             note="Bluetooth Classic A2DP sink co-processor, flashed through U1 (UART + EN/BOOT)."),
        cap("C19", "100nF", 56.6, 34.1, 270, "+3V3"),
        resistor("R8", "10k", 56.6, 31.1, 270, "+3V3", "BT_EN"),
        cap("C20", "1uF", 56.6, 28.1, 90, "BT_EN"),
        cap_22u("C18", 56.8, 19.5, 270, "+3V3"),
        resistor("R9", "1k", 35.3, 12.4, 90, "BT_EN_CTL", "BT_EN"),
        resistor("R10", "1k", 35.3, 15.4, 90, "BT_BOOT_CTL", "BT_BOOT"),
    ]


def _power_input() -> list[Part]:
    jack_nets = {"TIP": "VIN_RAW", "SLV": "GND", "SW": "GND", "MP1": "GND", "MP2": "GND"}
    return [
        Part("J2", "DC_JACK_ORIGINAL", "gh_revive:GH_DCJack_Original", MAIN.length, YC, nets=jack_nets, assemble=False,
             note="Reuse the original jack (3.5 x 1.35 mm, centre +, 16.5 V). Check polarity with a multimeter."),
        Part("D1", "SS54", D_SMA, 103.3, 19.9, 0, nets={"1": "PVDD", "2": "VIN_RAW"}, lcsc="C22452",
             note="Reverse polarity protection"),
        Part("D2", "SMAJ18A", D_SMA, 103.3, 29.1, 0, nets={"1": "PVDD", "2": "GND"}, lcsc="C19077538",
             note="Input TVS"),
        Part("C1", "220uF/25V", CP_ELEC, 61.3, 15.95, 90, nets={"1": "PVDD", "2": "GND"}, lcsc=CAP_220UF_ELEC,
             note="Bulk capacitor (same total as the original 2 x 100 uF)"),
    ]


def _buck_5v() -> list[Part]:
    nets = {"1": "GND", "2": "SW_5V", "3": "PVDD", "4": "FB_5V", "6": "BOOT_5V"}  # pin 5 EN floats = enabled
    return [
        Part("U4", "TPS54302DDCR", SOT23_6, 40.9, 12.1, 180, nets=nets, lcsc="C311983", note="16.5 V -> 5.07 V, 3 A"),
        cap_10u_50v("C3", 41.0, 8.5, 180, "PVDD"),
        cap("C8", "100nF", 40.9, 15.0, 0, "BOOT_5V", "SW_5V"),
        resistor("R1", "75k", 37.6, 13.6, 90, "FB_5V", "+5V"),
        resistor("R2", "10k", 37.6, 10.6, 90, "GND", "FB_5V"),
        inductor("L1", "10uH", 45.6, 11.8, 0, "SW_5V", "+5V"),
        cap_22u("C9", 49.6, 10.4, 90, "+5V"),
        cap_22u("C10", 51.6, 10.4, 90, "+5V"),
    ]


def _buck_3v3() -> list[Part]:
    nets = {"1": "+5V", "2": "GND", "3": "SW_3V3", "4": "+5V", "5": "FB_3V3"}
    return [
        Part("U5", "TLV62569DBVR", SOT23_5, 20.3, 33.2, 0, nets=nets, lcsc="C141836", note="5 V -> 3.33 V, 2 A"),
        cap_22u("C12", 17.0, 33.2, 90, "+5V"),
        inductor("L2", "2.2uH", 25.0, 33.2, 0, "SW_3V3", "+3V3"),
        cap_22u("C13", 29.6, 32.0, 0, "+3V3"),
        cap_22u("C14", 29.6, 34.4, 0, "+3V3"),
        resistor("R3", "100k", 20.0, 36.4, 0, "FB_3V3", "+3V3"),
        resistor("R4", "22k", 23.2, 36.4, 0, "FB_3V3", "GND"),
    ]


def _usb() -> list[Part]:
    usb_x, _ = MAIN.usb_port
    return [
        Part("J1", "USB-C", "gh_revive:USB-C-SMD_TYPEC-303-ACP16", usb_x, YC, 90, nets=USB_NETS, lcsc="C720628",
             note="Vertical USB-C, flashing / debug (replaces the micro-USB service port)."),
        Part("U6", "USBLC6-2SC6", SOT23_6, 97.95, 20.3, 90, lcsc="C7519",
             nets={"1": "USB_DN", "6": "USB_DN", "3": "USB_DP", "4": "USB_DP", "2": "GND", "5": "VBUS"}),
        resistor("R5", "5.1k", 97.9, 26.5, 0, "USB_CC1", "GND"),
        resistor("R6", "5.1k", 97.9, 28.1, 0, "USB_CC2", "GND"),
        cap("C37", "1uF", 97.9, 29.7, 0, "VBUS"),
        Part("D4", "B5819W", D_SOD123, 89.25, 27.0, 90, nets={"1": "+5V", "2": "VBUS"}, lcsc="C8598",
             note="USB power for flashing without the 16.5 V supply"),
    ]


def _amplifier() -> list[Part]:
    return [
        Part("U3", "TAS5805MPWPR", TAS5805_FP, 63.5, AMP_Y, 0, nets=AMP_NETS, lcsc="C478472",
             note="I2S class-D amplifier with DSP, BTL on channel A, SDOUT = echo reference."),
        cap("C21", "100nF", 58.6, AMP_Y - 4.2, 270, "GND", "+3V3"),
        cap("C23", "1uF", 57.6, AMP_Y - 1.6, 0, "GND", "AMP_VR_DIG"),
        cap("C24", "1uF", 60.6, AMP_Y + 6.3, 0, "AMP_AVDD"),
        # bootstrap caps follow the pin order of the right-hand row (26/25 A_P, 23/22 A_N, 21/20 B_N, 18/17 B_P):
        # column x 69.2 = A_P, B_N, B_P; column x 70.9 = A_N, reached through the 1.5 mm gap between C25 and C27.
        # The stem is only 14 mm high: the PVDD 100 nF caps lie flat above pin 28 and below pin 15, inside the edge.
        cap("C6", "100nF", 66.6, AMP_Y - 6.35, 0, "PVDD"),
        cap("C25", "470nF", 69.2, AMP_Y - 3.1, 270, "OUT_A_P", "BST_A_P"),
        cap("C27", "470nF", 69.2, AMP_Y + 0.95, 270, "BST_B_N", "OUT_B_N"),
        cap("C28", "470nF", 69.2, AMP_Y + 3.95, 270, "BST_B_P", "OUT_B_P"),
        cap("C7", "100nF", 63.9, AMP_Y + 6.0, 180, "PVDD"),
        cap_22u("C4", 71.0, AMP_Y - 5.5, 90, "PVDD"),
        cap("C26", "470nF", 70.9, AMP_Y - 0.6, 270, "OUT_A_N", "BST_A_N"),
        cap_22u("C5", 71.0, AMP_Y + 4.1, 90, "PVDD"),
        inductor("L3", "4.7uH", 74.6, 21.0, 0, "OUT_A_P", "SPK_P"),
        inductor("L4", "4.7uH", 74.6, 28.0, 0, "OUT_A_N", "SPK_N"),
        cap("C29", "1uF", 78.8, 21.0, 90, "SPK_P"),
        cap("C30", "1uF", 78.8, 28.0, 90, "SPK_N"),
        Part("J3", "SPEAKER", "Connector_JST:JST_ZH_S2B-ZR-SM4A-TF_1x02-1MP_P1.50mm_Horizontal",
             MAIN.speaker_connector_x, 27.3, 0, nets={"1": "SPK_P", "2": "SPK_N", "MP": "GND"}, lcsc="C265329",
             note="Original speaker plug (JST ZH 1.5 mm, 2 pins)"),
        Part("J5", "SPK_PADS", "gh_revive:GH_SpeakerPads", 88.4, 20.6, 90, nets={"1": "SPK_P", "2": "SPK_N"},
             assemble=False, note="Alternative: solder the speaker wires here"),
    ]


def _mute() -> list[Part]:
    sw_x, _ = MAIN.mute_switch
    latch = {"1": "MUTE_CLK", "2": "MUTE_NQ", "3": "MUTE_NQ", "4": "GND", "5": "MIC_OFF", "6": "MUTE_POR",
             "7": "MUTE_SET_N", "8": "+3V3"}
    return [
        Part("SW1", "MUTE", "Button_Switch_SMD:SW_Push_1P1T_XKB_TS-1187A", sw_x, YC, 0,
             nets={"1": "GND", "2": "MUTE_BTN"}, lcsc="C318884", note="Same position as the original mute switch"),
        resistor("R15", "100k", 6.3, 28.3, 0, "+3V3", "MUTE_BTN"),
        cap("C31", "100nF", 6.3, 29.8, 0, "MUTE_BTN"),
        Part("U8", "SN74LVC1G14DBVR", SOT23_5, 10.4, 30.0, 0, lcsc="C7835",
             nets={"2": "MUTE_BTN", "3": "GND", "4": "MUTE_CLK", "5": "+3V3"}, note="Debounce Schmitt trigger"),
        cap("C34", "100nF", 13.5, 30.2, 90, "GND", "+3V3"),
        Part("U7", "74LVC1G74DP", TSSOP8, 11.0, 34.7, 0, nets=latch, lcsc="C548409",
             note="Hardware mute latch: toggles on each press, powers up un-muted"),
        cap("C33", "100nF", 14.9, 34.7, 90, "GND", "+3V3"),
        resistor("R16", "100k", 6.3, 33.3, 0, "+3V3", "MUTE_POR"),
        cap("C32", "100nF", 6.3, 34.8, 0, "MUTE_POR"),
        resistor("R17", "10k", 6.3, 36.3, 0, "+3V3", "MUTE_SET_N"),
        resistor("R18", "100k", 11.0, 38.0, 0, "MIC_OFF", "MUTE_STATE"),
        Part("Q1", "AO3401A", SOT23, 9.7, 16.5, 0, nets={"1": "MIC_OFF", "2": "+3V3", "3": "VMIC"}, lcsc="C15127",
             note="Microphone supply switch"),
        cap("C35", "1uF", 9.4, 19.2, 0, "VMIC"),
        resistor("R19", "10k", 9.4, 20.7, 0, "VMIC", "GND"),
        Part("U9", "SN74LVC1G125DBVR", SOT23_5, 9.4, 10.9, 0, lcsc="C23654",
             nets={"1": "MIC_OFF", "2": "PDM_CLK_S3", "3": "GND", "4": "PDM_CLK_G", "5": "+3V3"},
             note="Microphone clock gate (high-Z when muted)"),
        cap("C36", "100nF", 9.4, 13.5, 0, "GND", "+3V3"),
    ]


def _link() -> list[Part]:
    header_nets = {str(i + 1): net for i, net in enumerate(LINK_PINS)}
    return [
        Part("J4", "TOP_LINK", "Connector_PinHeader_2.54mm:PinHeader_1x10_P2.54mm_Vertical", LINK_X, LINK_Y0, 0,
             nets=header_nets, assemble=False, note="10 wires to the top board, soldered in order"),
        resistor("R21", "33R", 5.2, 14.15, 90, "PDM_CLK", "PDM_CLK_G"),
        resistor("R22", "10k", 5.2, 17.15, 90, "GND", "PDM_CLK"),
        resistor("R20", "33R", 6.7, 14.15, 90, "LED_DATA", "LED_DATA_S3"),
        resistor("R23", "100k", 6.7, 17.15, 90, "GND", "PDM_DAT"),
        resistor("R13", "4.7k", 5.2, 20.15, 90, "I2C_SDA", "+3V3"),
        resistor("R14", "4.7k", 6.7, 20.15, 90, "I2C_SCL", "+3V3"),
    ]


def _holes() -> list[Hole]:
    return [Hole(x, YC + dy, MAIN.hole_drill, MAIN.hole_land, "GND", f"H{i + 1}") for i, (x, dy) in enumerate(MAIN.holes)]


def _texts() -> list[SilkText]:
    texts = [SilkText(label, 8.0, LINK_Y0 + i * LINK_PITCH, 1.0, "B.SilkS") for i, label in enumerate(LINK_LABELS)]
    texts += [
        SilkText("GH-REVIVE MAIN v1.0", 26.0, 44.0, 1.0, "B.SilkS", rot=-7.0),
        SilkText("16.5V  + AU CENTRE", 86.0, 19.5, 0.9, "B.SilkS"),
        SilkText("VERIFIER POLARITE", 86.0, 29.5, 0.9, "B.SilkS"),
        SilkText("1", 4.6, LINK_Y0 - 1.6, 0.9, "F.SilkS"),
        SilkText("SPK", 88.4, 17.9, 0.7, "F.SilkS"),
    ]
    return texts


def _keepouts() -> list[Keepout]:
    copper = ("F.Cu", "B.Cu")
    return [
        Keepout(((15.0, -1.0), (34.0, -1.0), (34.0, 9.7), (15.0, 9.7)), copper, "S3 antenna"),
        Keepout(((36.6, 36.2), (55.4, 36.2), (55.4, 50.0), (36.6, 50.0)), copper, "BT antenna"),
    ]


def build_spec() -> BoardSpec:
    everything = ((-2.0, -2.0), (MAIN.length + 2.0, -2.0), (MAIN.length + 2.0, MAIN.width + 2.0), (-2.0, MAIN.width + 2.0))
    parts = (_mcu() + _bluetooth() + _power_input() + _buck_5v() + _buck_3v3() + _usb() + _amplifier() + _mute()
             + _link())
    return BoardSpec(
        name="gh_mainboard",
        title="GH-Revive main board",
        layers=2,  # 4 layers cost ~28 $ at JLC for this size (engineering fee), 2 layers ~7 $
        origin=(60.0, 60.0),
        outline=list(_outline()),
        parts=parts,
        holes=_holes(),
        netclasses=[
            NetClass("Default", 0.2, 0.15, 0.6, 0.3, ()),
            NetClass("Ground", 0.3, 0.15, 0.6, 0.3, ("GND",)),
            NetClass("Power", 0.4, 0.15, 0.6, 0.3, ("+5V", "SW_3V3")),
            NetClass("Rail3V3", 0.3, 0.15, 0.6, 0.3, ("+3V3", "VMIC")),  # < 0.7 A peak; 0.3 mm keeps 2 layers routable
            NetClass("Usb", 0.3, 0.15, 0.6, 0.3, ("VBUS",)),  # enters the 0.5 mm pitch USB-C VBUS pads
            # 0.45 mm still enters the 0.65 mm pitch TAS5805M pads; ~1.6 A rms per side at 10 W / 4 ohm
            NetClass("HighCurrent", 0.45, 0.15, 0.8, 0.4,
                     ("PVDD", "VIN_RAW", "SW_5V", "SPK_P", "SPK_N", "OUT_A_P", "OUT_A_N")),
        ],
        keepouts=_keepouts(),
        post_zones=[
            CopperZone("GND", "F.Cu", everything, clearance=0.3, solid_pads=True, name="GND pour F"),
            CopperZone("GND", "B.Cu", everything, clearance=0.3, solid_pads=True, name="GND pour B"),
        ],
        texts=_texts(),
        signal_layers=("F.Cu", "B.Cu"),
        strip_footprint_keepouts=("U1", "U2"),
    )
