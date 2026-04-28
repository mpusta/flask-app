import os
import pandas as pd
import requests
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.environ.get('EODHD_API_KEY', '')
BASE_URL = 'https://eodhd.com/api/eod'
SECTORS = ['XLK', 'XLV', 'XLF', 'XLY', 'XLP', 'XLE', 'XLI', 'XLB', 'XLU', 'XLRE', 'XLC']
BENCHMARK = 'SPY'
START_DATE = '2000-01-01'

def update_csv():
    end_date = datetime.today().strftime('%Y-%m-%d')
    frames = []
    for ticker in [BENCHMARK] + SECTORS:
        r = requests.get(f'{BASE_URL}/{ticker}.US', params={
            'api_token': API_KEY,
            'from': START_DATE,
            'to': end_date,
            'period': 'm',
            'fmt': 'json',
        }, timeout=30)
        data = r.json()
        df = pd.DataFrame(data)
        df['date'] = pd.to_datetime(df['date'])
        # Dates are sorted to ensure correct order for SMA and momentum calculations.
        frames.append(
            df.set_index('date').
            sort_index()[['adjusted_close']].
            rename(columns={'adjusted_close': ticker})
        )
    df = pd.concat(frames, axis=1).ffill(limit=1)
    df.to_csv('prices.csv')


if __name__ == "__main__":
    update_csv()