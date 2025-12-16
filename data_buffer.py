# data_buffer.py
from collections import deque
import threading
import logging
from datetime import datetime

# -------------------------
# Configuración del buffer
# -------------------------
MAX_TICKS = 500  # Mantener hasta 500 ticks recientes
_buffer = deque(maxlen=MAX_TICKS)
_lock = threading.Lock()

# -------------------------
# Funciones de acceso
# -------------------------
def add_tick(tick: dict):
    """
    Agrega un tick recibido del websocket al buffer.
    tick: dict con datos del mercado (price_change o book)
    """
    with _lock:
        _buffer.append(tick)

def get_all_ticks():
    """
    Devuelve copia de todos los ticks en memoria.
    """
    with _lock:
        return list(_buffer)

def clear_buffer():
    """
    Limpia todos los ticks almacenados en el buffer.
    """
    with _lock:
        _buffer.clear()

# -------------------------
# Snapshot fusionado YES/NO
# -------------------------
def get_latest_snapshot(yes_token: str, no_token: str):
    """
    Devuelve el último snapshot fusionado con:
    {
        'price_yes': float,
        'price_no': float,
        'timestamp': str
    }
    """
    price_yes = None
    price_no = None
    timestamp = None

    with _lock:
        for tick in reversed(_buffer):
            asset_id = tick.get("asset_id")
            ts = tick.get("timestamp")
            if asset_id == yes_token and tick.get("price") is not None:
                price_yes = tick["price"]
                timestamp = ts
            elif asset_id == no_token and tick.get("price") is not None:
                price_no = tick["price"]
                timestamp = ts
            if price_yes is not None and price_no is not None:
                break

    if price_yes is None or price_no is None:
        return None

    return {
        "price_yes": price_yes,
        "price_no": price_no,
        "timestamp": timestamp or datetime.now().isoformat()
    }
