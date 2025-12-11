# strategy.py - GABAGOOL REAL 2025 (versión FINAL compatible con backtest)
from typing import Tuple

class GabagoolStrategy:
    def __init__(
        self,
        initial_capital: float = 1000.0,
        target_pair_cost: float = 0.98,
        max_order_pct: float = 0.30,
        min_order_value: float = 30.0,
    ):
        self.initial_capital = initial_capital
        self.capital = initial_capital
        self.target = target_pair_cost
        self.max_order_pct = max_order_pct
        self.min_order_value = min_order_value

        self.qty_yes = 0.0
        self.cost_yes = 0.0
        self.qty_no = 0.0
        self.cost_no = 0.0

        self.locked = False
        self.trades = []

    def reset(self):
        self.capital = self.initial_capital
        self.qty_yes = self.qty_no = 0.0
        self.cost_yes = self.cost_no = 0.0
        self.locked = False
        self.trades = []

    def avg_yes(self) -> float: return self.cost_yes / self.qty_yes if self.qty_yes > 0 else 0.0
    def avg_no(self) -> float: return self.cost_no / self.qty_no if self.qty_no > 0 else 0.0
    def pair_cost(self) -> float: return self.avg_yes() + self.avg_no()
    def guaranteed_profit(self) -> float: return min(self.qty_yes, self.qty_no) - (self.cost_yes + self.cost_no)

    def decide_and_execute(self, price_yes: float, price_no: float, ts) -> Tuple[str, float, float]:
        if self.locked:
            return "HOLD", 0.0, self.pair_cost()

        current_pair = self.pair_cost() or 999.0

        if self.guaranteed_profit() > 0.5:
            self.locked = True
            return "LOCKED", 0.0, current_pair

        best_action = "HOLD"
        best_qty = 0.0
        best_new_pair = current_pair

        # Primera compra: entra si un lado está muy barato
        if self.qty_yes + self.qty_no == 0:
            if price_yes < 0.45 or price_no < 0.45:
                side = "YES" if price_yes < price_no else "NO"
                price = price_yes if side == "YES" else price_no
                qty = min((self.capital * self.max_order_pct) / price, self.capital / price)
                cost = qty * price
                self.capital -= cost

                if side == "YES":
                    self.qty_yes += qty
                    self.cost_yes += cost
                else:
                    self.qty_no += qty
                    self.cost_no += cost

                self.trades.append({"side": side, "price": price, "qty": qty})
                return side, qty, self.pair_cost()

            return "HOLD", 0.0, current_pair

        # Compras siguientes: solo si baja el pair_cost
        candidates = []
        for side, price in [("YES", price_yes), ("NO", price_no)]:
            if price <= 0 or self.capital < self.min_order_value:
                continue
            qty = min((self.capital * self.max_order_pct) / price, self.capital / price)
            if qty * price < self.min_order_value:
                continue

            if side == "YES":
                new_cost = self.cost_yes + qty * price
                new_qty = self.qty_yes + qty
                new_avg = new_cost / new_qty
                new_pair = new_avg + self.avg_no()
            else:
                new_cost = self.cost_no + qty * price
                new_qty = self.qty_no + qty
                new_avg = new_cost / new_qty
                new_pair = self.avg_yes() + new_avg

            if new_pair < best_new_pair:
                best_action, best_qty, best_new_pair = side, qty, new_pair

        if best_action != "HOLD":
            price = price_yes if best_action == "YES" else price_no
            cost = best_qty * price
            self.capital -= cost

            if best_action == "YES":
                self.qty_yes += best_qty
                self.cost_yes += cost
            else:
                self.qty_no += best_qty
                self.cost_no += cost

            self.trades.append({"side": best_action, "price": price, "qty": best_qty})

        if best_new_pair < self.target or self.guaranteed_profit() > 0:
            self.locked = True

        return best_action, best_qty, best_new_pair