from flask import Flask, render_template
import os
import requests

app = Flask(__name__)

EODHD_API_KEY = os.environ.get("EODHD_API_KEY", "demo")
SYMBOL = "AAPL.US"

@app.route("/")
def index():
    url = f"https://eodhd.com/api/real-time/{SYMBOL}"
    params = {"api_token": EODHD_API_KEY, "fmt": "json"}

    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as e:
        return render_template("index.html", error=str(e), data=None)

    return render_template("index.html", data=data, error=None)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)