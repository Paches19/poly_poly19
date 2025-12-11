# backtest.py - Backtest con capital compuesto y profit real
import os
import json
from typing import List, Tuple

import pandas as pd

from strategy import GabagoolStrategy

DATA_DIR = "live_data_polling"
LOG_DIR = "trade_logs"
os.makedirs(LOG_DIR, exist_ok=True)


def load_all_markets() -> List[dict]:
    markets: List[dict] = []
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
        except Exception as e:  # noqa: BLE001
            print(f"Error leyendo {file}: {e}")

    print(f"\nTotal mercados válidos: {len(markets)}\n")
    return markets


def run_backtest(initial_capital: float = 1000.0) -> Tuple[pd.DataFrame, float]:
    """
    Ejecuta el backtest sobre todos los CSV en DATA_DIR.
    Usa capital compuesto: las ganancias de cada mercado se suman
    al capital disponible para el siguiente.
    """
    starting_capital = float(initial_capital)
    current_capital = float(initial_capital)
    total_profit = 0.0
    results = []

    markets = load_all_markets()

    for i, market in enumerate(markets, start=1):
        df = market["data"]
        name = market["name"]

        # Capital antes de operar este mercado
        capital_before = current_capital

        # La estrategia ve como "initial_capital" el capital disponible en este mercado
        strategy = GabagoolStrategy(initial_capital=capital_before)
        strategy.reset()

        print(
            f"Procesando → {name} ({len(df)} ticks) - "
            f"Capital actual: ${capital_before:.2f}"
        )

        # Recorremos todos los ticks
        for _, row in df.iterrows():
            p_yes = float(row["price_yes"])
            p_no = float(row["price_no"])
            ts = row["timestamp"]
            strategy.decide_and_execute(p_yes, p_no, ts)

        # --------------------------------------------------------------
        # Cálculo de beneficio real del mercado
        # --------------------------------------------------------------
        last_row = df.iloc[-1]
        final_price_yes = float(last_row["price_yes"])
        final_price_no = float(last_row["price_no"])

        # Heurística simple: si YES está cerca de 1, asumimos que ganó YES, etc.
        if final_price_yes > 0.9 and final_price_yes >= final_price_no:
            winner = "YES"
            payout = strategy.qty_yes * 1.0
        elif final_price_no > 0.9 and final_price_no >= final_price_yes:
            winner = "NO"
            payout = strategy.qty_no * 1.0
        else:
            winner = "UNKNOWN"
            payout = 0.0

        total_cost = strategy.cost_yes + strategy.cost_no
        profit_real = payout - total_cost
        profit_lockeado = strategy.guaranteed_profit()
        profit_final = max(profit_lockeado, profit_real)

        # Actualizar capital compuesto (capital_before + beneficio del mercado)
        current_capital = capital_before + profit_final
        total_profit += profit_final

        # Capital efectivamente utilizado en este mercado
        capital_used = strategy.initial_capital - strategy.capital

        results.append(
            {
                "market": name,
                "market_number": i,
                "capital_before": round(capital_before, 2),
                "profit_final": round(profit_final, 3),
                "capital_after": round(current_capital, 2),
                "profit_real": round(profit_real, 3),
                "profit_lockeado": round(profit_lockeado, 3),
                "winner": winner,
                "final_pair_cost": round(strategy.pair_cost(), 4),
                "trades": len(strategy.trades),
                "roi_%": round(
                    (profit_final / capital_used * 100) if capital_used > 0 else 0,
                    2,
                ),
            }
        )

        # Log detallado de este mercado
        log_file = os.path.join(
            LOG_DIR, f"{os.path.splitext(name)[0]}_log.json"
        )
        with open(log_file, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "market": name,
                    "capital_before": round(capital_before, 2),
                    "profit_final": round(profit_final, 3),
                    "capital_after": round(current_capital, 2),
                    "trades": strategy.trades,
                },
                f,
                indent=2,
                default=str,
            )

    # --------------------------------------------------------------
    # Resumen global
    # --------------------------------------------------------------
    df_res = pd.DataFrame(results)
    if len(df_res) == 0:
        print("No hay resultados de backtest (¿no se cargaron mercados válidos?).")
        return df_res, current_capital

    total_roi = (current_capital - starting_capital) / starting_capital * 100

    print("\n" + "=" * 80)
    print("RESULTADOS BACKTEST GABAGOOL - CAPITAL COMPUESTO")
    print("=" * 80)
    print(f"Capital inicial: ${starting_capital:.2f}")
    print(f"Capital final: ${current_capital:.2f}")
    print(f"Profit total: ${total_profit:.2f}")
    print(f"ROI total: {total_roi:.2f}%")
    print(f"Mercados totales: {len(df_res)}")
    print(f"Mercados con profit >0: {(df_res['profit_final'] > 0).sum()}")
    print(f"Win Rin Rate: {(df_res['profit_final'] > 0).sum() / len(df_res) * 100:.1f}%")
    print(f"Trades promedio: {df_res['trades'].mean():.1f}")
    print("=" * 80)

    print("\nTOP 5 MERCADOS")
    print(
        df_res.nlargest(5, "profit_final")[
            ["market_number", "market", "profit_final", "capital_after", "trades"]
        ].to_string(index=False)
    )

    print("\nPEORES 5 MERCADOS")
    print(
        df_res.nsmallest(5, "profit_final")[
            ["market_number", "market", "profit_final", "capital_after", "trades"]
        ].to_string(index=False)
    )

    return df_res, current_capital


if __name__ == "__main__":
    run_backtest(initial_capital=1000.0)