"""Part catalogue: KiCad footprints and JLCPCB (LCSC) references, plus small Part factories."""
from __future__ import annotations

from .model import Part

R0603 = "Resistor_SMD:R_0603_1608Metric"
C0603 = "Capacitor_SMD:C_0603_1608Metric"
C0805 = "Capacitor_SMD:C_0805_2012Metric"
C1206 = "Capacitor_SMD:C_1206_3216Metric"
CP_ELEC = "gh_revive:CAP-SMD_BD6.3-L6.6-W6.6-RD"  # pad 1 = +
SOT23 = "Package_TO_SOT_SMD:SOT-23"
SOT23_5 = "Package_TO_SOT_SMD:SOT-23-5"
SOT23_6 = "Package_TO_SOT_SMD:SOT-23-6"
TSSOP8 = "Package_SO:TSSOP-8_3x3mm_P0.65mm"
TAS5805_FP = "Package_SO:TSSOP-28-1EP_4.4x9.7mm_P0.65mm_EP3.4x9.7mm_Mask3.1x4.05mm_ThermalVias"
D_SMA = "Diode_SMD:D_SMA"
D_SOD123 = "Diode_SMD:D_SOD-123"
L_4020 = "gh_revive:IND-SMD_L4.0-W4.0"
TEST_PAD = "gh_revive:GH_TestPad_1.5mm"
ELECTRODE_TAP = "gh_revive:GH_ElectrodeTap"
WIRE_PADS_10 = "gh_revive:GH_WirePads_1x10_P2.54mm"
# 3.5 x 3.5 mm, J-leads outside the body (iron-solderable): 1 VDD, 2 DOUT, 3 GND, 4 DIN
LED_MINI_V3J = "gh_revive:LED-SMD_4P-L3.5-W3.5-P1.80-LS6.2_WS2812B-MINI-V3J"
MIC_IM69D130 = "gh_revive:GH_MIC_IM69D130"  # 1 DATA, 2 VDD, 3 CLK, 4 SELECT, 5 GND (seal ring)
QFN20_MPR121 = "gh_revive:GH_QFN20_MPR121"
LCSC_WS2812B_MINI_V3J = "C22371519"
LCSC_IM69D130 = "C536262"  # SNR 69 dB(A), AOP 130 dB SPL: >= the original InvenSense INMP621 (65 dB(A))
LCSC_MPR121 = "C91322"
LCSC_AHCT1G125 = "C7484"

# value -> LCSC part number (JLCPCB basic parts wherever one exists)
RESISTORS = {
    "33R": "C23140", "1k": "C21190", "4.7k": "C23162", "5.1k": "C23186", "10k": "C25804", "22k": "C31850",
    "75k": "C23242", "100k": "C25803",
}
CAPS_0603 = {"100nF": "C14663", "470nF": "C1623", "1uF": "C15849"}
CAP_22UF_0805 = "C45783"  # 22 uF 25 V X5R
CAP_10UF_1206 = "C13585"  # 10 uF 50 V X5R
CAP_220UF_ELEC = "C696188"  # 220 uF 25 V, 6.3 x 7.7 mm
INDUCTORS_4020 = {"2.2uH": "C602029", "4.7uH": "C602031", "10uH": "C602032"}  # FHD4020S series, 4 x 4 x 2 mm


def resistor(ref: str, value: str, x: float, y: float, rot: float, net_a: str, net_b: str) -> Part:
    return Part(ref, value, R0603, x, y, rot, nets={"1": net_a, "2": net_b}, lcsc=RESISTORS[value])


def cap(ref: str, value: str, x: float, y: float, rot: float, net_a: str, net_b: str = "GND") -> Part:
    return Part(ref, value, C0603, x, y, rot, nets={"1": net_a, "2": net_b}, lcsc=CAPS_0603[value])


def cap_22u(ref: str, x: float, y: float, rot: float, net_a: str) -> Part:
    return Part(ref, "22uF/25V", C0805, x, y, rot, nets={"1": net_a, "2": "GND"}, lcsc=CAP_22UF_0805)


def cap_10u_50v(ref: str, x: float, y: float, rot: float, net_a: str) -> Part:
    return Part(ref, "10uF/50V", C1206, x, y, rot, nets={"1": net_a, "2": "GND"}, lcsc=CAP_10UF_1206)


def inductor(ref: str, value: str, x: float, y: float, rot: float, net_a: str, net_b: str) -> Part:
    return Part(ref, value, L_4020, x, y, rot, nets={"1": net_a, "2": net_b}, lcsc=INDUCTORS_4020[value])


def test_pad(ref: str, label: str, x: float, y: float, net: str) -> Part:
    return Part(ref, label, TEST_PAD, x, y, nets={"1": net}, assemble=False)
