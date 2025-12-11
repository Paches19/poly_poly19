import requests
import json
import time
from datetime import datetime

GAMMA_URL = "https://gamma-api.polymarket.com/markets"

def get_current_15min_slot_timestamp():
    """Calcula el timestamp del slot actual de 15 minutos (redondea hacia abajo)"""
    now = int(time.time())
    slot_duration = 900  # 15 minutos en segundos
    current_slot = (now // slot_duration) * slot_duration
    return current_slot

def get_active_15min_market():
    """
    Busca el mercado BTC Up/Down 15min activo actual.
    Calcula el timestamp esperado y busca directamente ese slug.
    """
    current_slot_ts = get_current_15min_slot_timestamp()
    expected_slug = f"btc-updown-15m-{current_slot_ts}"

    # Buscar directamente por slug
    params = {
        "slug": expected_slug,
        "active": "true",
        "closed": "false"
    }
    try:
        response = requests.get(GAMMA_URL, params=params, timeout=10)
        if response.status_code != 200:
            print(f"Error Gamma API: {response.status_code} {response.text}")
            return None

        markets = response.json()
        if not markets:
            print(f"No se encontró mercado con slug {expected_slug}")
            return None

        m = markets[0]  # El primero debería ser el correcto
        tokens_str = m.get("clobTokenIds")
        if not tokens_str:
            print("Mercado encontrado pero sin clobTokenIds")
            return None

        tokens = json.loads(tokens_str)
        if len(tokens) != 2:
            print(f"Tokens inesperados: {len(tokens)}")
            return None

        print(f"\nMERCADO ACTIVO ENCONTRADO:")
        print(f"  Pregunta: {m['question']}")
        print(f"  Slug: {m['slug']}")
        print(f"  Inicio: {datetime.fromtimestamp(current_slot_ts)}")
        print(f"  Fin estimado: {datetime.fromtimestamp(current_slot_ts + 900)}")

        return {
            "slug": m["slug"],
            "question": m["question"],
            "yes_token": tokens[0],
            "no_token": tokens[1],
            "start_ts": current_slot_ts,
            "end_ts": current_slot_ts + 900
        }

    except Exception as e:
        print(f"Error buscando mercado activo: {e}")
        return None

# Prueba rápida
if __name__ == "__main__":
    market = get_active_15min_market()
    if market:
        print("¡Listo para monitorear!")
    else:
        print("No se encontró mercado activo en este momento.")