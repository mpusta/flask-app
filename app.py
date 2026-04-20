from flask import Flask, render_template
from datetime import datetime
import json

app = Flask(__name__)

# ── Hardcoded data ────────────────────────────────────────────────────────────

LABELS = [
    "Jan19","Feb19","Mar19","Apr19","May19","Jun19","Jul19","Aug19","Sep19","Oct19","Nov19","Dec19",
    "Jan20","Feb20","Mar20","Apr20","May20","Jun20","Jul20","Aug20","Sep20","Oct20","Nov20","Dec20",
    "Jan21","Feb21","Mar21","Apr21","May21","Jun21","Jul21","Aug21","Sep21","Oct21","Nov21","Dec21",
    "Jan22","Feb22","Mar22","Apr22","May22","Jun22","Jul22","Aug22","Sep22","Oct22","Nov22","Dec22",
    "Jan23","Feb23","Mar23","Apr23","May23","Jun23","Jul23","Aug23","Sep23","Oct23","Nov23","Dec23",
    "Jan24","Feb24","Mar24","Apr24","May24","Jun24","Jul24","Aug24","Sep24","Oct24","Nov24","Dec24",
]

CUM_DATA = [
    100,103.2,107.1,110.4,106.8,109.5,113.0,110.2,114.8,118.3,116.0,119.7,
    122.5,117.3,98.4,108.2,112.6,116.9,121.3,124.0,120.5,116.8,124.3,131.0,
    134.2,138.7,145.1,150.6,154.2,158.8,162.3,165.0,160.4,168.9,175.2,179.3,
    172.6,168.1,163.2,154.7,149.8,140.3,135.6,140.2,132.8,138.4,144.7,150.3,
    155.8,159.2,164.7,167.3,171.0,175.6,180.3,184.9,179.6,176.2,183.5,189.0,
    194.8,201.3,208.7,203.4,211.2,218.5,225.3,220.6,228.9,236.4,244.1,250.5,
]

BENCH_DATA = [
    100,101.8,105.2,108.6,104.1,106.7,109.4,107.0,111.3,114.2,112.5,115.8,
    118.3,113.4,95.2,105.8,109.6,112.9,116.8,119.1,115.4,112.0,119.3,125.4,
    128.2,132.6,138.4,143.2,146.8,150.1,153.7,156.2,151.8,159.4,164.9,168.0,
    161.3,157.2,152.8,144.6,140.1,131.5,127.0,131.9,124.8,130.1,136.2,141.4,
    146.7,149.8,154.9,157.2,160.6,164.1,168.5,172.8,168.2,165.0,171.8,177.1,
    182.6,188.9,195.4,190.5,197.9,204.7,210.8,206.3,213.9,220.8,227.2,212.5,
]

DD_DATA = [
    0,-1.2,0,0,-3.3,-1.4,0,-2.5,0,0,-2.0,0,
    0,-4.3,-19.7,-9.4,-5.4,-1.2,0,-2.2,-5.1,-8.3,-1.6,0,
    0,0,0,0,0,0,0,0,-2.7,0,0,0,
    -4.0,-6.4,-9.8,-16.5,-19.9,-23.1,-26.2,-23.3,-28.4,-23.7,-18.4,-13.5,
    -10.2,-7.8,-4.1,-2.1,0,0,0,0,-3.0,-5.1,0,0,
    0,0,0,-3.0,0,0,0,-2.1,0,0,0,0,
]

ROLL_SHARPE = [
    1.2,1.35,1.4,1.5,1.55,1.6,1.45,1.3,1.5,1.65,1.7,1.75,
    1.8,1.6,1.4,1.2,1.0,0.85,0.7,0.55,0.4,0.45,0.6,0.75,
    0.9,1.05,1.2,1.35,1.5,1.6,1.55,1.45,1.4,1.5,1.6,1.65,
    1.7,1.55,1.42,1.38,1.44,1.5,1.58,1.62,1.55,1.5,1.48,1.52,
    1.6,1.58,1.55,1.5,1.45,1.48,1.52,1.55,1.58,1.6,1.55,1.50,1.45,
]

MONTHLY_RET = {
    2019: [3.2,  2.1, -1.4,  4.5,  1.8, -2.3,  3.4, -1.2,  2.8,  1.9, -0.7,  3.1],
    2020: [-3.1,-7.2,-15.8,  9.5,  4.0,  3.8,  3.8,  2.2, -2.9, -3.1,  6.5,  5.4],
    2021: [2.5,  3.3,  4.6,  3.8,  2.4,  2.9,  2.2,  1.7, -2.8,  5.3,  3.7,  2.3],
    2022: [-4.0,-2.6, -3.1, -5.2, -3.2, -6.3, -3.3,  3.4, -5.8,  4.2,  4.6,  3.9],
    2023: [3.7,  2.2,  3.5,  1.6,  2.2,  2.7,  2.7,  2.6, -2.9, -1.9,  4.2,  3.0],
    2024: [3.1,  3.3,  3.7, -2.5,  3.8,  3.4,  3.1, -2.1,  3.8,  3.3,  3.2,  2.6],
}

KPI = [
    {"label": "Total return",  "value": "+184.3%", "cls": "pos"},
    {"label": "CAGR",          "value": "+19.4%",  "cls": "pos"},
    {"label": "Sharpe ratio",  "value": "1.42",    "cls": "neu"},
    {"label": "Sortino ratio", "value": "2.11",    "cls": "neu"},
    {"label": "Max drawdown",  "value": "-23.1%",  "cls": "neg"},
    {"label": "Volatility",    "value": "16.8%",   "cls": "neu"},
    {"label": "Calmar ratio",  "value": "0.84",    "cls": "neu"},
    {"label": "Win rate",      "value": "62.3%",   "cls": "pos"},
]

STATS_LEFT = [
    ("Annual return",   "+19.4%", "pos"),
    ("Ann. volatility", "16.8%",  "neu"),
    ("Sharpe ratio",    "1.42",   "neu"),
    ("Sortino ratio",   "2.11",   "neu"),
    ("Max drawdown",    "-23.1%", "neg"),
    ("Calmar ratio",    "0.84",   "neu"),
    ("Win rate",        "62.3%",  "pos"),
    ("Avg win day",     "+1.24%", "pos"),
    ("Avg loss day",    "-0.87%", "neg"),
    ("Profit factor",   "1.88",   "pos"),
]

STATS_RIGHT = [
    ("Beta",        "0.78",   "neu"),
    ("Alpha",       "8.2%",   "pos"),
    ("Correlation", "0.71",   "neu"),
    ("R-squared",   "0.51",   "neu"),
    ("VaR (95%)",   "-2.8%",  "neg"),
    ("CVaR (95%)",  "-4.1%",  "neg"),
    ("Skewness",    "0.34",   "neu"),
    ("Kurtosis",    "3.82",   "neu"),
    ("Best month",  "+12.3%", "pos"),
    ("Worst month", "-9.7%",  "neg"),
]

# ── Route ─────────────────────────────────────────────────────────────────────

@app.route("/")
def tearsheet():
    roll_labels = LABELS[11:]  # rolling window starts after first 12 months
    monthly_ret_str_keys = {str(k): v for k, v in MONTHLY_RET.items()}

    return render_template(
        "tearsheet.html",
        fund_name="Alpha Growth Fund",
        benchmark="S&P 500",
        date_range="Jan 2019 – Dec 2024",
        generated_at=datetime.today().strftime("%B %d, %Y"),
        kpi=KPI,
        stats_left=STATS_LEFT,
        stats_right=STATS_RIGHT,
        labels=json.dumps(LABELS),
        cum_data=json.dumps(CUM_DATA),
        bench_data=json.dumps(BENCH_DATA),
        dd_data=json.dumps(DD_DATA),
        roll_sharpe=json.dumps(ROLL_SHARPE),
        roll_labels=json.dumps(roll_labels),
        monthly_ret=json.dumps(monthly_ret_str_keys),
    )


if __name__ == "__main__":
    app.run(debug=True)