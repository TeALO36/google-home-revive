"""Cost estimate (TTC, France) of boards fully assembled by JLCPCB (nothing to solder but the link wires).

    "C:/Program Files/KiCad/10.0/bin/python.exe" tools/quote_assembled.py [--sets 2] [--usd-eur 0.86]

Fees: JLCPCB "PCB Assembly Cost" help page (updated 2026-10-22). Main board = Economic PCBA (one side), top board =
Standard PCBA double side (the LEDs sit on the bottom face). JLC assembles at least 2 boards of a design.
Part prices: JLC stock prices from the local parts database (the IM69D130 microphones are in JLC stock).
Bare boards and shipping: JLCPCB instant quote, 2026-11-14.
"""
from __future__ import annotations

import argparse
import math
import sqlite3
from dataclasses import dataclass

from quote import BOMS, DB, PCB_FEES, REPO, VAT, read_needs

OUT = REPO / "docs" / "devis_assemble.md"
SMT_JOINT, XRAY_UNIT, EXTENDED_FEEDER_ECO, FEEDER_STD = 0.0016, 1.64, 3.07, 1.53
SMT_COUPON = 9.0  # monthly JLC coupon, covers the 8.18 USD Economic setup fee (one coupon per order)
SHIPPING = 24.0  # USD, DHL Express to France (order above the 150 USD limit of Global Standard Direct)
# jlcpcb.com/partdetail, 2026-11-14, USD for 1-9 pieces (extended parts): S3 module missing from the local database,
# IM69D130 stock low (131 orderable): check before ordering
LIVE_JLC_PRICES = {"C2913202": 5.3485, "C536262": 3.1414}
CARRIER_FEE_EUR = 12.0  # import clearance fee charged by the carrier above 150 EUR (VAT paid on delivery)


@dataclass(frozen=True)
class Assembly:
    name: str
    boms: tuple[str, ...]
    economic: bool
    joints: int  # solder joints per board
    xray_parts: int  # leadless parts per board (modules, LGA microphones, QFN)


# every part of the board soldered by JLC: factory BOM + hand-soldered list
ASSEMBLIES = (
    Assembly("Carte mere - Economic PCBA, 1 face", BOMS[0:2], True, 420, 3),
    Assembly("Carte du dessus - Standard PCBA, 2 faces", BOMS[2:4], False, 140, 3),
)


def _jlc_part(con: sqlite3.Connection, lcsc: str, qty: int) -> tuple[float, bool]:
    if lcsc in LIVE_JLC_PRICES:
        return LIVE_JLC_PRICES[lcsc], False
    row = con.execute("SELECT price, basic, preferred FROM jlc_components WHERE lcsc = ?", (int(lcsc[1:]),)).fetchone()
    if not row or not row[0]:
        raise KeyError(f"{lcsc} is not in the JLC parts database")
    tiers = [(int(span.split("-")[0]), float(price))
             for span, _, price in (tier.partition(":") for tier in row[0].split(","))]
    unit = next((price for low, price in reversed(tiers) if qty >= low), tiers[0][1])
    return unit, bool(row[1] or row[2])


def _parts(con: sqlite3.Connection, boms: tuple[str, ...], sets: int) -> tuple[float, int, int]:
    """(parts cost, extended part types, part types); JLC adds attrition on cheap passives."""
    needs, _ = read_needs(sets, boms)
    cost, extended = 0.0, 0
    for lcsc, needed in needs.items():
        qty = max(math.ceil(needed * 1.1), needed + 2)
        unit, basic = _jlc_part(con, lcsc, qty)
        cost += (qty if unit < 0.1 else needed) * unit
        extended += 0 if basic else 1
    return cost, extended, len(needs)


def board_cost(con: sqlite3.Connection, job: Assembly, sets: int) -> dict[str, float]:
    parts, extended, types = _parts(con, job.boms, sets)
    fees = {"Mise en route": 8.18 if job.economic else 51.12, "Pochoir": 1.53 if job.economic else 16.42,
            "Soudures": job.joints * sets * SMT_JOINT, "Radiographie (pieces sans pattes)": job.xray_parts * sets * XRAY_UNIT}
    if job.economic:
        fees[f"Chargement pieces etendues ({extended} x {EXTENDED_FEEDER_ECO} $)"] = extended * EXTENDED_FEEDER_ECO
    else:
        fees[f"Chargement de toutes les pieces ({types} x {FEEDER_STD} $)"] = types * FEEDER_STD
        fees["Emballage"] = 0.5
    fees["Composants (stock JLC)"] = parts
    return fees


def _board_table(name: str, fees: dict[str, float], usd_eur: float) -> list[str]:
    rows = [f"### {name}", "", "| Poste | USD | EUR HT |", "|---|---:|---:|"]
    rows += [f"| {k} | {v:.2f} | {v * usd_eur:.2f} |" for k, v in fees.items()]
    total = sum(fees.values())
    return rows + [f"| **Sous-total** | **{total:.2f}** | **{total * usd_eur:.2f}** |", ""]


def _totals(assembly_usd: float, sets: int, usd_eur: float) -> list[str]:
    pcb = sum(fee for _, fee in PCB_FEES)
    ht = (assembly_usd + pcb - SMT_COUPON + SHIPPING) * usd_eur
    ttc = ht * (1 + VAT) + CARRIER_FEE_EUR
    return ["## Total", "", "| Poste | USD | EUR |", "|---|---:|---:|",
            f"| Assemblage + composants (2 cartes x {sets} jeux) | {assembly_usd:.2f} | {assembly_usd * usd_eur:.2f} |",
            f"| PCB nus (5 de chaque, 2 couches) | {pcb:.2f} | {pcb * usd_eur:.2f} |",
            f"| Coupon SMT mensuel JLC | -{SMT_COUPON:.2f} | -{SMT_COUPON * usd_eur:.2f} |",
            f"| Livraison DHL Express (France) | {SHIPPING:.2f} | {SHIPPING * usd_eur:.2f} |",
            f"| **Total HT** | **{ht / usd_eur:.2f}** | **{ht:.2f}** |",
            f"| TVA {int(VAT * 100)} % (payee a la livraison) | {ht * VAT / usd_eur:.2f} | {ht * VAT:.2f} |",
            f"| Frais de dedouanement transporteur | {CARRIER_FEE_EUR / usd_eur:.2f} | {CARRIER_FEE_EUR:.2f} |",
            f"| **Total TTC** | **{ttc / usd_eur:.2f}** | **{ttc:.2f}** |",
            f"| Soit par appareil ({sets} jeux) | {ttc / usd_eur / sets:.2f} | {ttc / sets:.2f} |", ""]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sets", type=int, default=2, help="assembled sets (JLC minimum: 2)")
    parser.add_argument("--usd-eur", type=float, default=0.86)
    args = parser.parse_args()
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    lines = ["# Devis estimatif - cartes assemblees par JLCPCB", "",
             f"{args.sets} jeux assembles (minimum JLC : 2), 5 PCB nus de chaque carte. Taux USD->EUR : "
             f"{args.usd_eur}. Grille tarifaire JLCPCB du 2026-10-22, prix des pieces du stock JLC.", ""]
    total = 0.0
    for job in ASSEMBLIES:
        fees = board_cost(con, job, args.sets)
        lines += _board_table(job.name, fees, args.usd_eur)
        total += sum(fees.values())
    text = "\n".join(lines + _totals(total, args.sets, args.usd_eur))
    OUT.write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
