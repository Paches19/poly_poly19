# backtest.py - Backtest con capital compuesto y profit real
import pandas as pd
import os
from strategy import GabagoolStrategy
import json

DATA_DIR = "live_data_polling"
LOG_DIR = "trade_logs"
os.makedirs(LOG_DIR, exist_ok=True)

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
):
    current_capital = initial_capital
    total_profit = 0.0
    results = []

    markets = load_all_markets()

    for i, market in enumerate(markets):
        df = market["data"]
        name = market["name"]

        strategy = GabagoolStrategy(initial_capital=current_capital)  # Capital actual
        strategy.reset()

        print(f"Procesando → {name} ({len(df)} ticks) - Capital actual: ${current_capital:.2f}")

        for _, row in df.iterrows():
            p_yes = float(row["price_yes"])
            p_no = float(row["price_no"])
            ts = row["timestamp"]

            strategy.decide_and_execute(p_yes, p_no, ts) 

        # Profit real
        last_row = df.iloc[-1]
        final_price_yes = float(last_row["price_yes"])
        final_price_no = float(last_row["price_no"])

        if final_price_yes > 0.9:
            winner = "YES"
            payout = strategy.qty_yes * 1.0
        elif final_price_no > 0.9:
            winner = "NO"
            payout = strategy.qty_no * 1.0
        else:
            winner = "UNKNOWN"
            payout = 0.0

        total_cost = strategy.cost_yes + strategy.cost_no
        profit_real = payout - total_cost
        profit_lockeado = strategy.guaranteed_profit()
        profit_final = max(profit_lockeado, profit_real)

        # Actualizar capital compuesto
        current_capital += profit_final
        total_profit += profit_final

        capital_used = initial_capital - strategy.capital  # Usado en este mercado

        results.append({
            "market": name,
            "market_number": i+1,
            "capital_before": round(initial_capital, 2),
            "profit_final": round(profit_final, 3),
            "capital_after": round(current_capital, 2),
            "profit_real": round(profit_real, 3),
            "profit_lockeado": round(profit_lockeado, 3),
            "winner": winner,
            "final_pair_cost": round(strategy.pair_cost(), 4),
            "trades": len(strategy.trades),
            "roi_%": round((profit_final / capital_used * 100) if capital_used > 0 else 0, 2),
        })

        # Log
        log_file = os.path.join(LOG_DIR, f"{name.replace('.csv', '')}_log.json")
        with open(log_file, "w") as f:
            json.dump({
                "market": name,
                "capital_before": round(initial_capital, 2),
                "profit_final": round(profit_final, 3),
                "capital_after": round(current_capital, 2),
                "trades": strategy.trades
            }, f, indent=2, default=str)

    # Resumen
    df_res = pd.DataFrame(results)
    total_roi = (current_capital - initial_capital) / initial_capital * 100

    print("\n" + "="*80)
    print("RESULTADOS BACKTEST GABAGOOL - CAPITAL COMPUESTO")
    print("="*80)
    print(f"Capital inicial: ${initial_capital:.2f}")
    print(f"Capital final: ${current_capital:.2f}")
    print(f"Profit total: ${total_profit:.2f}")
    print(f"ROI total: {total_roi:.2f}%")
    print(f"Mercados totales: {len(df_res)}")
    print(f"Mercados con profit >0: {(df_res['profit_final'] > 0).sum()}")
    print(f"Win Rate: {(df_res['profit_final'] > 0).sum() / len(df_res) * 100:.1f}%")
    print(f"Trades promedio: {df_res['trades'].mean():.1f}")
    print("="*80)

    print("\nTOP 5 MERCADOS")
    print(df_res.nlargest(5, "profit_final")[["market_number", "market", "profit_final", "capital_after", "trades"]].to_string(index=False))

    print("\nPEORES 5 MERCADOS")
    print(df_res.nsmallest(5, "profit_final")[["market_number", "market", "profit_final", "capital_after", "trades"]].to_string(index=False))

    return df_res, current_capital

if __name__ == "__main__":
    run_backtest(initial_capital=1000.0)