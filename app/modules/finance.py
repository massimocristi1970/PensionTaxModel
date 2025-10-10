from dataclasses import dataclass
from typing import Dict, Tuple, Callable


@dataclass
class StrategyInputs:
    allocation_pct: float
    gross_yield_pct: float
    mgmt_fee_pct: float
    growth_pct: float
    is_foreign_source: bool


def annual_investment_step(
    capital: float,
    strategy: StrategyInputs,
    in_regime_7pct: bool,
    tax_func_post10: Callable[[float], float],
) -> Tuple[float, float, float, float]:
    gross_income = capital * (strategy.gross_yield_pct / 100.0)
    fees = capital * (strategy.mgmt_fee_pct / 100.0)
    income_after_fees = max(gross_income - fees, 0.0)

    if in_regime_7pct and strategy.is_foreign_source:
        tax = income_after_fees * 0.07
    else:
        tax = tax_func_post10(income_after_fees) if income_after_fees > 0 else 0.0

    net_income = max(income_after_fees - tax, 0.0)
    capital_growth = capital * (strategy.growth_pct / 100.0)
    end_capital = capital + capital_growth
    return end_capital, net_income, gross_income, tax


def blend_allocations(strategies: Dict[str, StrategyInputs]) -> float:
    return sum(s.allocation_pct for s in strategies.values())


def weighted_starting_capital(total_capital: float, strategies: Dict[str, StrategyInputs]) -> Dict[str, float]:
    alloc_sum = blend_allocations(strategies)
    if alloc_sum <= 0:
        return {k: 0.0 for k in strategies}
    return {k: total_capital * (s.allocation_pct / alloc_sum) for k, s in strategies.items()}