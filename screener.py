import yfinance as yf
import pandas as pd
import requests
import os

# CLEANED FTSE MIB TICKERS (Removed delisted/broken ones)
TICKERS = [
    'A2A.MI', 'AMP.MI', 'AZM.MI', 'BPE.MI', 'DAN.MI', 
    'DIA.MI', 'ENEL.MI', 'ENI.MI', 'G.MI', 'HER.MI', 
    'IG.MI', 'ISP.MI', 'IVG.MI', 'LDO.MI', 'MB.MI', 
    'MONC.MI', 'NEXI.MI', 'PRY.MI', 'RACE.MI', 'RCS.MI', 
    'SFER.MI', 'SRG.MI', 'TEN.MI', 'TIT.MI', 'TRN.MI', 
    'UCG.MI', 'STLAM.MI'
]

WORKER_URL = os.environ.get('CLOUDFLARE_WORKER_URL')
SECRET = os.environ.get('GIT_SECRET')
HEADERS = {'Authorization': f'Bearer {SECRET}', 'Content-Type': 'application/json'}

def calculate_rsi(prices, period=14):
    delta = prices.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def run_screener():
    print(f"Starting Italian Screener for {len(TICKERS)} tickers...")
    payload_batch = []
    
    for symbol in TICKERS:
        try:
            stock = yf.Ticker(symbol)
            info = stock.info
            hist = stock.history(period="1y")
            
            if hist.empty or len(hist) < 200:
                print(f"Skipping {symbol}: Insufficient historical data.")
                continue

            pe = info.get('forwardPE') or info.get('trailingPE')
            roe = info.get('returnOnEquity', 0) or 0
            target_mean = info.get('targetMeanPrice')
            analyst_rec = info.get('recommendationKey', 'N/A')
            num_analysts = info.get('numberOfAnalystOpinions', 0)
            
            closes = hist['Close']
            current_price = float(closes.iloc[-1])
            sma_200 = float(closes.rolling(window=200).mean().iloc[-1])
            rsi = float(calculate_rsi(closes).iloc[-1])

            signal = "Buy on Pullback" if (current_price > sma_200 and rsi < 45) else "Watchlist"

            stock_data = {
                "ticker": symbol,
                "price": round(current_price, 2),
                "pe": round(float(pe), 2) if pe else 999.0,
                "roe": round(float(roe * 100), 2),
                "rsi": round(rsi, 2),
                "target_mean": round(float(target_mean), 2) if target_mean else None,
                "analyst_rec": analyst_rec,
                "num_analysts": int(num_analysts) if num_analysts else 0,
                "signal": signal
            }
            payload_batch.append(stock_data)
            
            hist_data = [{"date": str(d.date())[:10], "close": float(c)} for d, c in zip(hist.index[-300:], closes[-300:])]
            requests.post(f"{WORKER_URL}/api/update-history", json={"ticker": symbol, "data": hist_data}, headers=HEADERS)
            
        except Exception as e:
            print(f"Error processing {symbol}: {e}")
            continue

    if payload_batch:
        res = requests.post(f"{WORKER_URL}/api/update-screener", json=payload_batch, headers=HEADERS)
        print(f"Successfully updated {len(payload_batch)} stocks in database: {res.status_code}")
    else:
        print("WARNING: No stocks were successfully processed!")

if __name__ == "__main__":
    run_screener()
