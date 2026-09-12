import os
import time
import requests
import pandas as pd
from flask import Flask
from threading import Thread

app = Flask(__name__)

# =========================
# TELEGRAM SETTINGS
# =========================

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()

# =========================
# COINS
# =========================

SYMBOLS = [
    "BTCUSDT",
    "ETHUSDT",
    "SOLUSDT"
]

# =========================
# TELEGRAM
# =========================

def send_telegram(msg):
    if not TELEGRAM_BOT_TOKEN:
        print("❌ TELEGRAM_BOT_TOKEN tapılmadı!")
        return False

    if not TELEGRAM_CHAT_ID:
        print("❌ TELEGRAM_CHAT_ID tapılmadı!")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": msg
    }

    try:
        response = requests.post(
            url,
            json=payload,
            timeout=10
        )

        print("Telegram Status:", response.status_code)
        print("Telegram Response:", response.text)

        if response.ok:
            print("✅ Telegram mesajı göndərildi!")
            return True

        print("❌ Telegram mesajı göndərilmədi!")
        return False

    except Exception as e:
        print("❌ Telegram Xətası:", e)
        return False


# =========================
# BYBIT DATA
# =========================

def get_bybit_kline(symbol, interval, limit=200):

    url = (
        "https://api.bybit.com/v5/market/kline"
        f"?category=linear"
        f"&symbol={symbol}"
        f"&interval={interval}"
        f"&limit={limit}"
    )

    try:
        response = requests.get(url, timeout=10)
        data = response.json()

        if data.get("retCode") != 0:
            print(f"❌ Bybit xətası {symbol}: {data}")
            return None

        list_data = data["result"]["list"]

        df = pd.DataFrame(
            list_data,
            columns=[
                "startTime",
                "open",
                "high",
                "low",
                "close",
                "volume",
                "turnover"
            ]
        )

        # Köhnədən yeniyə
        df = df.iloc[::-1].reset_index(drop=True)

        df["open"] = df["open"].astype(float)
        df["high"] = df["high"].astype(float)
        df["low"] = df["low"].astype(float)
        df["close"] = df["close"].astype(float)

        return df

    except Exception as e:
        print(f"❌ Bybit API Xətası ({symbol}): {e}")
        return None


# =========================
# RSI
# =========================

def calculate_rsi(series, period=14):

    delta = series.diff()

    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)

    avg_gain = gain.rolling(window=period).mean()
    avg_loss = loss.rolling(window=period).mean()

    rs = avg_gain / avg_loss

    rsi = 100 - (100 / (1 + rs))

    return rsi


# =========================
# SCANNER
# =========================

def run_scanner():

    print("===================================")
    print("🚀 SMC PRO LEVEL 3 SCANNER STARTED")
    print("===================================")

    # Server açılan kimi test mesajı
    send_telegram(
        "🚀 SMC Pro Level 3 Engine Activated!\n\n"
        "Bybit marketləri 24/7 skan olunur.\n"
        "✅ Telegram bağlantısı aktivdir."
    )

    while True:

        try:

            for symbol in SYMBOLS:

                print(f"🔎 {symbol} yoxlanılır...")

                # =========================
                # 1H DATA
                # =========================

                df_1h = get_bybit_kline(
                    symbol,
                    "60",
                    limit=200
                )

                if df_1h is None or len(df_1h) < 200:
                    print(f"⚠️ {symbol} üçün 1H data kifayət deyil.")
                    continue

                # EMA 200
                df_1h["ema200"] = (
                    df_1h["close"]
                    .ewm(span=200, adjust=False)
                    .mean()
                )

                last_1h_close = df_1h["close"].iloc[-1]
                ema_200 = df_1h["ema200"].iloc[-1]

                is_bullish_trend = last_1h_close > ema_200
                is_bearish_trend = last_1h_close < ema_200

                # =========================
                # 5M DATA
                # =========================

                df_5m = get_bybit_kline(
                    symbol,
                    "5",
                    limit=50
                )

                if df_5m is None or len(df_5m) < 20:
                    print(f"⚠️ {symbol} üçün 5M data kifayət deyil.")
                    continue

                # RSI
                df_5m["rsi"] = calculate_rsi(
                    df_5m["close"]
                )

                last_rsi = df_5m["rsi"].iloc[-1]

                if pd.isna(last_rsi):
                    continue

                # =========================
                # FVG
                # =========================

                # Son 3 şam
                candle_1 = df_5m.iloc[-3]
                candle_3 = df_5m.iloc[-1]

                # Bullish FVG
                # 1-ci şamın HIGH-ı
                # 3-cü şamın LOW-undan aşağıdır
                bullish_fvg = (
                    candle_1["high"] < candle_3["low"]
                )

                # Bearish FVG
                # 1-ci şamın LOW-u
                # 3-cü şamın HIGH-ından yuxarıdır
                bearish_fvg = (
                    candle_1["low"] > candle_3["high"]
                )

                # =========================
                # LONG SIGNAL
                # =========================

                if (
                    is_bullish_trend
                    and bullish_fvg
                    and last_rsi < 55
                ):

                    entry = df_5m["close"].iloc[-1]

                    sl = candle_1["low"]

                    risk = entry - sl

                    if risk > 0:

                        tp = entry + (risk * 2)

                        msg = (
                            "🟢 SMC LEVEL 3 LONG SIGNAL\n\n"
                            f"📌 Symbol: #{symbol}\n"
                            "📊 1H Trend: Bullish\n"
                            f"🎯 Entry: {entry:.2f}\n"
                            f"🛑 SL: {sl:.2f}\n"
                            f"🎯 TP (1:2): {tp:.2f}\n"
                            f"📉 RSI: {last_rsi:.1f}\n\n"
                            "⚡ SMC Pro Level 3"
                        )

                        send_telegram(msg)

                        print(f"🟢 LONG SIGNAL: {symbol}")

                        # 5 dəqiqə gözlə
                        time.sleep(300)

                # =========================
                # SHORT SIGNAL
                # =========================

                elif (
                    is_bearish_trend
                    and bearish_fvg
                    and last_rsi > 45
                ):

                    entry = df_5m["close"].iloc[-1]

                    sl = candle_1["high"]

                    risk = sl - entry

                    if risk > 0:

                        tp = entry - (risk * 2)

                        msg = (
                            "🔴 SMC LEVEL 3 SHORT SIGNAL\n\n"
                            f"📌 Symbol: #{symbol}\n"
                            "📊 1H Trend: Bearish\n"
                            f"🎯 Entry: {entry:.2f}\n"
                            f"🛑 SL: {sl:.2f}\n"
                            f"🎯 TP (1:2): {tp:.2f}\n"
                            f"📈 RSI: {last_rsi:.1f}\n\n"
                            "⚡ SMC Pro Level 3"
                        )

                        send_telegram(msg)

                        print(f"🔴 SHORT SIGNAL: {symbol}")

                        # 5 dəqiqə gözlə
                        time.sleep(300)

        except Exception as e:

            print("❌ Scanner Loop Error:", e)

        # 1 dəqiqə sonra yenidən yoxla
        time.sleep(60)


# =========================
# BACKGROUND THREAD
# =========================

scanner_thread = Thread(
    target=run_scanner,
    daemon=True
)

scanner_thread.start()


# =========================
# RENDER HEALTH CHECK
# =========================

@app.route("/")
def home():

    return (
        "SMC Pro Level 3 Engine "
        "Active & Scanning!",
        200
    )


# =========================
# START SERVER
# =========================

if __name__ == "__main__":

    port = int(
        os.environ.get(
            "PORT",
            10000
        )
    )

    app.run(
        host="0.0.0.0",
        port=port
    )
