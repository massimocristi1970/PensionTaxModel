import streamlit as st
import pandas as pd
import plotly.express as px
import os

from modules.tax import (
    italian_irpef_2025, calc_irpef_tax, add_region_muni_surcharge,
    tax_at_irpef_with_surcharges, gbp_to_eur
)
from modules.finance import StrategyInputs, annual_investment_step, weighted_starting_capital
from modules.utils import combine_series_to_df, add_real_terms

# ---- Page Setup ----
st.set_page_config(page_title="Retirement & 7% Regime Model", layout="wide")

# ---- Load custom CSS safely regardless of where the app is launched ----
css_path = os.path.join(os.path.dirname(__file__), "assets", "styles.css")
if os.path.exists(css_path):
    with open(css_path, "r", encoding="utf-8") as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)
else:
    st.warning("⚠️ styles.css not found in app/assets/. Using default Streamlit style.")

st.title("Retirement & Investment Model — Italy 7% Regime → Post-10 Years")
st.caption("Local model with editable assumptions and CSV export.")

# ---- Theme: auto-detect + manual override ----
try:
    import darkdetect
    system_dark = darkdetect.isDark()
except Exception:
    system_dark = False

default_index = 1 if system_dark else 0
theme_choice = st.sidebar.radio("🌓 Theme", ["Light", "Dark"], index=default_index)
theme_template = "plotly_dark" if theme_choice == "Dark" else "plotly_white"

# ---- Sidebar Inputs ----
st.sidebar.header("General Settings")
fx = st.sidebar.number_input(
    "FX: € per £",
    value=1.17, min_value=0.5, max_value=2.0, step=0.01,
    help="This sets the exchange rate used to convert your pensions and capital from pounds to euros."
)
inflation_pct = st.sidebar.number_input(
    "Inflation (annual, %)",
    value=2.0, min_value=0.0, max_value=15.0, step=0.1,
    help="Expected average inflation per year. Higher inflation reduces real purchasing power over time."
)

st.sidebar.header("Pensions (GBP)")
you_pension_gbp = st.sidebar.number_input(
    "Your annual pension (£)", value=30000, step=1000,
    help="Enter your annual pension income in pounds. This will be converted to euros using the FX rate."
)
wife_pension_gbp = st.sidebar.number_input(
    "Wife's annual pension (£)", value=20000, step=1000,
    help="Enter your spouse’s annual pension income in pounds. This is also converted to euros using the FX rate."
)

st.sidebar.header("Capital (GBP)")
starting_capital_gbp = st.sidebar.number_input(
    "Starting investable capital (£)", value=500000, step=10000,
    help="Total savings or inheritance you expect to invest at the start of retirement."
)

st.sidebar.header("Horizon")
years_in_7pct = st.sidebar.number_input(
    "Years in 7% regime", value=10, min_value=1, max_value=10,
    help="Number of years you plan to qualify for Italy’s 7% flat-tax regime on foreign income."
)
years_post = st.sidebar.number_input(
    "Years post-regime", value=10, min_value=1, max_value=40,
    help="How many years to simulate after the 7% regime ends (normal Italian tax applies)."
)

st.sidebar.header("Italian Progressive (post-regime)")
regional_surcharge = st.sidebar.number_input(
    "Regional add-on", value=0.01, step=0.005,
    help="Regional tax applied on top of standard Italian income tax after the 7% regime ends."
)
municipal_surcharge = st.sidebar.number_input(
    "Municipal add-on", value=0.005, step=0.005,
    help="Local municipal tax rate added to IRPEF after the 7% regime period."
)
st.sidebar.caption("IRPEF brackets set in code; surcharges applied here.")

# ---- Investment strategies ----
st.sidebar.header("Strategies (sum ≈ 100%)")
colA, colB = st.sidebar.columns(2)
with colA:
    alloc_cash = st.number_input("Cash Allocation %", 40.0, help="Percent of your capital held as cash or savings.")
    yld_cash = st.number_input("Cash yield %", 3.5, help="Annual interest rate earned on cash savings.")
    fee_cash = st.number_input("Cash fee %", 0.1, help="Bank or platform fees on your cash holdings.")
    grow_cash = st.number_input("Cash growth %", 0.0, help="Long-term growth of cash (usually 0%).")
with colB:
    alloc_bond = st.number_input("Bonds Allocation %", 30.0, help="Percent of your capital invested in bonds.")
    yld_bond = st.number_input("Bonds yield %", 3.8, help="Expected annual return from bond interest.")
    fee_bond = st.number_input("Bonds fee %", 0.2, help="Management or platform fee for bond investments.")
    grow_bond = st.number_input("Bonds growth %", 0.0, help="Capital growth of bonds beyond interest returns.")

colC, colD = st.sidebar.columns(2)
with colC:
    alloc_equity = st.number_input("Equity Allocation %", 20.0, help="Percent of capital in stocks or shares.")
    yld_equity = st.number_input("Equity yield %", 2.0, help="Dividend yield or income return from shares.")
    fee_equity = st.number_input("Equity fee %", 0.4, help="Typical investment management fee for equities.")
    grow_equity = st.number_input("Equity growth %", 5.0, help="Expected average annual price growth of equities.")
with colD:
    alloc_rental = st.number_input("Rental Allocation %", 10.0, help="Percent of capital invested in rental property.")
    yld_rental = st.number_input("Rental net yield %", 4.0, help="Net annual income after property expenses.")
    fee_rental = st.number_input("Rental maint. %", 0.5, help="Maintenance and management costs for rental property.")
    grow_rental = st.number_input("Property growth %", 2.0, help="Expected annual capital appreciation of property.")
    is_rental_foreign = st.checkbox(
        "Treat rental as foreign-source (eligible for 7%)", value=False,
        help="Tick this if your rental property is outside Italy (so it qualifies for the 7% tax rate)."
    )

# ---- Build strategy dict ----
strategies = {
    "Cash": StrategyInputs(alloc_cash, yld_cash, fee_cash, grow_cash, True),
    "Bonds": StrategyInputs(alloc_bond, yld_bond, fee_bond, grow_bond, True),
    "Equity": StrategyInputs(alloc_equity, yld_equity, fee_equity, grow_equity, True),
    "Rental": StrategyInputs(alloc_rental, yld_rental, fee_rental, grow_rental, is_rental_foreign),
}

alloc_sum = sum(s.allocation_pct for s in strategies.values())
if abs(alloc_sum - 100.0) > 0.5:
    st.warning(f"Allocations sum to {alloc_sum:.1f}% (aim for ~100).")

# ---- Convert to EUR ----
you_pension_eur = gbp_to_eur(you_pension_gbp, fx)
wife_pension_eur = gbp_to_eur(wife_pension_gbp, fx)
starting_capital_eur = gbp_to_eur(starting_capital_gbp, fx)
brackets = italian_irpef_2025()

# ---- Simulation ----
years_total = years_in_7pct + years_post
years = list(range(1, years_total + 1))
pots = weighted_starting_capital(starting_capital_eur, strategies)

# Tracking lists
year_end_capital, year_pension_gross, year_tax_total, year_net_income_total = [], [], [], []
year_foreign_invest_income, year_italian_invest_income = [], []
year_foreign_invest_tax, year_italian_invest_tax, year_pension_tax = [], [], []

for y in years:
    in_regime = y <= years_in_7pct
    pension_gross = you_pension_eur + wife_pension_eur

    if in_regime:
        pension_tax = pension_gross * 0.07
    else:
        base = calc_irpef_tax(pension_gross, brackets)
        pension_tax = add_region_muni_surcharge(base, regional_surcharge, municipal_surcharge)
    pension_net = pension_gross - pension_tax

    def invest_tax_post10(amount_eur: float) -> float:
        return tax_at_irpef_with_surcharges(amount_eur, brackets, regional_surcharge, municipal_surcharge)

    foreign_income = foreign_tax = italian_income = italian_tax = 0.0
    new_pots = {}

    for name, strat in strategies.items():
        cap0 = pots.get(name, 0.0)
        end_cap, net_income, gross_income, tax = annual_investment_step(
            capital=cap0,
            strategy=strat,
            in_regime_7pct=in_regime,
            tax_func_post10=invest_tax_post10,
        )
        new_pots[name] = end_cap
        if strat.is_foreign_source:
            foreign_income += gross_income
            foreign_tax += tax
        else:
            italian_income += gross_income
            italian_tax += tax
    pots = new_pots
    total_capital = sum(pots.values())
    total_tax = pension_tax + foreign_tax + italian_tax
    total_net = pension_net + (foreign_income - foreign_tax) + (italian_income - italian_tax)

    # record
    year_end_capital.append(total_capital)
    year_pension_gross.append(pension_gross)
    year_tax_total.append(total_tax)
    year_net_income_total.append(total_net)
    year_foreign_invest_income.append(foreign_income)
    year_italian_invest_income.append(italian_income)
    year_foreign_invest_tax.append(foreign_tax)
    year_italian_invest_tax.append(italian_tax)
    year_pension_tax.append(pension_tax)

# ---- Build DataFrame ----
df = combine_series_to_df(
    years,
    {
        "Pension_Gross_EUR": year_pension_gross,
        "Foreign_Invest_Gross_EUR": year_foreign_invest_income,
        "Italian_Invest_Gross_EUR": year_italian_invest_income,
        "Tax_Pension_EUR": year_pension_tax,
        "Tax_Foreign_Invest_EUR": year_foreign_invest_tax,
        "Tax_Italian_Invest_EUR": year_italian_invest_tax,
        "Tax_Total_EUR": year_tax_total,
        "Net_Income_Total_EUR": year_net_income_total,
        "End_Capital_EUR": year_end_capital,
    },
)
df = add_real_terms(
    df,
    cols=[
        "Pension_Gross_EUR", "Foreign_Invest_Gross_EUR", "Italian_Invest_Gross_EUR",
        "Tax_Total_EUR", "Net_Income_Total_EUR", "End_Capital_EUR",
    ],
    inflation_pct=inflation_pct,
)

df_7 = df.iloc[:years_in_7pct, :].copy() if years_in_7pct > 0 else pd.DataFrame()
df_post = df.iloc[years_in_7pct:, :].copy() if years_post > 0 else pd.DataFrame()

# ---- Tabs ----
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📈 Overview", "🟢 Years 1–10 (7% Regime)", "🔵 Post-Regime", "📊 Source Breakdown", "ℹ️ Inputs Explained"
])

def euro(x): return f"€{x:,.0f}"

with tab1:
    st.subheader("Key Totals (EUR)")
    c1, c2, c3 = st.columns(3)
    c1.metric("Year 1 Net", euro(df.loc[0, 'Net_Income_Total_EUR']))
    c2.metric("Year 10 Net", euro(df.loc[years_in_7pct-1, 'Net_Income_Total_EUR']) if years_in_7pct > 0 else "—")
    c3.metric(f"Year {len(df)} Capital", euro(df.loc[len(df)-1, 'End_Capital_EUR']))

    st.markdown("### Income, Capital & Tax Over Time (€)")
    fig = px.line(
        df, x="Year", y=["Net_Income_Total_EUR", "End_Capital_EUR", "Tax_Total_EUR"],
        labels={"value": "€", "variable": "Category"},
        color_discrete_map={
            "Net_Income_Total_EUR": "#00B050",
            "End_Capital_EUR": "#0070C0",
            "Tax_Total_EUR": "#C00000"
        },
        template=theme_template,
    )
    fig.update_traces(line=dict(width=3))
    fig.update_layout(yaxis_tickprefix="€", yaxis_tickformat=",", legend_title_text="")
    st.plotly_chart(fig, use_container_width=True)
    st.download_button("⬇️ Download Full CSV", df.to_csv(index=False).encode("utf-8"), "projection_full.csv")

with tab2:
    st.subheader("7% Regime Period")
    st.dataframe(df_7.style.format({c: "€{:,.0f}" for c in df_7.columns if c.endswith("_EUR")}))
    st.download_button("⬇️ Download 7% CSV", df_7.to_csv(index=False).encode("utf-8"), "projection_7pct.csv")

with tab3:
    st.subheader("Post-Regime Period")
    st.dataframe(df_post.style.format({c: "€{:,.0f}" for c in df_post.columns if c.endswith("_EUR")}))
    st.download_button("⬇️ Download Post CSV", df_post.to_csv(index=False).encode("utf-8"), "projection_post.csv")

with tab4:
    st.subheader("Income & Tax by Source Type")
    cols = [
        "Year", "Pension_Gross_EUR", "Foreign_Invest_Gross_EUR", "Italian_Invest_Gross_EUR",
        "Tax_Pension_EUR", "Tax_Foreign_Invest_EUR", "Tax_Italian_Invest_EUR",
        "Tax_Total_EUR", "Net_Income_Total_EUR",
    ]
    st.dataframe(df[cols].style.format({c: "€{:,.0f}" for c in cols if c.endswith("_EUR")}))
    st.download_button("⬇️ Download Source Breakdown", df[cols].to_csv(index=False).encode("utf-8"), "projection_source_breakdown.csv")

# ---- Inputs Explained Tab ----
with tab5:
    st.header("Understanding Each Input")
    st.markdown("""
    ### 💱 General Settings
    - **FX (€ per £)** – Converts your UK income and savings to euros.
    - **Inflation (%)** – Models price rises; higher inflation lowers future purchasing power.

    ### 💰 Pensions (GBP)
    - **Your Pension (£)** and **Wife's Pension (£)** – Annual pre-tax pension income converted into euros.

    ### 💼 Capital (GBP)
    - **Starting Investable Capital (£)** – Savings or inheritance used to generate investment income.

    ### ⏳ Horizon
    - **Years in 7% Regime** – Duration of Italy’s flat 7% tax on foreign income.
    - **Years Post-Regime** – Normal Italian tax applies beyond this period.

    ### 🇮🇹 Italian Progressive (Post-Regime)
    - **Regional Add-on** and **Municipal Add-on** – Local surcharges on IRPEF after the 7% regime ends.

    ### 📊 Investment Strategies
    - **Cash, Bonds, Equity, Property** – Define how your capital is invested.
    - Adjust yields, fees, and growth rates to test different performance assumptions.

    ### 🧾 Tips
    - Keep allocations near 100%.
    - Use higher growth for higher-risk assets.
    - Experiment with inflation or FX to see long-term effects.
    """)

    with st.expander("📘 Learn More – Example Scenarios"):
        st.markdown("""
        #### 💨 Inflation Example
        5% inflation halves your purchasing power in about 14 years.
        Check 'real' columns in CSVs to see inflation-adjusted results.

        #### 💶 Exchange Rate Example
        A lower FX rate (e.g. €1.05/£) reduces your euro income. Try changing FX to visualise its impact.

        #### 📊 Allocation Example
        More equities or property increase growth potential but also volatility.

        #### 🇮🇹 7% Regime Example
        First 10 years taxed at flat 7% on foreign income, then switches automatically to IRPEF.

        #### 🏡 Rental Property Example
        Tick 'foreign-source' if property is abroad to keep 7% benefit. Untick for Italian rentals taxed under IRPEF.
        """)

        st.info("💡 Tip: Change one input at a time to see its effect — e.g. raise inflation or lower FX — and watch the graphs adjust dynamically.")
