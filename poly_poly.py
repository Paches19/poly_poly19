import asyncio
import logging
from datetime import datetime, timezone

from data_buffer import get_latest_snapshot
from market_detector import get_active_15min_market
from strategy import Strategy
from polymarket_client import live_prices


# -------------------------
# Logging
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


# -------------------------
MARKET_DURATION = 15 * 60


def get_market_start_ts(ts=None):
    if ts is None:
        ts = datetime.now(timezone.utc).timestamp()
    return int(ts // MARKET_DURATION) * MARKET_DURATION


# -------------------------
# Bot
# -------------------------
class PolyPolyBot:
    def __init__(self, initial_capital=1000.0, yes_token=None, no_token=None):
        self.strategy = Strategy(initial_capital=initial_capital)
        self.tendency = 0.0
        self.tick_index = 0
        self.market_start_ts = get_market_start_ts()
        self._last_prices = {"mid_yes": None, "mid_no": None}

        if yes_token and no_token:
            self.strategy.yes_token = yes_token
            self.strategy.no_token = no_token
            logger.info(f"Tokens iniciales: YES={yes_token}, NO={no_token}")

    def reset_market(self, yes_token=None, no_token=None):
        self.tendency = 0.0
        self.tick_index = 0
        self.market_start_ts = get_market_start_ts()
        logger.info("Cambio de mercado: estado reseteado")

        if yes_token and no_token:
            self.strategy.yes_token = yes_token
            self.strategy.no_token = no_token

        self.strategy.reset()

    async def run(self, tick_interval=0.5):
        logger.info("Bot iniciado, esperando snapshots...")

        while True:
            snapshot = get_latest_snapshot(
                self.strategy.yes_token,
                self.strategy.no_token
            )

            if snapshot is None:
                logger.debug("Snapshot incompleto, esperando...")
                await asyncio.sleep(tick_interval)
                continue

            mid_yes = snapshot["mid_yes"]
            mid_no = snapshot["mid_no"]

            # Evitar ticks duplicados
            if (
                self._last_prices["mid_yes"] == mid_yes
                and self._last_prices["mid_no"] == mid_no
            ):
                await asyncio.sleep(tick_interval)
                continue

            self._last_prices["mid_yes"] = mid_yes
            self._last_prices["mid_no"] = mid_no

            self.tick_index += 1
            ask_yes = snapshot["ask_yes"]
            ask_no = snapshot["ask_no"]

            self.tendency += mid_yes - mid_no

            logger.debug(
                f"\n[TICK {self.tick_index}] "
                f"YES mid={mid_yes:.4f} ask={ask_yes:.4f} | "
                f"NO mid={mid_no:.4f} ask={ask_no:.4f} | "
                f"Tendency={self.tendency:.4f}"
            )

            if not self.strategy.locked:
                action, qty, _ = self.strategy.decide_and_execute(
                    ts=snapshot["timestamp"],
                    price_yes=mid_yes,
                    price_no=mid_no,
                    tick_index=self.tick_index,
                    tendency=self.tendency,
                )

                if action == "YES":
                    exec_price = ask_yes
                elif action == "NO":
                    exec_price = ask_no
                else:
                    exec_price = 0.0

                if action in ("YES", "NO", "SAFE_YES", "SAFE_NO"):
                    order = {
                        "timestamp": datetime.now(timezone.utc).timestamp(),
                        "action": action,
                        "qty": qty,
                        "price": exec_price,
                    }
                    logger.info(f"[Tick {self.tick_index}] Orden: {order}")

            await asyncio.sleep(tick_interval)


# -------------------------
# Main
# -------------------------
if __name__ == "__main__":
    market_info = get_active_15min_market()
    if not market_info:
        print("No se encontró mercado activo. Saliendo.")
        exit()

    bot = PolyPolyBot(
        initial_capital=1000.0,
        yes_token=market_info["yes_token"],
        no_token=market_info["no_token"],
    )

    async def main_loop():
        ws_task = asyncio.create_task(
            live_prices(on_market_change=bot.reset_market)
        )
        bot_task = asyncio.create_task(bot.run())
        await asyncio.gather(ws_task, bot_task)

    asyncio.run(main_loop())
