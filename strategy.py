# strategy.py - GABAGOOL SIMPLE: Solo compra si baja Pair Cost
from typing import Tuple

class GabagoolStrategy:
    def __init__(
        self,
        initial_capital: float = 1000.0,
        target_pair_cost: float = 0.95,
        max_order_pct: float = 0.25,  # % del capital disponible por compra
        min_order_value: float = 10.0,
        entry_threshold: float = 0.45,
    ):
        self.initial_capital = initial_capital
        self.capital = initial_capital
        self.target = target_pair_cost
        self.max_order_pct = max_order_pct
        self.min_order_value = min_order_value
        self.entry_threshold = entry_threshold

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

    def avg_yes(self) -> float:
        return self.cost_yes / self.qty_yes if self.qty_yes > 0 else 0.0

    def avg_no(self) -> float:
        return self.cost_no / self.qty_no if self.qty_no > 0 else 0.0

    def pair_cost(self) -> float:
        return self.avg_yes() + self.avg_no()

    def guaranteed_profit(self) -> float:
        return min(self.qty_yes, self.qty_no) - (self.cost_yes + self.cost_no)

    def decide_and_execute(self, price_yes: float, price_no: float, ts) -> Tuple[str, float, float]:

        current_pair = self.pair_cost()

        action = "HOLD"
        qty = 0.0
        best_new_pair = current_pair

        # Probar ambos lados
        for side, price in [("YES", price_yes), ("NO", price_no)]:
            if price <= 0 or self.capital < self.min_order_value:
                continue

            if self.qty_yes == self.qty_no:
                qty_c = min(self.capital * self.max_order_pct / price, self.capital / price)
                if qty_c * price < self.min_order_value:
                    continue
            else:
                if self.qty_yes > self.qty_no:
                    qty_c = self.qty_yes - self.qty_no
                else:
                    qty_c = self.qty_no - self.qty_yes

            # Simular new_pair
            if side == "YES":
                new_cost = self.cost_yes + qty_c * price
                new_qty = self.qty_yes + qty_c
                new_pair_c = (new_cost / new_qty) + self.avg_no()
            else:
                new_cost = self.cost_no + qty_c * price
                new_qty = self.qty_no + qty_c
                new_pair_c = self.avg_yes() + (new_cost / new_qty)

            if self.qty_yes + self.qty_no == 0:
                if price < self.entry_threshold:
                    action = side
                    qty = qty_c
                    best_new_pair = new_pair_c
            elif (self.qty_yes or self.qty_no == 0) and new_pair_c < 0.99:
                action = side
                qty = qty_c
                best_new_pair = new_pair_c
            elif new_pair_c < current_pair:
                action = side
                qty = qty_c
                best_new_pair = new_pair_c

        price = price_yes if action == "YES" else price_no
        cost = qty * price
        self.capital -= cost

        if action == "YES":
            self.qty_yes += qty
            self.cost_yes += cost
        elif action == "NO":
            self.qty_no += qty
            self.cost_no += cost

        self.trades.append({
            "ts": str(ts),
            "action": action,
            "price": round(price, 5),
            "qty": round(qty, 2),
            "pair_cost_after": round(best_new_pair, 4),
            "balance_ratio": round(min(self.qty_yes, self.qty_no) / (self.qty_yes + self.qty_no + 1e-9), 3),
            "guaranteed_profit_after": round(self.guaranteed_profit(), 2),
            "capital_left": round(self.capital, 2),
        })
