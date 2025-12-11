# backtest.py - Backtest profesional con datos reales de Polymarket 15min
import pandas as pd
import os
from strategy import GabagoolStrategy
from datetime import datetime

# CARPETA CON TUS DATOS REALES
DATA_DIR = "live_data_polling"

def load_all_markets():
    markets = []
    files = [f for f in os.listdir(DATA_DIR) if f.endswith(".csv")]
    print(f"Encontrados {len(files)} archivos en {DATA_DIR}\n")
    
    for file in sorted(files):
        path = os.path.join(DATA_DIR, file)
        try:
            df = pd.read_csv(path, parse_dates=["timestamp"])
            if len(df) < 50:
                print(f"Saltando {file} (muy pocos datos: {len(df)} filas)")
                continue
            df = df.sort_values("timestamp").reset_index(drop=True)
            markets.append({"name": file, "data": df})
            print(f"Cargado {file}: {len(df)} ticks")
        except Exception as e:
            print(f"Error leyendo {file}: {e}")
    
    print(f"\nTotal mercados válidos: {len(markets)}\n")
    return markets

def run_backtest(
    initial_capital=1000.0,
    target_pair_cost=0.99,
    min_order_value=30.0,
    max_order_pct=0.25,
):
    strategy = GabagoolStrategy(
        initial_capital=initial_capital,
        target_pair_cost=target_pair_cost,
        min_order_value=min_order_value,
        max_order_pct=max_order_pct,
    )
    
    markets = load_all_markets()
    results = []

    for market in markets:
        df = market["data"]
        name = market["name"]
        strategy.reset()

        print(f"Procesando → {name} ({len(df)} ticks)")

        for _, row in df.iterrows():
            p_yes = float(row["price_yes"])
            p_no = float(row["price_no"])
            ts = row["timestamp"]

            action, qty, new_pair = strategy.decide_and_execute(p_yes, p_no, ts)

            if strategy.locked:
                print(f"   LOCKED +{strategy.guaranteed_profit():.2f} USD | Pair cost final: {new_pair:.4f}")
                break

        profit = strategy.guaranteed_profit()
        final_pair = strategy.pair_cost()
        locked = profit > 0
        trades = len(strategy.trades)
        capital_used = initial_capital - strategy.capital

        results.append({
            "market": name,
            "profit": round(profit, 3),
            "final_pair_cost": round(final_pair, 4),
            "locked": locked,
            "trades": trades,
            "capital_used": round(capital_used, 1),
            "roi_%": round((profit / capital_used * 100) if capital_used > 0 else 0, 2),
        })

    # === RESUMEN GLOBAL ===
    df_res = pd.DataFrame(results)
    
    locked_count = df_res["locked"].sum()
    total_profit = df_res["profit"].sum()
    avg_profit = df_res["profit"].mean()
    win_rate = locked_count / len(df_res) * 100 if len(df_res) > 0 else 0
    avg_capital = df_res["capital_used"].mean()
    estimated_roi_per_hour = (total_profit / avg_capital * 100 * 4) if avg_capital > 0 else 0  # 4 mercados/hora

    print("\n" + "="*80)
    print("RESULTADOS BACKTEST GABAGOOL - DATOS REALES 15MIN BTC")
    print("="*80)
    print(f"{'Mercados totales':<35}: {len(df_res)}")
    print(f"{'Mercados con profit lockeado':<35}: {locked_count}")
    print(f"{'Win Rate (lock)':<35}: {win_rate:.1f}%")
    print(f"{'Profit total':<35}: ${total_profit:.2f}")
    print(f"{'Profit promedio por mercado':<35}: ${avg_profit:.2f}")
    print(f"{'Capital promedio usado':<35}: ${avg_capital:.1f}")
    print(f"{'Trades promedio':<35}: {df_res['trades'].mean():.1f}")
    print(f"{'ROI promedio por mercado':<35}: {df_res['roi_%'].mean():.1f}%")
    print(f"{'ROI estimado por hora (4 mercados)':<35}: {estimated_roi_per_hour:.1f}%")
    print("="*80)

    # Top 5 y peores 5
    if len(df_res) > 0:
        print("\nTOP 5 MERCADOS (más profit)")
        print(df_res.nlargest(5, "profit")[["market", "profit", "final_pair_cost", "trades", "roi_%"]].to_string(index=False))
        
        print("\nPEORES 5 MERCADOS")
        print(df_res.nsmallest(5, "profit")[["market", "profit", "final_pair_cost", "trades"]].to_string(index=False))

    return df_res

if __name__ == "__main__":
    run_backtest()