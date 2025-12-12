# strategy.py - GABAGOOL SIMPLE con seguridad mínima
from typing import Tuple
from datetime import datetime, timedelta
import pandas as pd

class GabagoolStrategy:
    def __init__(
        self,
        initial_capital: float = 1000.0,
        target_pair_cost: float = 0.98,
        max_order_pct: float = 0.7,
        min_order_value: float = 10.0,
        entry_threshold: float = 0.42,
    ):
        # Parámetros
        self.initial_capital = float(initial_capital)
        self.capital = float(initial_capital)
        self.target = float(target_pair_cost)
        self.max_order_pct = float(max_order_pct)
        self.min_order_value = float(min_order_value)
        self.entry_threshold = float(entry_threshold)

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

     # ------------------------------------------------------------------ #
    # Núcleo de la estrategia
    # ------------------------------------------------------------------ #
    def _simulate_new_pair(
        self, side: str, qty: float, price: float
    ) -> float:
        """Devuelve el nuevo pair cost si compramos qty en side a price."""
        if qty <= 0:
            return self.pair_cost()

        if side == "YES":
            new_cost_yes = self.cost_yes + qty * price
            new_qty_yes = self.qty_yes + qty
            avg_yes = new_cost_yes / new_qty_yes
            avg_no = self.avg_no()
        else:  # NO
            new_cost_no = self.cost_no + qty * price
            new_qty_no = self.qty_no + qty
            avg_no = new_cost_no / new_qty_no
            avg_yes = self.avg_yes()

        return avg_yes + avg_no

    def decide_and_execute(self, price_yes: float, price_no: float, ts, tendency, tick_index, total_ticks) -> Tuple[str, float, float]:
        # Si ya está bloqueado el beneficio, no seguimos operando este mercado
        if self.locked:
            action = "LOCKED"
            qty = 0.0
            price = 0.0
            return action, qty, price

        current_pair = self.pair_cost()

        # Control de cash disponible para este tick
        max_cash_this_trade = self.capital * self.max_order_pct

        best_action = "HOLD"
        best_qty = 0.0
        best_price = 0.0
        best_new_pair = current_pair
        buy = False
        # Intentar ambos lados y quedarnos con el que deje mejor pair_cost
        for side, price in [("YES", float(price_yes)), ("NO", float(price_no))]:
            if price <= 0:
                continue
            if self.capital < self.min_order_value:
                continue
            if (tick_index < total_ticks * 0.35):
                continue

            # Primera entrada: sólo si el precio está por debajo del umbral
            if self.qty_yes == 0 and self.qty_no == 0:
                if price > self.entry_threshold or price < 0.2:
                    continue

            # Tamaño por capital disponible
            qty_by_cash = max_cash_this_trade / price if price > 0 else 0.0

            # Además, intentar balancear cantidades (hedge)
            if side == "YES":
                imbalance = max(self.qty_no - self.qty_yes, 0.0)
            else:
                imbalance = max(self.qty_yes - self.qty_no, 0.0)

            # Si hay desequilibrio, al menos queremos cubrir parte
            base_qty = max(qty_by_cash, imbalance)

            # Comprobar valor mínimo de orden
            if base_qty * price < self.min_order_value:
                continue

            new_pair = self._simulate_new_pair(side, base_qty, price)

            enter = None
            if self.qty_yes == 0 and self.qty_no == 0:
                enter = new_pair < self.target
            elif (self.qty_yes == 0 or self.qty_no == 0):
                if side == "YES" and self.qty_yes == 0:
                    enter = new_pair < 0.995
                elif side == "NO" and self.qty_no == 0:
                    enter = new_pair < 0.995
            else:
                enter = new_pair < current_pair

            if not enter:
                if self.qty_yes > 0 and self.qty_no == 0 and tendency / tick_index > 0.5 and tick_index > total_ticks * 0.5:
                    qty_safe = (self.qty_yes * self.avg_yes()) / price_no
                    qty_safe = min(qty_safe, self.capital / price_no)
                    if qty_safe * price_no <= self.capital:
                        self.capital -= qty_safe * price_no
                        self.qty_no += qty_safe
                        self.cost_no += qty_safe * price_no
                        self.trades.append({
                            "ts": str(ts),
                            "action": "SAFE_NO",
                            "price": round(price_no, 5),
                            "qty": round(qty_safe, 2),
                            "capital_left": round(self.capital, 2),
                        })
                        self.locked = True
                        self.safe += 1
                        return "SAFE_NO", qty_safe, price_no

                elif self.qty_no > 0 and self.qty_yes == 0 and tendency / tick_index < 0.5 and tick_index > total_ticks * 0.5:
                    qty_safe = (self.qty_no * self.avg_no()) / price_yes
                    qty_safe = min(qty_safe, self.capital / price_yes)
                    if qty_safe * price_yes <= self.capital:
                        self.capital -= qty_safe * price_yes
                        self.qty_yes += qty_safe
                        self.cost_yes += qty_safe * price_yes
                        self.trades.append({
                            "ts": str(ts),
                            "action": "SAFE_YES",
                            "price": round(price_yes, 5),
                            "qty": round(qty_safe, 2),
                            "capital_left": round(self.capital, 2),
                        })
                        self.locked = True
                        self.safe += 1
                        return "SAFE_YES", qty_safe, price_yes
                continue

            # Escogemos la mejor mejora de pair_cost
            if best_action == "HOLD" or new_pair < best_new_pair:
                best_action = side
                best_qty = base_qty
                best_price = price
                best_new_pair = new_pair

            # Ejecutar, si toca
            if best_action != "HOLD" and best_action in ("YES", "NO") and best_qty > 0:
                total_cost = best_qty * best_price
                self.capital -= total_cost
                buy = True
                if best_action == "YES":
                    self.qty_yes += best_qty
                    self.cost_yes += total_cost
                else:
                    self.qty_no += best_qty
                    self.cost_no += total_cost

                balance_ratio = (
                    min(self.qty_yes, self.qty_no) / (self.qty_yes + self.qty_no + 1e-9)
                    if (self.qty_yes + self.qty_no) > 0
                    else 0.0
                )

                self.trades.append(
                    {
                        "ts": str(ts),
                        "action": best_action,
                        "price": round(best_price, 5),
                        "qty": round(best_qty, 2),
                        "pair_cost_after": round(best_new_pair, 4),
                        "balance_ratio": round(balance_ratio, 3),
                        "guaranteed_profit_after": round(self.guaranteed_profit(), 2),
                        "capital_left": round(self.capital, 2),
                    }
                )

            # Recalcular locked tras la operación
            if self.guaranteed_profit() > 0:
                self.locked = True

            return best_action, best_qty, best_price

