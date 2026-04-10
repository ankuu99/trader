"""
Scheduler — market-hours automation using APScheduler.

Jobs
----
pre_market   : 09:00 IST — warm up data cache, validate token
market_open  : 09:15 IST — start live feed, activate strategies
square_off   : 15:15 IST — exit all open positions
post_market  : 15:35 IST — daily P&L report, reset state

Only runs on weekdays. NSE holiday handling is left to config
(add holidays to config.yaml as needed).
"""

from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from trader.core.config import config
from trader.core.logger import get_logger

logger = get_logger(__name__)

_IST = "Asia/Kolkata"


class Scheduler:
    def __init__(self):
        self._scheduler = BackgroundScheduler(timezone=_IST)
        self._hooks: dict[str, list] = {
            "pre_market": [],
            "market_open": [],
            "square_off": [],
            "post_market": [],
        }

    # ------------------------------------------------------------------ #
    # Registration                                                         #
    # ------------------------------------------------------------------ #

    def on_pre_market(self, fn):
        """Register a callable to run at 09:00 IST."""
        self._hooks["pre_market"].append(fn)

    def on_market_open(self, fn):
        """Register a callable to run at 09:15 IST."""
        self._hooks["market_open"].append(fn)

    def on_square_off(self, fn):
        """Register a callable to run at square-off time (config.square_off_time)."""
        self._hooks["square_off"].append(fn)

    def on_post_market(self, fn):
        """Register a callable to run at 15:35 IST."""
        self._hooks["post_market"].append(fn)

    # ------------------------------------------------------------------ #
    # Start / stop                                                         #
    # ------------------------------------------------------------------ #

    def start(self):
        h, m = config.square_off_time.split(":")

        self._scheduler.add_job(
            lambda: self._run("pre_market"),
            CronTrigger(day_of_week="mon-fri", hour=9, minute=0, timezone=_IST),
            id="pre_market",
        )
        self._scheduler.add_job(
            lambda: self._run("market_open"),
            CronTrigger(day_of_week="mon-fri", hour=9, minute=15, timezone=_IST),
            id="market_open",
        )
        self._scheduler.add_job(
            lambda: self._run("square_off"),
            CronTrigger(day_of_week="mon-fri", hour=int(h), minute=int(m), timezone=_IST),
            id="square_off",
        )
        self._scheduler.add_job(
            lambda: self._run("post_market"),
            CronTrigger(day_of_week="mon-fri", hour=15, minute=35, timezone=_IST),
            id="post_market",
        )

        self._scheduler.start()
        logger.info(
            "Scheduler started | square_off=%s IST",
            config.square_off_time,
        )

    def stop(self):
        self._scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")

    # ------------------------------------------------------------------ #
    # Internal                                                             #
    # ------------------------------------------------------------------ #

    def _run(self, event: str):
        logger.info("Scheduler event: %s | %s", event, datetime.now().strftime("%H:%M:%S"))
        for fn in self._hooks[event]:
            try:
                fn()
            except Exception:
                logger.exception("Error in %s hook: %s", event, fn)
