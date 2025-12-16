import asyncio
from dotenv import load_dotenv
import websockets
import json
import time
from datetime import datetime
from market_detector import get_active_15min_market
import os
from data_buffer import add_tick  # Buffer en memoria para ticks

load_dotenv()

# -------------------------
# Variables de entorno
# -------------------------
POLY_API_KEY = os.getenv("POLY_API_KEY")
POLY_PRIVATE_KEY = os.getenv("POLY_PRIVATE_KEY")
POLY_WALLET = os.getenv("POLY_WALLET")
POLY_CHAIN_ID = int(os.getenv("POLY_CHAIN_ID", 137))

# -------------------------
# Config
# -------------------------
WS_URL = "wss://ws-subscriptions-clob.polymarket.com/ws/market"

# -------------------------
# Función Live Tracking WS
# -------------------------
async def live_prices(on_market_change=None):
    while True:
        try:
            market_info = get_active_15min_market()
            if not market_info:
                print("No se encontró mercado activo. Saliendo.")
                return

            yes_token = market_info["yes_token"]
            no_token = market_info["no_token"]
            token_ids = [yes_token, no_token]

            print(f"Suscribiéndose a tokens: {token_ids}")

            async with websockets.connect(WS_URL) as ws:
                await ws.send(json.dumps({
                    "type": "subscribe",
                    "channel": "market",
                    "assets_ids": token_ids
                }))

                while True:
                    try:
                        msg_task = asyncio.create_task(ws.recv())

                        current_ts = int(time.time())
                        next_slot = ((current_ts // 900) + 1) * 900
                        sleep_task = asyncio.create_task(asyncio.sleep(next_slot - current_ts))

                        done, pending = await asyncio.wait(
                            [msg_task, sleep_task],
                            return_when=asyncio.FIRST_COMPLETED
                        )

                        if msg_task in done:
                            raw_msg = msg_task.result()
                            data = json.loads(raw_msg)

                            # ---- Procesamos ticks ----
                            if isinstance(data, list):
                                for msg in data:
                                    process_ws_message(msg, yes_token, no_token)
                            elif isinstance(data, dict):
                                process_ws_message(data, yes_token, no_token)

                        if sleep_task in done:
                            print(f"[{datetime.now()}] Actualizando mercado al nuevo slot de 15 min...")
                            new_market = get_active_15min_market()
                            if new_market:
                                new_tokens = [new_market["yes_token"], new_market["no_token"]]
                                if set(new_tokens) != set(token_ids):
                                    token_ids = new_tokens
                                    yes_token, no_token = new_tokens
                                    await ws.send(json.dumps({
                                        "type": "subscribe",
                                        "channel": "market",
                                        "assets_ids": token_ids
                                    }))
                                    print(f"Suscripción actualizada a tokens: {token_ids}")
                                    if on_market_change:
                                        on_market_change()

                        for task in pending:
                            task.cancel()
                        await asyncio.sleep(0.2)

                    except Exception as e:
                        print(f"Error WS: {e}, esperando 5s antes de continuar...")
                        break
        except Exception as e:
                        print(f"Error WS: {e}, esperando 5s antes de continuar...")
                        await asyncio.sleep(5)
                        continue
        
        

# -------------------------
# Procesamiento de mensajes WS
# -------------------------
def process_ws_message(message, yes_token, no_token):
    event_type = message.get("event_type", "")

    if event_type == "price_change" and "price_changes" in message:
        for change in message["price_changes"]:
            asset_id = change.get("asset_id")
            if not asset_id:
                continue
            tick = {
                "event_type": "price_change",
                "asset_id": asset_id,
                "timestamp": message.get("timestamp"),
                "price": float(change.get("price", 0.0)),
                "size": float(change.get("size", 0.0)),
                "side": change.get("side"),
            }
            normalize_and_add_tick(tick, yes_token, no_token)

# -------------------------
# Normalización de ticks
# -------------------------
def normalize_and_add_tick(tick, yes_token, no_token):
    asset_id = tick.get("asset_id")
    if not asset_id:
        return

    tick["price_yes"] = 0.0
    tick["price_no"] = 0.0

    # Usamos price real de trade
    if asset_id == yes_token:
        tick["price_yes"] = float(tick.get("price", 0.0))
    elif asset_id == no_token:
        tick["price_no"] = float(tick.get("price", 0.0))

    add_tick(tick)
