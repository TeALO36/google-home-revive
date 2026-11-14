"""Cost estimate (TTC, France) of ONE set, self-assembled: bare PCBs from JLCPCB + components from LCSC.

    "C:/Program Files/KiCad/10.0/bin/python.exe" tools/quote.py [--sets 1] [--usd-eur 0.86]

Bare-board and shipping prices were read on the JLCPCB instant quote (cart.jlcpcb.com/quote) on 2026-11-14,
2 layers, 1.6 mm, HASL, tented vias, 5 pcs (JLC minimum), destination France. Component minimum quantities and price
breaks come from tools/data/lcsc_prices.json (read on lcsc.com the same day); a part missing from it falls back to the
local JLCPCB parts database with a MOQ guessed by MOQ_RULES. Re-check everything at checkout.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sqlite3
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DB = Path.home() / ".kicad-mcp/data/jlcparts_cache/cdfer.sqlite3"
OUT = REPO / "docs" / "devis.md"
# JLC BOM (factory-soldered parts) + hand-soldered list of each board; a missing file means "no such part"
BOMS = tuple(f"hardware/{board}/fab/gh_{board}_{kind}.csv"
             for board in ("mainboard", "topboard") for kind in ("bom", "hand_bom"))
SNAPSHOT = REPO / "tools" / "data" / "lcsc_prices.json"  # LCSC MOQ + price breaks read on lcsc.com, 2026-11-14
# LCSC sells the IM69D130 only by 10 (third-party stock, ~52 USD): bought apart, at the unit, from a distributor
EXTERNAL_PARTS = {"C536262": "IM69D130 (Mouser / DigiKey / Farnell, a l'unite)"}
MOQ_RULES = ((0.01, 100), (0.1, 20), (0.5, 5))  # unit price below X USD -> buy at least N pieces
PCB_FEES = (("Carte mere 2 couches 107.6 x 49 mm, 5 pcs", 6.60), ("Carte du dessus 2 couches D74.8 mm, 5 pcs", 4.00))
JLC_SHIPPING = 6.73  # USD, Global Standard Direct Line to France (<= 1.5 kg, <= 150 USD), 10-12 working days
LCSC_SHIPPING_COMBINED = 5.0  # USD, estimate: LCSC parcel merged with the JLC order (cost recalculated by LCSC)
PARCEL_TAX_EUR = 2.0  # French tax on low-value parcels (<= 150 EUR) since 2026-03-01, one merged parcel
VAT = 0.20  # collected at checkout (IOSS) for parcels <= 150 EUR: no carrier clearance fee


@dataclass(frozen=True)
class Line:
    lcsc: str
    comment: str
    needed: int
    bought: int
    unit: float

    @property
    def cost(self) -> float:
        return self.bought * self.unit


@dataclass(frozen=True)
class Offer:
    """LCSC selling conditions: minimum order (also the order multiple) and price breaks [(qty, unit USD)]."""

    moq: int
    tiers: tuple[tuple[int, float], ...]

    def unit(self, qty: int) -> float:
        return next((price for low, price in reversed(self.tiers) if qty >= low), self.tiers[0][1])

    def buy(self, needed: int) -> int:
        return max(self.moq, math.ceil(needed / self.moq) * self.moq)


def _snapshot_offers() -> dict[str, Offer]:
    if not SNAPSHOT.exists():
        return {}
    data = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    return {code: Offer(int(item["moq"]), tuple((int(q), float(p)) for q, p in item["tiers"]))
            for code, item in data.items() if not code.startswith("_")}


def _database_offer(con: sqlite3.Connection | None, lcsc: str) -> Offer:
    """Parts missing from the LCSC snapshot: JLC price breaks, MOQ guessed from the unit price."""
    row = con.execute("SELECT price FROM jlc_components WHERE lcsc = ?", (int(lcsc[1:]),)).fetchone() if con else None
    if not row or not row[0]:
        raise KeyError(f"no price for {lcsc}: add it to {SNAPSHOT.name}")
    tiers = tuple((int(span.split("-")[0]), float(price))
                  for span, _, price in (tier.partition(":") for tier in row[0].split(",")))
    moq = next((count for limit, count in MOQ_RULES if tiers[0][1] < limit), 1)
    return Offer(moq, tiers)


def read_needs(sets: int, boms: tuple[str, ...] = BOMS) -> tuple[Counter[str], dict[str, str]]:
    """Pieces needed per LCSC code over the given BOMs (shared passives are bought once)."""
    needs: Counter[str] = Counter()
    comments: dict[str, str] = {}
    for bom in boms:
        if not (REPO / bom).exists():
            continue
        with (REPO / bom).open(encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                needs[row["LCSC Part #"]] += len(row["Designator"].split(",")) * sets
                comments[row["LCSC Part #"]] = row["Comment"]
    return needs, comments


def price_lines(sets: int, boms: tuple[str, ...] = BOMS,
                skip: frozenset[str] = frozenset(EXTERNAL_PARTS)) -> list[Line]:
    """LCSC order lines (minimum quantities applied) for the given BOMs, parts in `skip` excluded."""
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True) if DB.exists() else None
    offers = _snapshot_offers()
    needs, comments = read_needs(sets, boms)
    lines = []
    for lcsc, needed in needs.items():
        if lcsc in skip:
            continue
        offer = offers.get(lcsc) or _database_offer(con, lcsc)
        bought = offer.buy(needed)
        lines.append(Line(lcsc, comments[lcsc], needed, bought, offer.unit(bought)))
    return sorted(lines, key=lambda line: line.cost, reverse=True)


def _parts_table(lines: list[Line], usd_eur: float) -> list[str]:
    rows = ["## Composants (LCSC)", "", "| Piece | LCSC | Besoin | Achete | USD |", "|---|---|---:|---:|---:|"]
    rows += [f"| {l.comment} | {l.lcsc} | {l.needed} | {l.bought} | {l.cost:.2f} |" for l in lines]
    total = sum(l.cost for l in lines)
    rows += [f"| **Total composants** | | | | **{total:.2f}** ({total * usd_eur:.2f} EUR) |", ""]
    return rows


def _totals(parts_usd: float, sets: int, usd_eur: float, external_eur: float) -> list[str]:
    pcb = sum(fee for _, fee in PCB_FEES)
    shipping = JLC_SHIPPING + LCSC_SHIPPING_COMBINED
    ht = (pcb + parts_usd + shipping) * usd_eur
    china_ttc = ht * (1 + VAT) + PARCEL_TAX_EUR
    ttc = china_ttc + external_eur
    rows = ["## Total", "", "| Poste | USD | EUR |", "|---|---:|---:|"]
    rows += [f"| PCB nus : {name} | {fee:.2f} | {fee * usd_eur:.2f} |" for name, fee in PCB_FEES]
    rows += [f"| Composants | {parts_usd:.2f} | {parts_usd * usd_eur:.2f} |",
             f"| Livraison JLC Global Standard Direct (France) | {JLC_SHIPPING:.2f} | {JLC_SHIPPING * usd_eur:.2f} |",
             f"| Supplement colis LCSC fusionne (estimation) | {LCSC_SHIPPING_COMBINED:.2f} | "
             f"{LCSC_SHIPPING_COMBINED * usd_eur:.2f} |",
             f"| **Total HT** | | **{ht:.2f}** |",
             f"| TVA {int(VAT * 100)} % (percue a la commande, IOSS) | | {ht * VAT:.2f} |",
             f"| Taxe petits colis France | | {PARCEL_TAX_EUR:.2f} |",
             f"| **Sous-total TTC commande JLC + LCSC** | | **{china_ttc:.2f}** |",
             *[f"| {name} x{2 * sets}, TTC port compris (estimation, --external-eur) | | {external_eur:.2f} |"
               for name in EXTERNAL_PARTS.values()],
             f"| **Total TTC** | | **{ttc:.2f}** |",
             f"| Soit par jeu | | {ttc / sets:.2f} |", ""]
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sets", type=int, default=1, help="number of complete sets (main + top board)")
    parser.add_argument("--usd-eur", type=float, default=0.86)
    parser.add_argument("--external-eur", type=float, default=10.0,
                        help="TTC cost, shipping included, of the parts bought apart (IM69D130 microphones)")
    args = parser.parse_args()
    lines = price_lines(args.sets)
    text = "\n".join(
        ["# Devis estimatif - 1 jeu en kit (PCB nus JLCPCB + composants LCSC, assemblage maison)", "",
         f"{args.sets} jeu(x). Taux USD->EUR : {args.usd_eur}. PCB et livraison : devis en ligne JLCPCB du "
         "2026-11-14. Composants : stock LCSC/JLC au moment de l'etude. 4 PCB nus de chaque carte restent en "
         "reserve (minimum de commande JLC = 5).", ""]
        + _parts_table(lines, args.usd_eur)
        + _totals(sum(l.cost for l in lines), args.sets, args.usd_eur, args.external_eur))
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
