"""
Scheduler — market-hours automation using APScheduler.

Jobs:
  pre_market  : 09:00 IST — warm up data cache
  post_market : 15:35 IST — daily P&L report, reset state
"""

from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from trader.core.logger import get_logger

logger = get_logger(__name__)

_IST = "Asia/Kolkata"


class Scheduler:
    def __init__(self):
        self._scheduler = BackgroundScheduler(timezone=_IST)
        self._pre_market_hooks: list = []
        self._post_market_hooks: list = []

    def on_pre_market(self, fn):
        self._pre_market_hooks.append(fn)

    def on_post_market(self, fn):
        self._post_market_hooks.append(fn)

    def start(self):
        self._scheduler.add_job(
            lambda: self._run(self._pre_market_hooks, "pre_market"),
            CronTrigger(day_of_week="mon-fri", hour=9, minute=0, timezone=_IST),
            id="pre_market",
        )
        self._scheduler.add_job(
            lambda: self._run(self._post_market_hooks, "post_market"),
            CronTrigger(day_of_week="mon-fri", hour=15, minute=35, timezone=_IST),
            id="post_market",
        )
        self._scheduler.start()
        logger.info("Scheduler started")

    def stop(self):
        self._scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")

    def _run(self, hooks: list, name: str):
        logger.info("Scheduler: %s | %s", name, datetime.now().strftime("%H:%M:%S"))
        for fn in hooks:
            try:
                fn()
            except Exception:
                logger.exception("Error in %s hook", name)
