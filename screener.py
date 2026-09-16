import yfinance as yf
import pandas as pd
import requests
import os

# Major Italian Equities (FTSE MIB & Mid Caps)
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

def run_screener():
    print(f"Starting Italian Screener for {len(TICKERS)} tickers...")
    
    for symbol in TICKERS:
        try:
            stock = yf.Ticker(symbol)
            info = stock.info
            hist = stock.history(period="1y")
            
            if hist.empty or len(hist) < 200:
                print(f"Skipping {symbol}: Not enough historical data.")
                continue

            # 1. Extract Fundamentals & Analyst Data
            pe = info.get('forwardPE') or info.get('trailingPE')
            roe = info.get('returnOnEquity', 0) or 0
            target_mean = info.get('targetMeanPrice')
            analyst_rec = info.get('recommendationKey', 'N/A')
            num_analysts = info.get('numberOfAnalystOpinions', 0)
            
            # Basic fundamental filter (Avoid overvalued or inefficient companies)
            if not pe or pe > 25 or roe < 0.08:
                print(f"Skipping {symbol}: Failed fundamental filter (PE: {pe}, ROE: {roe}).")
                continue

            # 2. Calculate Technicals
            closes = hist['Close']
            current_price = float(closes.iloc[-1])
            sma_200 = float(closes.rolling(window=200).mean().iloc[-1])
            rsi = float(calculate_rsi(closes).iloc[-1])

            # Determine Signal
            signal = "Buy on Pullback" if (current_price > sma_200 and rsi < 45) else "Watchlist"

            # 3. Format Payload for Cloudflare Worker
            payload = [{
                "ticker": symbol,
                "price": round(current_price, 2),
                "pe": round(float(pe), 2),
                "roe": round(float(roe * 100), 2),
                "rsi": round(rsi, 2),
                "target_mean": round(float(target_mean), 2) if target_mean else None,
                "analyst_rec": analyst_rec,
                "num_analysts": int(num_analysts) if num_analysts else 0,
                "signal": signal
            }]
            
            # Push to Cloudflare
            res = requests.post(f"{WORKER_URL}/api/update-screener", json=payload, headers=HEADERS)
            print(f"Updated {symbol} screener data: {res.status_code}")

            # 4. Push Historical Prices for the Frontend Chart
            hist_data = [{"date": str(d.date())[:10], "close": float(c)} for d, c in zip(hist.index[-300:], closes[-300:])]
            res_hist = requests.post(f"{WORKER_URL}/api/update-history", json={"ticker": symbol, "data": hist_data}, headers=HEADERS)
            print(f"Updated {symbol} chart history: {res_hist.status_code}")
            
        except Exception as e:
            print(f"Error processing {symbol}: {e}")

if __name__ == "__main__":
    run_screener()
