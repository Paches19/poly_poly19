# data_buffer.py
import threading
from datetime import datetime
from typing import Optional, Dict

# -------------------------
# Estado interno
# -------------------------
_lock = threading.Lock()

# Último tick por asset_id (cache fijo)
_ticks: Dict[str, dict] = {}

# -------------------------
# API pública
# -------------------------
def add_tick(tick: dict) -> None:
    """
    Guarda el último tick de un asset.
    El tamaño de _ticks es fijo (1 entrada por asset_id).
    """
    asset_id = tick.get("asset_id")
    if not asset_id:
        return

    with _lock:
        _ticks[asset_id] = tick


def get_latest_snapshot(yes_token: str, no_token: str) -> Optional[dict]:
    with _lock:
        yes = _ticks.get(yes_token)
        no  = _ticks.get(no_token)

    # ⚠️ Protege contra ticks incompletos
    required_keys = ["bid", "ask", "mid", "timestamp"]
    if not yes or not no:
        return None
    if not all(k in yes for k in required_keys) or not all(k in no for k in required_keys):
        return None

    return {
        "timestamp": max(yes["timestamp"], no["timestamp"]),
        "mid_yes": yes["mid"],
        "mid_no": no["mid"],
        "bid_yes": yes["bid"],
        "ask_yes": yes["ask"],
        "bid_no": no["bid"],
        "ask_no": no["ask"],
    }
