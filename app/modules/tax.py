from dataclasses import dataclass
from typing import List


@dataclass
class IrpefBracket:
    up_to: float
    rate: float


def italian_irpef_2025() -> List[IrpefBracket]:
    return [
        IrpefBracket(up_to=28_000, rate=0.23),
        IrpefBracket(up_to=50_000, rate=0.35),
        IrpefBracket(up_to=float("inf"), rate=0.43),
    ]


def calc_irpef_tax(income_eur: float, brackets: List[IrpefBracket]) -> float:
    remaining = income_eur
    prev_cap = 0.0
    tax = 0.0
    for b in brackets:
        span = min(remaining, b.up_to - prev_cap)
        if span > 0:
            tax += span * b.rate
            remaining -= span
            prev_cap = b.up_to
        if remaining <= 0:
            break
    return max(tax, 0.0)


def add_region_muni_surcharge(tax_eur: float, regional_pct: float, municipal_pct: float) -> float:
    return tax_eur * (1 + regional_pct + municipal_pct)


def flat_7_percent_tax(amount_eur: float, enabled: bool) -> float:
    return amount_eur * 0.07 if enabled else 0.0


def tax_at_irpef_with_surcharges(amount_eur: float, brackets: List[IrpefBracket],
                                 regional_pct: float, municipal_pct: float) -> float:
    base = calc_irpef_tax(amount_eur, brackets)
    return add_region_muni_surcharge(base, regional_pct, municipal_pct)


def gbp_to_eur(amount_gbp: float, fx: float) -> float:
    return amount_gbp * fx


def eur_to_gbp(amount_eur: float, fx: float) -> float:
    return amount_eur / fx