## CoinSwitch PRO - Auto-Trading Bot (Advanced Filtering Version)
## Trades INR pairs on CoinSwitch, cross-referencing data feeds for reliability.

import time
import json
import requests
import urllib
from urllib.parse import urlencode, urlparse
from cryptography.hazmat.primitives.asymmetric import ed25519
import os
import pandas as pd
import pandas_ta as ta

# --- CONFIGURATION (Hardcoded - NOT RECOMMENDED) ---
API_KEY = os.environ.get("API_KEY")
SECRET_KEY = os.environ.get("SECRET_KEY")

BASE_URL = "https://coinswitch.co"
EXCHANGE = "c2c2"
QUOTE_CURRENCY = "USDT"

# --- Trading & Strategy Parameters ---
TRADE_PERCENT_OF_BALANCE = 0.95
MIN_USDT_BALANCE_TO_TRADE = 10
TRADING_INTERVAL_SECONDS = 300
REQUEST_TIMEOUT = 10
MIN_24H_VOLUME_USDT = 100000  # Using a reasonable default
RSI_PERIOD = 14
RSI_OVERSOLD_THRESHOLD = 30
BBANDS_PERIOD = 20
BBANDS_STD_DEV = 2


# --- UTILITY FUNCTION ---
def safe_float_convert(value):
    """Safely converts a value to a float, returning 0.0 on failure."""
    if value is None: return 0.0
    try:
        return float(value)
    except (ValueError, TypeError):
        return 0.0


# --- AUTHENTICATION & API UTILITIES ---
def get_server_time():
    try:
        res = requests.get(f"{BASE_URL}/trade/api/v2/time", timeout=REQUEST_TIMEOUT)
        res.raise_for_status()
        return str(res.json().get("serverTime"))
    except Exception:
        return str(int(time.time() * 1000))


def generate_signature(method, endpoint, params, epoch_time, payload_str=None):
    path = endpoint
    if method == "GET" and params:
        path += ('&', '?')[urlparse(path).query == ''] + urlencode(params)
    unquoted_path = urllib.parse.unquote_plus(path)
    signature_msg = method + unquoted_path
    if payload_str:
        signature_msg += payload_str
    signature_msg += epoch_time
    request_string = signature_msg.encode('utf-8')
    secret_bytes = bytes.fromhex(SECRET_KEY)
    key = ed25519.Ed25519PrivateKey.from_private_bytes(secret_bytes)
    return key.sign(request_string).hex()


def get_headers(method, endpoint, params={}, payload_str=None):
    epoch_time = get_server_time()
    signature = generate_signature(method, endpoint, params, epoch_time, payload_str)
    return {
        'Content-Type': 'application/json',
        'X-AUTH-APIKEY': API_KEY, 'X-AUTH-SIGNATURE': signature, 'X-AUTH-EPOCH': epoch_time
    }


def safe_v2_request(method, endpoint, params=None, json_payload=None):
    try:
        payload_str = json.dumps(json_payload, separators=(',', ':'), sort_keys=True) if json_payload else None
        headers = get_headers(method, endpoint, params, payload_str)
        url = BASE_URL + endpoint
        if method.upper() == 'GET':
            res = requests.get(url, headers=headers, params=params, timeout=REQUEST_TIMEOUT)
        elif method.upper() == 'POST':
            res = requests.post(url, headers=headers, data=payload_str, timeout=REQUEST_TIMEOUT)
        else:
            return None
        res.raise_for_status()
        return res.json()
    except requests.exceptions.RequestException as e:
        print(f"[ERROR] Request to {endpoint} failed: {e}")
        if e.response: print(f"[ERROR] Response Body: {e.response.text}")
    return None


# --- API FUNCTIONS ---
def get_usdt_balance():
    endpoint = "/trade/api/v2/user/portfolio"
    res = safe_v2_request("GET", endpoint)
    if res and res.get("data"):
        for item in res.get("data", []):
            if item["currency"].lower() == "usdt":
                return float(item["main_balance"])
    print(f"[WARN] Could not fetch {QUOTE_CURRENCY} balance.")
    return 0.0


def get_market_tickers_cs():
    """Finds liquid USDT pairs by calculating estimated quote volume."""
    endpoint = "/trade/api/v2/24hr/all-pairs/ticker"
    params = {"exchange": EXCHANGE}
    response_data = safe_v2_request("GET", endpoint, params=params)
    if not response_data: return []
    ticker_dictionary = response_data.get('data', response_data)
    if not isinstance(ticker_dictionary, dict): return []

    tickers = []
    for symbol, item in ticker_dictionary.items():
        if symbol.endswith(f"/{QUOTE_CURRENCY}"):
            # --- FINAL FIX: Calculate estimated USDT volume ---
            base_volume = safe_float_convert(item.get("baseVolume"))
            price = safe_float_convert(item.get("lastPrice"))

            estimated_quote_volume = base_volume * price

            if estimated_quote_volume > MIN_24H_VOLUME_USDT and price > 0:
                tickers.append({
                    "symbol": symbol.replace('/', '_'),
                    "price": price,
                    "volume": estimated_quote_volume  # Store the calculated volume
                })
    return tickers


def get_candles_from_binance(cs_symbol):
    try:
        binance_symbol = cs_symbol.replace('_', '')
        url = "https://api.binance.com/api/v3/klines"
        params = {"symbol": binance_symbol, "interval": "1h", "limit": 50}
        res = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
        res.raise_for_status()
        return [candle[:6] for candle in res.json()]
    except requests.exceptions.RequestException:
        return []


def place_buy_order(symbol, quantity, price):
    endpoint = "/trade/api/v2/order"
    payload = {
        "side": "buy", "symbol": symbol.replace('_', '/'), "type": "limit",
        "price": price, "quantity": quantity, "exchange": EXCHANGE
    }
    print(f"[ACTION] Preparing to place buy order: {payload}")
    response = safe_v2_request("POST", endpoint, json_payload=payload)
    if response:
        print(f"[SUCCESS] Order response received: {response}")
    else:
        print(f"[FAILURE] Failed to place buy order for {symbol}.")


# --- MAIN TRADING BOT LOGIC ---
def run_trading_bot():
    if not API_KEY or not SECRET_KEY:
        print("[FATAL] API keys are not set. Please set them as environment variables.")
        return

    usdt_balance = get_usdt_balance()
    print(f"[INFO] Current {QUOTE_CURRENCY} Balance: ${usdt_balance:.2f}")

    if usdt_balance < MIN_USDT_BALANCE_TO_TRADE:
        print("[INFO] Balance is below the minimum required to trade.")
        return

    print(f"[INFO] Fetching liquid {QUOTE_CURRENCY} markets from CoinSwitch...")
    candidate_coins = get_market_tickers_cs()
    if not candidate_coins:
        print("[INFO] No coins meet the minimum volume criteria.")
        return

    print(f"[INFO] Found {len(candidate_coins)} liquid coin(s). Analyzing...")

    for coin in candidate_coins:
        symbol = coin["symbol"]
        print(f"\n--- Analyzing {symbol} ---")

        candles_data = get_candles_from_binance(symbol)

        if not candles_data or len(candles_data) < BBANDS_PERIOD:
            print(f"[SKIP] Not enough candle data for {symbol} from Binance.")
            continue

        df = pd.DataFrame(candles_data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['close'] = pd.to_numeric(df['close'])

        df.ta.bbands(length=BBANDS_PERIOD, std=BBANDS_STD_DEV, append=True)
        df.ta.rsi(length=RSI_PERIOD, append=True)

        latest = df.iloc[-1]
        latest_price = latest['close']
        lower_band = latest[f'BBL_{BBANDS_PERIOD}_{BBANDS_STD_DEV:.1f}']
        latest_rsi = latest[f'RSI_{RSI_PERIOD}']

        if pd.isna(lower_band) or pd.isna(latest_rsi):
            print(f"[SKIP] Could not calculate indicators for {symbol}.")
            continue

        print(f"[DATA] {symbol} | Price: ${latest_price:.4f} | Lower Band: ${lower_band:.4f} | RSI: {latest_rsi:.2f}")

        if latest_price <= lower_band and latest_rsi < RSI_OVERSOLD_THRESHOLD:
            price_to_buy = coin["price"]
            print(f"[SIGNAL] ✅ Buy Signal Detected for {symbol}!")

            amount_to_invest = usdt_balance * TRADE_PERCENT_OF_BALANCE
            quantity_to_buy = round(amount_to_invest / price_to_buy, 6)

            place_buy_order(symbol, quantity_to_buy, price_to_buy)

            print("[INFO] Trade attempted for this cycle. Waiting for the next run.")
            return
        else:
            print(f"[SKIP] {symbol} does not meet buy criteria.")

    print("\n[INFO] Analysis complete. No buy signals found in this cycle.")


# --- MAIN LOOP ---
if __name__ == "__main__":
    print("--- COINSWITCH PRO TRADING BOT (Final Robust Version) ---")
    print("---        DISCLAIMER: USE AT YOUR OWN RISK         ---")
    while True:
        try:
            print(f"\n{'=' * 50}")
            print(f"[CYCLE START] {time.ctime()}")
            run_trading_bot()
            print(f"[CYCLE END] Sleeping for {TRADING_INTERVAL_SECONDS} seconds...")
            print(f"{'=' * 50}")
            time.sleep(TRADING_INTERVAL_SECONDS)
        except KeyboardInterrupt:
            print("\n[INFO] Bot stopped manually. Exiting.")
            break
        except Exception as e:
            print(f"[CRITICAL] An unexpected error occurred in the main loop: {e}")
            time.sleep(60)
