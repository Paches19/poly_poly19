# poly_poly.py - Base central del bot Gabagool con logs y live prices
import asyncio
from data_buffer import get_all_ticks, clear_buffer, get_latest_snapshot
from market_detector import get_active_15min_market
from strategy import Strategy
from datetime import datetime
import logging
from polymarket_client import live_prices
from datetime import datetime, timezone

# -------------------------
# Configuración logging
# -------------------------
logger = logging.getLogger("PolyPolyBot")

if not logger.handlers:
    logger.setLevel(logging.DEBUG)
    console = logging.StreamHandler()
    console.setLevel(logging.DEBUG)
    formatter = logging.Formatter(
        "%(asctime)s - %(levelname)s - %(message)s"
    )
    console.setFormatter(formatter)
    logger.addHandler(console)



MARKET_DURATION = 15 * 60  # 15 minutos en segundos

# Calculamos el timestamp de inicio del mercado redondeando al múltiplo de 15 min
def get_market_start_ts(ts=None):
    if ts is None:
        ts = datetime.now(timezone.utc).timestamp()
    slot_start = int(ts // MARKET_DURATION) * MARKET_DURATION
    return slot_start

# -------------------------
# Bot strategy
# -------------------------
class PolyPolyBot:
    def __init__(self, initial_capital=1000.0, yes_token=None, no_token=None):
        self.strategy = Strategy(initial_capital=initial_capital)
        self.tendency = 0.0
        self.tick_index = 0

        if yes_token and no_token:
            self.strategy.yes_token = yes_token
            self.strategy.no_token = no_token
            logger.info(f"Tokens iniciales cargados: YES={yes_token}, NO={no_token}")

    def reset_market(self, yes_token=None, no_token=None):
        """Resetea tendency, tick_index y actualiza tokens del mercado"""
        self.tendency = 0.0
        self.tick_index = 0
        self.market_start_ts = get_market_start_ts()
        logger.info("Cambio de mercado: tendency y tick_index reseteados")

        if yes_token and no_token:
            self.strategy.yes_token = yes_token
            self.strategy.no_token = no_token
            logger.info(f"Nuevos tokens cargados: YES={yes_token}, NO={no_token}")
        self.strategy.reset()

    async def run(self, tick_interval=0.5):
        logger.info("Bot iniciado, esperando ticks...")
        market_start_ts = get_market_start_ts()
        while True:
            current_ts = datetime.now(timezone.utc).timestamp()
            time_elapsed = current_ts - market_start_ts
            progress = time_elapsed / MARKET_DURATION
            # No entrar si no ha pasado el 35% del mercado
            if progress < 0.05: #OJO CAMBIAR A 0.35 tras testing
                print("Waiting for 35% of the market to enter", progress)
                clear_buffer()
                await asyncio.sleep(tick_interval)
                continue
            if self.strategy.locked:
                clear_buffer()
                await asyncio.sleep(tick_interval)
                continue
            self.tick_index += 1

            ticks = get_all_ticks()
            batch_size  = len(ticks)
            logger.debug(f"Ticks en buffer: {batch_size }")

            if batch_size  == 0:
                await asyncio.sleep(tick_interval)
                continue

            latest_prices = get_latest_snapshot(
                self.strategy.yes_token,
                self.strategy.no_token
            )
            if not latest_prices:
                clear_buffer()
                await asyncio.sleep(tick_interval)
                continue

            price_yes = latest_prices["price_yes"]
            price_no  = latest_prices["price_no"]

            # Tendencia incremental (correcta)
            if price_yes > price_no:
                self.tendency += price_yes - price_no
            else:
                self.tendency -= price_yes - price_no

            action, qty, price = self.strategy.decide_and_execute(
                ts=latest_prices["timestamp"],
                price_yes=price_yes,
                price_no=price_no,
                tick_index=self.tick_index,
                tendency=self.tendency,
            )
            clear_buffer()

            if action in ("YES", "NO", "SAFE_YES", "SAFE_NO"):
                order = {
                    "timestamp": current_ts,
                    "action": action,
                    "qty": qty,
                    "price": price
                }
                logger.info(f"[Tick {self.tick_index}] Orden generada: {order}")
            else:
                logger.debug(f"[Tick {self.tick_index}] Acción tomada: {action}")

            clear_buffer()
            await asyncio.sleep(tick_interval)


# -------------------------------
if __name__ == "__main__":
    market_info = get_active_15min_market()
    if not market_info:
        print("No se encontró mercado activo. Saliendo.")
        exit()

    yes_token = market_info["yes_token"]
    no_token = market_info["no_token"]

    bot = PolyPolyBot(initial_capital=1000.0, yes_token=yes_token, no_token=no_token)
    
    async def main_loop():
        task1 = asyncio.create_task(live_prices(on_market_change=bot.reset_market))
        task2 = asyncio.create_task(bot.run())
        await asyncio.gather(task1, task2)
    asyncio.run(main_loop())