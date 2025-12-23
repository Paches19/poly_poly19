import asyncio
import json
from datetime import datetime
import websockets

from market_detector import get_active_15min_market
from data_buffer import add_tick

WS_URL = "wss://ws-subscriptions-clob.polymarket.com/ws/market"

# Estado local del order book (top of book)
ORDER_BOOKS = {}


# -------------------------
# Procesar BOOK (fuente real de precios)
# -------------------------
def process_book_message(message, yes_token, no_token):
    asset_id = message.get("asset_id")
    if asset_id not in (yes_token, no_token):
        return

    bids = message.get("bids", [])
    asks = message.get("asks", [])

    if not bids or not asks:
        return

    try:
        best_bid = max(float(b["price"]) for b in bids)
        best_ask = min(float(a["price"]) for a in asks)
    except (KeyError, ValueError):
        return

    if best_bid <= 0 or best_ask <= 0:
        return

    mid = (best_bid + best_ask) / 2
    ts = message.get("timestamp")

    # Evitar ticks idénticos
    prev = ORDER_BOOKS.get(asset_id)
    if prev and prev["best_bid"] == best_bid and prev["best_ask"] == best_ask:
        return

    ORDER_BOOKS[asset_id] = {
        "best_bid": best_bid,
        "best_ask": best_ask,
        "mid": mid,
        "timestamp": ts,
    }

    tick = {
        "asset_id": asset_id,
        "timestamp": ts,
        "bid": best_bid,
        "ask": best_ask,
        "mid": mid,
    }

    add_tick(tick)


# -------------------------
# Live tracking WS con cambio de mercado
# -------------------------
async def live_prices(on_market_change=None):
    current_tokens = None

    while True:
        try:
            market_info = get_active_15min_market()
            if not market_info:
                print(f"[{datetime.now()}] No hay mercado activo. Esperando 5s...")
                await asyncio.sleep(5)
                continue

            yes_token = market_info["yes_token"]
            no_token = market_info["no_token"]
            token_ids = [yes_token, no_token]

            if current_tokens != token_ids:
                current_tokens = token_ids
                ORDER_BOOKS.clear()
                if on_market_change:
                    on_market_change(yes_token=yes_token, no_token=no_token)
                print(f"[{datetime.now()}] Cambio de mercado detectado. Tokens: {token_ids}")

            try:
                async with websockets.connect(WS_URL, ping_interval=20) as ws:
                    await ws.send(json.dumps({
                        "type": "subscribe",
                        "channel": "market",
                        "assets_ids": token_ids
                    }))
                    print(f"[{datetime.now()}] WS conectado y suscrito a {token_ids}")

                    while True:
                        raw_msg = await ws.recv()
                        data = json.loads(raw_msg)

                        if isinstance(data, dict):
                            messages = [data]
                        elif isinstance(data, list):
                            messages = data
                        else:
                            continue

                        for msg in messages:
                            if (
                                isinstance(msg, dict)
                                and msg.get("event_type") == "book"
                            ):
                                process_book_message(msg, yes_token, no_token)

            except websockets.ConnectionClosed:
                print(f"[{datetime.now()}] WS cerrado, reconectando en 2s...")
                await asyncio.sleep(2)

            except Exception as e:
                print(f"[{datetime.now()}] Error WS: {e}, reconectando en 5s...")
                await asyncio.sleep(5)

        except Exception as e:
            print(f"[{datetime.now()}] Error general live_prices: {e}")
            await asyncio.sleep(5)
