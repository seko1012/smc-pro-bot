import ccxt
import os
import time
import threading
import requests
from datetime import datetime
from flask import Flask
from flask_socketio import SocketIO

app = Flask(__name__)
app.config['SECRET_KEY'] = 'smc_pro_render_free'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='gevent')

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

signal_history = []

exchange = ccxt.bybit({
    'enableRateLimit': True,
    'options': {'defaultType': 'future'}
})

symbols_map = {
    'BTC/USDT:USDT': 'BTC/USDT',
    'ETH/USDT:USDT': 'ETH/USDT',
    'SOL/USDT:USDT': 'SOL/USDT'
}

def send_telegram(text):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"}
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        print(f"Telegram Xətası: {e}", flush=True)

def calc_ema(closes, period=200):
    if len(closes) < period:
        period = len(closes)
    k = 2 / (period + 1)
    ema = closes[0]
    for p in closes[1:]:
        ema = (p * k) + (ema * (1 - k))
    return ema

def calc_rsi(closes, period=14):
    if len(closes) < period + 1:
        return 50.0
    gains, losses = [], []
    for i in range(1, len(closes)):
        diff = closes[i] - closes[i-1]
        if diff >= 0:
            gains.append(diff)
            losses.append(0)
        else:
            gains.append(0)
            losses.append(abs(diff))
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))

def calc_atr(bars, period=14):
    tr_list = []
    for i in range(1, len(bars)):
        h, l, prev_c = bars[i][2], bars[i][3], bars[i-1][4]
        tr = max(h - l, abs(h - prev_c), abs(l - prev_c))
        tr_list.append(tr)
    return sum(tr_list[-period:]) / min(len(tr_list), period) if tr_list else 1.0

def analyze_symbol(symbol):
    global signal_history
    try:
        bars_1h = exchange.fetch_ohlcv(symbol, timeframe='1h', limit=210)
        closes_1h = [b[4] for b in bars_1h]
        ema_200 = calc_ema(closes_1h, 200)
        htf_trend = "BULLISH" if closes_1h[-1] > ema_200 else "BEARISH"

        bars_5m = exchange.fetch_ohlcv(symbol, timeframe='5m', limit=100)
        if not bars_5m or len(bars_5m) < 50:
            return

        closes_5m = [b[4] for b in bars_5m]
        highs_5m = [b[2] for b in bars_5m]
        lows_5m = [b[3] for b in bars_5m]

        price = closes_5m[-1]
        rsi = calc_rsi(closes_5m, 14)
        atr = calc_atr(bars_5m, 14)

        rec_high = max(highs_5m[-20:-1])
        rec_low = min(lows_5m[-20:-1])
        eq = (rec_high + rec_low) / 2
        zone = "DISCOUNT" if price < eq else "PREMIUM"

        fvg_type = None
        for i in range(len(bars_5m) - 4, len(bars_5m) - 1):
            if bars_5m[i-1][2] < bars_5m[i+1][3]:
                fvg_type = "BULLISH"
                break
            elif bars_5m[i-1][3] > bars_5m[i+1][2]:
                fvg_type = "BEARISH"
                break

        signal = None
        if htf_trend == "BULLISH" and zone == "DISCOUNT" and rsi < 55 and fvg_type == "BULLISH":
            signal = "PRO LONG 🚀"
            entry = price
            sl = entry - (atr * 1.5)
            tp = entry + ((entry - sl) * 2.5)

        elif htf_trend == "BEARISH" and zone == "PREMIUM" and rsi > 45 and fvg_type == "BEARISH":
            signal = "PRO SHORT 🔻"
            entry = price
            sl = entry + (atr * 1.5)
            tp = entry - ((sl - entry) * 2.5)

        if signal:
            display_name = symbols_map.get(symbol, symbol)
            entry_str = f"${entry:.2f}"
            
            already_sent = any(
                s['symbol'] == display_name and s['signal'] == signal and s['entry'] == entry_str
                for s in signal_history[:1]
            )

            if not already_sent:
                now_str = datetime.now().strftime('%H:%M:%S')
                history_item = {"symbol": display_name, "signal": signal, "entry": entry_str}
                signal_history.insert(0, history_item)
                if len(signal_history) > 20: signal_history.pop()

                msg = (
                    f"🎯 <b>SMC PRO LEVEL 3 SIGNAL</b>\n\n"
                    f"📌 <b>Parite:</b> {display_name}\n"
                    f"🚦 <b>Siqnal:</b> {signal}\n"
                    f"📈 <b>1H HTF Trend:</b> {htf_trend}\n"
                    f"💵 <b>Giriş:</b> {entry_str}\n"
                    f"🛑 <b>Stop Loss:</b> ${sl:.2f}\n"
                    f"🎯 <b>Take Profit:</b> ${tp:.2f}\n"
                    f"⚖️ <b>Risk/Reward:</b> 1 : 2.5\n"
                    f"🕒 <b>Saat:</b> {now_str}"
                )
                send_telegram(msg)
    except Exception as e:
        print(f"Error ({symbol}): {e}", flush=True)

def bot_loop():
    while True:
        try:
            for symbol in symbols_map.keys():
                analyze_symbol(symbol)
            time.sleep(5)
        except Exception:
            time.sleep(5)

@app.route('/')
def home():
    return "SMC Pro Level 3 Engine Active!"

if __name__ == '__main__':
    t = threading.Thread(target=bot_loop)
    t.daemon = True
    t.start()
    port = int(os.environ.get("PORT", 10000))
    socketio.run(app, host='0.0.0.0', port=port)

