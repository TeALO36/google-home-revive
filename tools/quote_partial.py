"""Cost estimate (TTC, France) of the retained order: JLCPCB solders the fragile parts, the user the rest.

    "C:/Program Files/KiCad/10.0/bin/python.exe" tools/quote_partial.py [--usd-eur 0.86] [--desktop-app]

- Main board: Economic PCBA (one side) of `gh_mainboard_bom.csv` / `_cpl.csv`: TAS5805M (PowerPAD), USB-C (pins under
  the body) and every 0603 / 0805 / SMA passive. The modules, SOT-23 / TSSOP-8 ICs, inductors, electrolytic and speaker
  connector of `gh_mainboard_hand_bom.csv` are bought at LCSC and soldered by the user.
- Top board: Economic PCBA (one side, F) of `gh_topboard_bom.csv` / `_cpl.csv`: IM69D130 microphones, MPR121 (QFN 0.4 mm)
  and their passives. LEDs and level shifter (`gh_topboard_hand_bom.csv`): LCSC, soldered by the user.
JLC assembles at least 2 boards of each design: the second assembled set is a spare. One SMT coupon per order.
One order (JLC + LCSC parcel merged) under 150 EUR: VAT collected at checkout, cheap shipping, no clearance fee.
"""
from __future__ import annotations

import argparse
import sqlite3

from quote import (DB, JLC_SHIPPING, LCSC_SHIPPING_COMBINED, PARCEL_TAX_EUR, PCB_FEES, REPO, VAT, _parts_table,
                   price_lines)
from quote_assembled import SMT_COUPON, Assembly, board_cost

OUT = REPO / "docs" / "devis_partiel.md"
MAIN_FACTORY = Assembly("Carte mere - Economic PCBA, 1 face (TAS5805M, USB-C, passifs)",
                        ("hardware/mainboard/fab/gh_mainboard_bom.csv",), True, 174, 0)
TOP_FACTORY = Assembly("Carte du dessus - Economic PCBA, face F seule (micros, MPR121, passifs)",
                       ("hardware/topboard/fab/gh_topboard_bom.csv",), True, 75, 3)
HAND_BOMS = ("hardware/mainboard/fab/gh_mainboard_hand_bom.csv", "hardware/topboard/fab/gh_topboard_hand_bom.csv")
ASSEMBLED_SETS = 2  # JLC minimum
DESKTOP_APP_SAVING = 4.0  # USD, same 2 bare boards ordered from the JLCPCB desktop application (2026-11-14)


FACTORY = (MAIN_FACTORY, TOP_FACTORY)


def _factory_table(job: Assembly, fees: dict[str, float], usd_eur: float) -> list[str]:
    rows = [f"## JLCPCB : {job.name}, {ASSEMBLED_SETS} cartes", "", "| Poste | USD | EUR HT |", "|---|---:|---:|"]
    rows += [f"| {name} | {value:.2f} | {value * usd_eur:.2f} |" for name, value in fees.items()]
    total = sum(fees.values())
    return rows + [f"| **Sous-total** | **{total:.2f}** | **{total * usd_eur:.2f}** |", ""]


def _ttc_eur(factory: float, parts: float, pcb: float, usd_eur: float) -> tuple[float, float]:
    """(total HT in USD, total TTC in EUR) of one order."""
    ht_usd = factory - SMT_COUPON + parts + pcb + JLC_SHIPPING + LCSC_SHIPPING_COMBINED
    return ht_usd, ht_usd * usd_eur * (1 + VAT) + PARCEL_TAX_EUR


def _two_devices(factory: float, parts_two: float, pcb: float, usd_eur: float) -> list[str]:
    """The spare assembled set becomes a second device: only a second LCSC kit is added to the order."""
    ht_usd, ttc = _ttc_eur(factory, parts_two, pcb, usd_eur)
    return ["## Variante : 2 appareils dans la meme commande", "",
            "Le jeu de cartes de reserve devient un 2e appareil : seul un 2e kit LCSC s'ajoute.", "",
            "| Poste | USD | EUR |", "|---|---:|---:|",
            f"| Composants LCSC (2 jeux) | {parts_two:.2f} | {parts_two * usd_eur:.2f} |",
            f"| **Total TTC de la commande** | **{ttc / usd_eur:.2f}** | **{ttc:.2f}** |",
            f"| **Par appareil** | **{ttc / usd_eur / 2:.2f}** | **{ttc / 2:.2f}** |", "",
            f"(Total HT {ht_usd:.2f} USD, toujours sous le seuil de 150 EUR : TVA a la commande, pas de frais de"
            " dedouanement.)", ""]


def _totals(factory: float, parts: float, pcb: float, usd_eur: float) -> list[str]:
    shipping = JLC_SHIPPING + LCSC_SHIPPING_COMBINED
    ht_usd, ttc = _ttc_eur(factory, parts, pcb, usd_eur)
    rows = ["## Total (1 appareil complet + 1 jeu de cartes pre-assemblees en reserve)", "",
            "| Poste | USD | EUR |", "|---|---:|---:|",
            f"| Assemblage JLC des 2 cartes (x{ASSEMBLED_SETS} jeux) | {factory:.2f} | {factory * usd_eur:.2f} |",
            f"| Coupon SMT mensuel JLC | -{SMT_COUPON:.2f} | -{SMT_COUPON * usd_eur:.2f} |",
            f"| Composants LCSC a souder soi-meme (1 jeu) | {parts:.2f} | {parts * usd_eur:.2f} |",
            f"| PCB nus (5 de chaque, 2 couches) | {pcb:.2f} | {pcb * usd_eur:.2f} |",
            f"| Livraison JLC + colis LCSC fusionne | {shipping:.2f} | {shipping * usd_eur:.2f} |",
            f"| **Total HT** | **{ht_usd:.2f}** | **{ht_usd * usd_eur:.2f}** |",
            f"| TVA {int(VAT * 100)} % (percue a la commande) | {ht_usd * VAT:.2f} | {ht_usd * usd_eur * VAT:.2f} |",
            f"| Taxe petits colis France | | {PARCEL_TAX_EUR:.2f} |",
            f"| **Total TTC** | **{ttc / usd_eur:.2f}** | **{ttc:.2f}** |", ""]
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--usd-eur", type=float, default=0.86)
    parser.add_argument("--desktop-app", action="store_true", help="bare boards priced on the JLC desktop app")
    args = parser.parse_args()
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    fees = [board_cost(con, job, ASSEMBLED_SETS) for job in FACTORY]
    lines = price_lines(1, HAND_BOMS, frozenset())
    parts_two = sum(line.cost for line in price_lines(2, HAND_BOMS, frozenset()))
    pcb = sum(fee for _, fee in PCB_FEES) - (DESKTOP_APP_SAVING if args.desktop_app else 0.0)
    factory, parts = sum(sum(board.values()) for board in fees), sum(line.cost for line in lines)
    factory_tables = [row for job, board in zip(FACTORY, fees) for row in _factory_table(job, board, args.usd_eur)]
    text = "\n".join(
        ["# Devis estimatif - pieces sensibles soudees en usine, reste soude a la main", "",
         f"Taux USD->EUR : {args.usd_eur}. Grille PCBA JLCPCB du 2026-10-22, PCB et livraison du 2026-11-14 "
         f"({'application de bureau' if args.desktop_app else 'site web'}), composants LCSC avec minimums de "
         "commande reels.", ""]
        + factory_tables
        + _parts_table(lines, args.usd_eur)
        + _totals(factory, parts, pcb, args.usd_eur)
        + _two_devices(factory, parts_two, pcb, args.usd_eur))
    OUT.write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
