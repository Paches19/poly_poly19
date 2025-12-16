# strategy.py
from datetime import datetime, timezone
from typing import Tuple
from data_buffer import get_latest_snapshot
import logging

MARKET_DURATION = 15 * 60

logger = logging.getLogger("PolyPolyBot")

# Calculamos el timestamp de inicio del mercado redondeando al múltiplo de 15 min
def get_market_start_ts(ts=None):
    if ts is None:
        ts = datetime.now(timezone.utc).timestamp()
    slot_start = int(ts // MARKET_DURATION) * MARKET_DURATION
    return slot_start

class Strategy:
    def __init__(
        self,
        initial_capital: float = 1000.0,
        target_pair_cost: float = 0.975,
        max_order_pct: float = 0.20,
        min_order_value: float = 10.0,
        entry_threshold: float = 0.35,
        yes_token: str = "",
        no_token: str = "",
    ):
        # Parámetros
        self.initial_capital = float(initial_capital)
        self.capital = float(initial_capital)
        self.target = float(target_pair_cost)
        self.max_order_pct = float(max_order_pct)
        self.min_order_value = float(min_order_value)
        self.entry_threshold = float(entry_threshold)

        self.yes_token = yes_token
        self.no_token = no_token

        # Estado acumulado
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

    def decide_and_execute(self, ts, price_yes, price_no, tick_index, tendency) -> Tuple[str, float, float]:
        if self.locked:
            logger.debug(f"[Tick {tick_index}] Estrategia bloqueada (LOCKED)")
            return "LOCKED", 0.0, 0.0

        if self.guaranteed_profit() > 0:
            self.locked = True
            print("Strategy locked. Guaranteed Profit: ", self.strategy.guaranteed_profit())

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

        for side, price in [("YES", price_yes), ("NO", price_no)]:
            if price <= 0 or self.capital < self.min_order_value:
                continue
            logger.debug(f"[TICK {tick_index}] Evaluating side={side} price={price:.4f}")
            # Primera entrada: sólo si precio está por debajo del umbral
            if self.qty_yes == 0 and self.qty_no == 0:
                if price > self.entry_threshold or price < 0.3:
                    logger.debug(
                        f"[TICK {tick_index}] SKIP {side} → entry threshold (price={price:.4f})"
                    )
                    continue
            # No permitir comprar el mismo lado si el otro está vacío
            if self.qty_yes > 0 and self.qty_no == 0 and side == "YES":
                logger.debug(f"[TICK {tick_index}] SKIP YES → waiting for NO")
                continue
            if self.qty_no > 0 and self.qty_yes == 0 and side == "NO":
                logger.debug(f"[TICK {tick_index}] SKIP NO → waiting for YES")
                continue

            # qty objetivo por % de capital
            qty_by_cash = max_cash_this_trade / price  # contracts

            # qty mínimo para balancear
            imbalance_qty = max( (self.qty_no - self.qty_yes) if side == "YES" else (self.qty_yes - self.qty_no), 0.0)

            # qty final en CONTRATOS
            base_qty = max(qty_by_cash, imbalance_qty)

            # límite duro por capital disponible
            max_qty_by_capital = self.capital / price
            base_qty = min(base_qty, max_qty_by_capital)

            # Comprobar valor mínimo de orden
            if base_qty * price < self.min_order_value:
                continue

            # Simulación de nuevo pair cost
            new_pair = self._simulate_new_pair(side, base_qty, price)

            enter = None
            if self.qty_yes == 0 or self.qty_no == 0:
                enter = new_pair < self.target
                logger.debug(
                    f"[TICK {tick_index}] {side} qty={base_qty:.2f} "
                    f"new_pair={new_pair:.4f} enter={enter}")

            if not enter:
                market_start_ts = get_market_start_ts()
                current_ts = datetime.now(timezone.utc).timestamp()
                time_elapsed = current_ts - market_start_ts
                progress = time_elapsed / MARKET_DURATION
                if self.qty_yes > 0 and self.qty_no == 0 and tendency / tick_index > 0.5 and progress > MARKET_DURATION * 0.5:
                    qty_safe = (self.qty_yes * self.avg_yes()) / price_no
                    qty_safe = min(qty_safe, self.capital / price_no)
                    if qty_safe * price_no <= self.capital:
                        self.capital -= qty_safe * price_no
                        self.qty_no += qty_safe
                        self.cost_no += qty_safe * price_no
                        trade_info = {
                            "ts": str(ts),
                            "action": "SAFE_NO",
                            "price": round(price_no, 5),
                            "qty": round(qty_safe, 2),
                            "capital_left": round(self.capital, 2),
                        }
                        self.trades.append(trade_info)
                        logger.info(f"[Tick {tick_index}] Trade ejecutado: {trade_info}")
                        self.locked = True
                        print("Strategy locked. Guaranteed Profit: ", self.strategy.guaranteed_profit())
                        self.safe += 1
                        return "SAFE_NO", qty_safe, price_no

                elif self.qty_no > 0 and self.qty_yes == 0 and tendency / tick_index < 0.5 and progress > MARKET_DURATION * 0.5:
                    qty_safe = (self.qty_no * self.avg_no()) / price_yes
                    qty_safe = min(qty_safe, self.capital / price_yes)
                    if qty_safe * price_yes <= self.capital:
                        self.capital -= qty_safe * price_yes
                        self.qty_yes += qty_safe
                        self.cost_yes += qty_safe * price_yes
                        trade_info = {
                            "ts": str(ts),
                            "action": "SAFE_YES",
                            "price": round(price_yes, 5),
                            "qty": round(qty_safe, 2),
                            "capital_left": round(self.capital, 2),
                        }
                        self.trades.append(trade_info)
                        logger.info(f"[Tick {tick_index}] Trade ejecutado: {trade_info}")
                        self.locked = True
                        print("Strategy locked. Guaranteed Profit: ", self.strategy.guaranteed_profit())
                        self.safe += 1
                        return "SAFE_YES", qty_safe, price_yes
                continue

            # Escogemos la mejor mejora de pair_cost
            if best_action == "HOLD" or new_pair < best_new_pair:
                best_action = side
                best_qty = base_qty
                best_price = price
                best_new_pair = new_pair

        # Ejecutar orden
        if best_action in ("YES", "NO") and best_qty > 0:
            total_cost = best_qty * best_price
            self.capital -= total_cost
            if best_action == "YES":
                self.qty_yes += best_qty
                self.cost_yes += total_cost
            else:
                self.qty_no += best_qty
                self.cost_no += total_cost

            balance_ratio = (
                min(self.qty_yes, self.qty_no) / (self.qty_yes + self.qty_no + 1e-9)
                if (self.qty_yes + self.qty_no) > 0 else 0.0
            )
            logger.debug(
                f"[Tick {tick_index}] Capital después del trade: {self.capital:.2f}"
            )
            trade_info = {
                "ts": str(ts),
                "action": best_action,
                "price": round(best_price, 5),
                "qty": round(best_qty, 2),
                "pair_cost_after": round(best_new_pair, 4),
                "balance_ratio": round(balance_ratio, 3),
                "guaranteed_profit_after": round(self.guaranteed_profit(), 2),
                "capital_left": round(self.capital, 2),
            }
            self.trades.append(trade_info)
            logger.info(f"[Tick {tick_index}] Trade ejecutado: {trade_info}")

        if self.guaranteed_profit() > 0:
            self.locked = True
            print("Strategy locked. Guaranteed Profit: ", self.guaranteed_profit())

        return best_action, best_qty, best_price