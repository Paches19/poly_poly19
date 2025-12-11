# live_polling_monitor.py - Polling estable + detector automático + cambio cada 15min
import time
import csv
from datetime import datetime
import os
from py_clob_client.client import ClobClient
from market_detector import get_active_15min_market

# Cliente read-only (no necesita key)
clob = ClobClient("https://clob.polymarket.com")

OUTPUT_DIR = "live_data_polling"
os.makedirs(OUTPUT_DIR, exist_ok=True)

def monitor_market(market):
    yes_token = market["yes_token"]
    no_token = market["no_token"]
    slug = market["slug"]
    
    filename = f"{OUTPUT_DIR}/{slug}_polling.csv"
    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["timestamp", "price_yes", "price_no", "sum_prices"])
        
        print(f"\n>>> INICIANDO MONITOREO DE {slug}")
        print(f"    Archivo: {filename}")
        print("    Precios cada segundo (solo imprime cambios)\n")
        
        last_yes = None
        last_no = None
        end_time = market["end_ts"] + 60  # Margen
        
        while time.time() < end_time:
            try:
                mid_yes = clob.get_midpoint(yes_token)
                mid_no = clob.get_midpoint(no_token)

                # CORRECTO: extraer 'mid' como string del dict
                price_yes = float(mid_yes.get("mid", "0")) if isinstance(mid_yes, dict) else 0.0
                price_no = float(mid_no.get("mid", "0")) if isinstance(mid_no, dict) else 0.0
                
                ts = datetime.now().isoformat()
                sum_p = price_yes + price_no
                
                # Detectar cambios (incluyendo primera vez)
                changed = (last_yes is None or abs(price_yes - last_yes) > 1e-6 or
                           last_no is None or abs(price_no - last_no) > 1e-6)
                
                if changed:
                    print(f"{ts} | YES: {price_yes:.5f} | NO: {price_no:.5f} | Sum: {sum_p:.5f}")
                    last_yes = price_yes
                    last_no = price_no
                
                writer.writerow([ts, price_yes, price_no, sum_p])
                f.flush()
                
                time.sleep(0.5)
            except KeyboardInterrupt:
                print("\nDetenido por usuario")
                break
            except Exception as e:
                print(f"Error consulta precios: {e}")
                time.sleep(0.5)
    
    print(f"\nMercado terminado. CSV completo: {filename}")

def main():
    print("MONITOR POLLING AUTOMÁTICO BTC Up/Down 15min")
    print("Cambia automáticamente cada 15 minutos\n")
    
    while True:
        market = get_active_15min_market()
        if market:
            monitor_market(market)
            # Esperar al siguiente slot
            next_slot = market["end_ts"] + 60
            sleep_time = next_slot - time.time()
            if sleep_time > 0:
                print(f"\nEsperando próximo mercado ({sleep_time:.0f}s)...")
                time.sleep(sleep_time)
        else:
            print("No mercado activo. Reintentando en 30s...")
            time.sleep(30)

if __name__ == "__main__":
    main()