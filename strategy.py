# strategy.py
from datetime import datetime, timezone
from typing import Tuple
import logging
import json
from pathlib import Path

MARKET_DURATION = 15 * 60
logger = logging.getLogger("PolyPolyBot")
TRADES_LOG_FILE = Path("trades_log.json")

def get_market_start_ts(ts=None):
    if ts is None:
        ts = datetime.now(timezone.utc).timestamp()
    return int(ts // MARKET_DURATION) * MARKET_DURATION


class Strategy:
    def __init__(
        self,
        initial_capital: float = 1000.0,
        target_pair_cost: float = 0.98,
        max_order_pct: float = 0.20,
        min_order_value: float = 10.0,
        entry_threshold: float = 0.4,
        yes_token: str = "",
        no_token: str = "",
    ):
        self.initial_capital = float(initial_capital)
        self.capital = float(initial_capital)
        self.target = float(target_pair_cost)
        self.max_order_pct = float(max_order_pct)
        self.min_order_value = float(min_order_value)
        self.entry_threshold = float(entry_threshold)

        self.yes_token = yes_token
        self.no_token = no_token

        self.qty_yes = 0.0
        self.cost_yes = 0.0
        self.qty_no = 0.0
        self.cost_no = 0.0

        self.locked = False
        self.trades = []
        self.safe = 0

    # ------------------- Helpers ------------------- #
    def reset(self):
        self.capital = self.initial_capital
        self.qty_yes = 0.0
        self.qty_no = 0.0
        self.cost_yes = 0.0
        self.cost_no = 0.0
        self.locked = False
        self.trades = []
        self.safe = 0

    def avg_yes(self) -> float:
        return self.cost_yes / self.qty_yes if self.qty_yes > 0 else 0.0

    def avg_no(self) -> float:
        return self.cost_no / self.qty_no if self.qty_no > 0 else 0.0

    def pair_cost(self) -> float:
        return self.avg_yes() + self.avg_no()

    def guaranteed_profit(self) -> float:
        return min(self.qty_yes, self.qty_no) - (self.cost_yes + self.cost_no)

    def _simulate_new_pair(self, side: str, qty: float, price: float) -> float:
        if qty <= 0:
            return self.pair_cost()

        if side == "YES":
            new_cost_yes = self.cost_yes + qty * price
            new_qty_yes = self.qty_yes + qty
            avg_yes = new_cost_yes / new_qty_yes
            avg_no = self.avg_no()
        else:
            new_cost_no = self.cost_no + qty * price
            new_qty_no = self.qty_no + qty
            avg_no = new_cost_no / new_qty_no
            avg_yes = self.avg_yes()

        return avg_yes + avg_no

    def _log_trade(self, trade: dict):
        """Guarda el trade en trades_log.json"""
        try:
            if TRADES_LOG_FILE.exists():
                with open(TRADES_LOG_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
            else:
                data = []

            data.append(trade)

            with open(TRADES_LOG_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            logger.error(f"No se pudo guardar el trade en JSON: {e}")

    # ------------------- Core ------------------- #
    def decide_and_execute(
        self, ts, price_yes, price_no, tick_index, tendency
    ) -> Tuple[str, float, float]:

        if self.locked:
            logger.debug(f"[Tick {tick_index}] Estrategia bloqueada")
            return "LOCKED", 0.0, 0.0

        if self.guaranteed_profit() > 0:
            self.locked = True
            logger.info(f"Strategy locked. GP={self.guaranteed_profit():.2f}")
            return "LOCKED", 0.0, 0.0

        logger.debug(
            f"\n[TICK {tick_index}] ===== STRATEGY STEP =====\n"
            f"Capital={self.capital:.2f} | "
            f"YES qty={self.qty_yes:.2f} avg={self.avg_yes():.4f} | "
            f"NO qty={self.qty_no:.2f} avg={self.avg_no():.4f} | "
            f"PairCost={self.pair_cost():.4f} | "
            f"Tendency={tendency:.4f}"
        )

        current_pair = self.pair_cost()
        max_cash_this_trade = self.capital * self.max_order_pct

        best_action = "HOLD"
        best_qty = 0.0
        best_price = 0.0
        best_new_pair = current_pair

        for side, price in (("YES", price_yes), ("NO", price_no)):
            if price <= 0 or self.capital < self.min_order_value:
                continue

            # Primera entrada
            if self.qty_yes == 0 and self.qty_no == 0:
                if price > self.entry_threshold or price < 0.22:
                    continue

            # No comprar mismo lado dos veces seguidas
            if self.qty_yes > 0 and self.qty_no == 0 and side == "YES":
                continue
            if self.qty_no > 0 and self.qty_yes == 0 and side == "NO":
                continue

            qty_by_cash = max_cash_this_trade / price
            imbalance_qty = max(
                (self.qty_no - self.qty_yes) if side == "YES"
                else (self.qty_yes - self.qty_no),
                0.0,
            )

            qty = min(
                max(qty_by_cash, imbalance_qty),
                self.capital / price,
            )

            if qty * price < self.min_order_value:
                continue

            new_pair = self._simulate_new_pair(side, qty, price)

            if new_pair < self.target or (self.qty_yes == 0 and self.qty_no == 0):
                best_action = side
                best_qty = qty
                best_price = price
                best_new_pair = new_pair

        # Ejecutar
        if best_action in ("YES", "NO") and best_qty > 0:
            cost = best_qty * best_price
            self.capital -= cost

            if best_action == "YES":
                self.qty_yes += best_qty
                self.cost_yes += cost
            else:
                self.qty_no += best_qty
                self.cost_no += cost

            trade = {
                "ts": str(ts),
                "action": best_action,
                "price": round(best_price, 5),
                "qty": round(best_qty, 2),
                "pair_cost_after": round(best_new_pair, 4),
                "capital_left": round(self.capital, 2),
            }

            self.trades.append(trade)
            self._log_trade(trade)
            logger.info(f"[Tick {tick_index}] Trade ejecutado: {trade}")

        return best_action, best_qty, best_price
