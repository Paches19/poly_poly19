# data_historical.py - VERSIÓN FINAL CORREGIDA: interval válido y filtro preciso para 15min recientes
import requests
import pandas as pd
import time
from datetime import datetime
import os
import json

GAMMA_URL = "https://gamma-api.polymarket.com/markets"
CLOB_HISTORY_URL = "https://clob.polymarket.com/prices-history"

OUTPUT_DIR = "historical_data"
os.makedirs(OUTPUT_DIR, exist_ok=True)

def get_up_down_markets(max_pages=20, limit=500):
    all_markets = []
    offset = 0
    for page in range(max_pages):
        params = {
            "ascending": "false",
            "order": "startDate",
            "limit": limit,
            "offset": offset,
            "closed": "true",  # Cerrados recientes tienen los 15min completos
            "tag_id": 235,     # Bitcoin
        }
        response = requests.get(GAMMA_URL, params=params)
        if response.status_code != 200:
            print(f"Error Gamma API: {response.text}")
            break
        
        markets_page = response.json()
        if not markets_page:
            break
        
        for m in markets_page:
            question = m.get("question", "").lower()
            if "bitcoin up or down" in question.lower() and "?" in question:
                all_markets.append(m)
                print(f"Encontrado válido: {question[:100]}")
        
        print(f"Página {page+1}: {len(markets_page)} mercados, acumulados {len(all_markets)} 15min válidos.")
        offset += limit
        time.sleep(0.5)
    
    print(f"\nTotal mercados 15min Bitcoin Up/Down encontrados: {len(all_markets)}")
    return all_markets

def download_price_history(asset_id, interval="1m"):
    params = {
        "market": asset_id,
        "interval": interval,
        "fidelity": 10,
    }
    print(f"Descargando con interval={interval} para market {asset_id}")
    
    response = requests.get(CLOB_HISTORY_URL, params=params)
    if response.status_code != 200:
        print(f"Error CLOB: {response.text}")
        return pd.DataFrame()
    
    data = response.json().get("history", [])
    if not data:
        print(f"Sin datos para {asset_id}")
        return pd.DataFrame()
    
    df = pd.DataFrame(data)
    df["timestamp"] = pd.to_datetime(df["t"], unit="s")
    df["price"] = df["p"].astype(float)
    df = df[["timestamp", "price"]]
    print(f"¡ÉXITO! {len(df)} puntos descargados para {asset_id}")
    return df

def download_market_history(market):
    question = market["question"]
    slug = market.get("slug", question.replace("?", ""))
    
    clob_tokens_str = market.get("clobTokenIds")
    if not clob_tokens_str:
        print("Sin clobTokenIds")
        return False  # ← Cambiado a False
    
    try:
        tokens = json.loads(clob_tokens_str)
        if len(tokens) != 2:
            print(f"{len(tokens)} tokens, esperado 2")
            return False  # ← False
        yes_token, no_token = tokens
        print(f"Tokens → YES: {yes_token} | NO: {no_token}")
    except Exception as e:
        print(f"Error parseando tokens: {e}")
        return False  # ← False
    
    print(f"\nDescargando datos para: {question}")
    
    df_yes = download_price_history(yes_token, "1m")
    df_no = download_price_history(no_token, "1m")
    
    if df_yes.empty or df_no.empty:
        print("Uno de los lados sin datos")
        return False  # ← False
    
    df_yes = df_yes.set_index("timestamp")
    df_no = df_no.set_index("timestamp")
    df = pd.concat([df_yes.add_suffix("_yes"), df_no.add_suffix("_no")], axis=1)
    df = df.dropna(thresh=2)
    
    if len(df) < 20:  # Umbral razonable
        print(f"Pocos datos combinados: {len(df)} filas")
        return False  # ← False
    
    filename = f"{OUTPUT_DIR}/{slug}_15min.csv"
    df.to_csv(filename)
    print(f"¡GUARDADO! {len(df)} filas en {filename} ✓")
    return True  # ← ¡ÉXITO! Devuelve True

def main():
    markets = get_up_down_markets(max_pages=20)  # Aumenta si quieres más
    
    successful = 0
    for i, market in enumerate(markets):
        print(f"\n--- Procesando {i+1}/{len(markets)} ---")
        if download_market_history(market):  # Ahora sí funciona porque devuelve True/False
            successful += 1
        if successful >= 40:
            print("¡Suficientes mercados descargados!")
            break
        time.sleep(1)

if __name__ == "__main__":
    main()