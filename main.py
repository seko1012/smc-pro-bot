import os
import time
import requests
import pandas as pd
from flask import Flask
from threading import Thread

app = Flask(__name__)

# Render Environment Variables
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]

def send_telegram(msg):
    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": msg,
            "parse_mode": "Markdown"
        }
        try:
            requests.post(url, json=payload, timeout=10)
        except Exception as e:
            print(f"Telegram Göndərmə Xətası: {e}")

def get_bybit_kline(symbol, interval, limit=200):
    url = f"https://api.bybit.com/v5/market/kline?category=linear&symbol={symbol}&interval={interval}&limit={limit}"
    try:
        res = requests.get(url, timeout=10).json()
        if res.get("retCode") == 0:
            list_data = res["result"]["list"]
            df = pd.DataFrame(list_data, columns=["startTime", "open", "high", "low", "close", "volume", "turnover"])
            df = df.iloc[::-1].reset_index(drop=True)
            df["close"] = df["close"].astype(float)
            df["high"] = df["high"].astype(float)
            df["low"] = df["low"].astype(float)
            return df
    except Exception as e:
        print(f"Bybit API Xətası ({symbol}): {e}")
    return None

def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def run_scanner():
    print(">>> SMC Pro Level 3 Scanner Ishe Dushdu <<<")
    # Bot açılan kimi Telegram bağlantısını yoxlamaq üçün test mesajı
    send_telegram("🚀 *SMC Pro Level 3 Engine Activated!*\nBybit marketləri 24/7 skan olunur...")

    while True:
        try:
            for symbol in SYMBOLS:
                # 1. 1 Saatlıq (1H) Trend & EMA-200 Analizi
                df_1h = get_bybit_kline(symbol, "60", limit=200)
                if df_1h is None or len(df_1h) < 200:
                    continue
                
                df_1h["ema200"] = df_1h["close"].ewm(span=200, adjust=False).mean()
                last_1h_close = df_1h["close"].iloc[-1]
                ema_200 = df_1h["ema200"].iloc[-1]

                is_bullish_trend = last_1h_close > ema_200
                is_bearish_trend = last_1h_close < ema_200

                # 2. 5 Dəqiqəlik (5m) FVG & RSI Analizi
                df_5m = get_bybit_kline(symbol, "5", limit=50)
                if df_5m is None or len(df_5m) < 3:
                    continue

                df_5m["rsi"] = calculate_rsi(df_5m["close"])
                last_rsi = df_5m["rsi"].iloc[-1]

                # 5m FVG Təyini (Bullaşma / Ayılaşma)
                # Bullish FVG: Mum 3 High < Mum 1 Low
                c1_low = df_5m["low"].iloc[-3]
                c3_high = df_5m["high"].iloc[-1]
                
                # Bearish FVG: Mum 3 Low > Mum 1 High
                c1_high = df_5m["high"].iloc[-3]
                c3_low = df_5m["low"].iloc[-1]

                # SMC Level 3 Qaydaları
                # LONG Signal
                if is_bullish_trend and (c1_low > c3_high) and (last_rsi < 55):
                    entry = df_5m["close"].iloc[-1]
                    sl = df_5m["low"].iloc[-3]
                    tp = entry + ((entry - sl) * 2) # R:R 1:2
                    
                    msg = (
                        f"🟢 *SMC LEVEL 3 LONG SIGNAL*\n\n"
                        f"📌 *Symbol:* #{symbol}\n"
                        f"📊 *1H Trend:* Bullish (Above EMA-200)\n"
                        f"🎯 *Entry:* `{entry:.2f}`\n"
                        f"🛑 *SL:* `{sl:.2f}`\n"
                        f"🎯 *TP (1:2):* `{tp:.2f}`\n"
                        f"📉 *RSI:* `{last_rsi:.1f}`"
                    )
                    send_telegram(msg)
                    time.sleep(300) # Təkrar siqnal verməmək üçün 5 dəq gözləyir

                # SHORT Signal
                elif is_bearish_trend and (c3_low > c1_high) and (last_rsi > 45):
                    entry = df_5m["close"].iloc[-1]
                    sl = df_5m["high"].iloc[-3]
                    tp = entry - ((sl - entry) * 2) # R:R 1:2

                    msg = (
                        f"🔴 *SMC LEVEL 3 SHORT SIGNAL*\n\n"
                        f"📌 *Symbol:* #{symbol}\n"
                        f"📊 *1H Trend:* Bearish (Below EMA-200)\n"
                        f"🎯 *Entry:* `{entry:.2f}`\n"
                        f"🛑 *SL:* `{sl:.2f}`\n"
                        f"🎯 *TP (1:2):* `{tp:.2f}`\n"
                        f"📈 *RSI:* `{last_rsi:.1f}`"
                    )
                    send_telegram(msg)
                    time.sleep(300)

        except Exception as e:
            print(f"Scanner Loop Error: {e}")

        time.sleep(60) # Hər 1 dəqiqədən bir skan et

# Skaneri arxa fonda müstəqil işlədirik
Thread(target=run_scanner, daemon=True).start()

@app.route("/")
def home():
    return "SMC Pro Level 3 Engine Active & Scanning!", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
