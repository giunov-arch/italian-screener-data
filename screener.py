import yfinance as yf
import pandas as pd
import requests
import os

TICKERS = ['ENI.MI', 'ENEL.MI', 'ISP.MI', 'UCG.MI', 'STLAM.MI', 'PRY.MI', 'DIA.MI', 'TIT.MI']
WORKER_URL = os.environ.get('CLOUDFLARE_WORKER_URL')
SECRET = os.environ.get('GITHUB_SECRET')
HEADERS = {'Authorization': f'Bearer {SECRET}', 'Content-Type': 'application/json'}

def calculate_rsi(prices, period=14):
    delta = prices.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

for symbol in TICKERS:
    try:
        stock = yf.Ticker(symbol)
        info = stock.info
        hist = stock.history(period="1y")
        if hist.empty or len(hist) < 200: continue

        pe = info.get('forwardPE') or info.get('trailingPE')
        roe = info.get('returnOnEquity', 0) or 0
        if not pe or pe > 25 or roe < 0.08: continue

        closes = hist['Close']
        current_price = closes.iloc[-1]
        sma_200 = closes.rolling(window=200).mean().iloc[-1]
        rsi = calculate_rsi(closes).iloc[-1]

        # 1. Push Fundamentals & Technicals
        payload = [{
            "ticker": symbol, "price": round(float(current_price), 2), "pe": round(float(pe), 2),
            "roe": round(float(roe * 100), 2), "rsi": round(float(rsi), 2),
            "target_mean": round(float(info.get('targetMeanPrice', 0)), 2) if info.get('targetMeanPrice') else None,
            "analyst_rec": info.get('recommendationKey', 'N/A'), "num_analysts": info.get('numberOfAnalystOpinions', 0),
            "signal": "Buy on Pullback" if (current_price > sma_200 and rsi < 45) else "Watchlist"
        }]
        requests.post(f"{WORKER_URL}/api/update-screener", json=payload, headers=HEADERS)

        # 2. Push Historical Prices for Chart
        hist_data = [{"date": str(d.date())[:10], "close": float(c)} for d, c in zip(hist.index[-300:], closes[-300:])]
        requests.post(f"{WORKER_URL}/api/update-history", json={"ticker": symbol, "data": hist_data}, headers=HEADERS)
        
    except Exception as e:
        print(f"Error {symbol}: {e}")
