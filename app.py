from flask import Flask, render_template, request, jsonify
import pandas as pd
from strategy_logic import run_dynamic_backtest

app = Flask(__name__)
# Preserve order of keys in JSON responses for consistent UI display, e.g. performance chart at the top.
app.json.sort_keys = False

PRICES = pd.read_csv('prices.csv', index_col=0, parse_dates=True)

# @app.route("/") defines the route for the home page, which renders the tearsheet.html template with some context variables.
@app.route("/")
def index():

    start_date = PRICES.index.min().strftime('%b %Y')
    end_date = PRICES.index.max().strftime('%b %Y')
    date_range = f"{start_date} – {end_date}"

    return render_template("tearsheet.html", 
                           fund_name="Momentum Sector Rotation Strategy", 
                           date_range=date_range,
                           benchmark="S&P 500")

# @app.route("/api/refresh") defines the route for the API that refreshes the backtest results based on new input 
# parameters, i.e. lookback periods, number of sectors, etc.
@app.route("/api/refresh")
def refresh():
    # Ensure these keys match the fetch URL in tearsheet.html exactly
    l1 = request.args.get('l1', default=3, type=int)
    l2 = request.args.get('l2', default=6, type=int)
    n = request.args.get('n', default=3, type=int)
    c = request.args.get('c', default=0.5, type=float)
    
    # It calls the function with these parameters and returns the results as JSON.
    data = run_dynamic_backtest(PRICES, [l1, l2], n, c)
    return jsonify(data)

if __name__ == "__main__":
    app.run(debug=True)