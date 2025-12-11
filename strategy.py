# strategy.py - GABAGOOL SIMPLE: Solo compra si baja Pair Cost
from typing import Tuple


class GabagoolStrategy:
    def __init__(
        self,
        initial_capital: float = 1000.0,
        target_pair_cost: float = 0.97,
        max_order_pct: float = 0.20,  # % del capital disponible por compra
        min_order_value: float = 10.0,
        entry_threshold: float = 0.40,
    ):
        # Parámetros de la estrategia
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

        self.locked = False  # True cuando ya hay beneficio garantizado
        self.trades = []

    # ------------------------------------------------------------------ #
    # Helpers de estado
    # ------------------------------------------------------------------ #
    def reset(self):
        self.capital = self.initial_capital
        self.qty_yes = 0.0
        self.qty_no = 0.0
        self.cost_yes = 0.0
        self.cost_no = 0.0
        self.locked = False
        self.trades = []

    def avg_yes(self) -> float:
        return self.cost_yes / self.qty_yes if self.qty_yes > 0 else 0.0

    def avg_no(self) -> float:
        return self.cost_no / self.qty_no if self.qty_no > 0 else 0.0

    def pair_cost(self) -> float:
        """avg_YES + avg_NO."""
        return self.avg_yes() + self.avg_no()

    def guaranteed_profit(self) -> float:
        """min(Qty_YES, Qty_NO) - (Cost_YES + Cost_NO)."""
        return min(self.qty_yes, self.qty_no) - (self.cost_yes + self.cost_no)

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

    def decide_and_execute(
        self,
        price_yes: float,
        price_no: float,
        ts,
        debug_tick=None,  # se acepta pero no se usa, para compatibilidad
    ) -> Tuple[str, float, float]:
        """
        Lógica principal:
        - No hace nada si ya hay beneficio garantizado (locked).
        - Solo compra si el nuevo pair_cost baja respecto al actual
          Y además queda por debajo de target_pair_cost.
        - Mantiene tamaños razonables con max_order_pct y min_order_value.

        Devuelve (acción, cantidad, precio_ejecutado).
        """

        # Si ya está bloqueado el beneficio, no seguimos operando este mercado
        if self.locked:
            action = "LOCKED"
            qty = 0.0
            price = 0.0
            return action, qty, price

        current_pair = self.pair_cost()

        # Actualizar flag locked si ya se cumple la fórmula del artículo
        if self.guaranteed_profit() > 0:
            self.locked = True

        # Control de cash disponible para este tick
        max_cash_this_trade = self.capital * self.max_order_pct

        best_action = "HOLD"
        best_qty = 0.0
        best_price = 0.0
        best_new_pair = current_pair

        # Intentar ambos lados y quedarnos con el que deje mejor pair_cost
        for side, price in [("YES", float(price_yes)), ("NO", float(price_no))]:
            if price <= 0:
                continue
            if self.capital < self.min_order_value:
                continue

            # Primera entrada: sólo si el precio está por debajo del umbral
            if self.qty_yes == 0 and self.qty_no == 0:
                if price > self.entry_threshold or price < 0.25:
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

            # Reglas de entrada:
            # 1) Siempre queremos que el pair new < pair actual (baja el coste medio)
            # 2) Y además que el nuevo pair esté por debajo del target de seguridad
            enter = None
            if self.qty_yes == 0 and self.qty_no == 0:
                # Cuando aún no estamos completamente hedgeados,
                # permitimos comprar mientras el pair < target.
                enter = new_pair < self.target
            elif (self.qty_yes == 0 or self.qty_no == 0):
                if side == "YES" and self.qty_yes == 0:
                    enter = new_pair < 0.99
                elif side == "NO" and self.qty_no == 0:
                    enter = new_pair < 0.99
            else:
                enter = new_pair < current_pair

            if not enter:
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