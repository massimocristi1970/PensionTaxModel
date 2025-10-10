import pandas as pd
from typing import Dict, List


def combine_series_to_df(years: List[int], data: Dict[str, List[float]]) -> pd.DataFrame:
    df = pd.DataFrame({"Year": years})
    for k, v in data.items():
        df[k] = v
    return df


def add_real_terms(df: pd.DataFrame, cols: List[str], inflation_pct: float) -> pd.DataFrame:
    df = df.copy()
    infl = (1 + inflation_pct / 100.0)
    df["Inflation_Index"] = [infl ** i for i in range(len(df))]
    for c in cols:
        df[f"{c}_real"] = df[c] / df["Inflation_Index"]
    return df