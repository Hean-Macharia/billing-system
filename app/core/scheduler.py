"""Background job scheduler.

Thin wiring layer only - all the actual logic lives in
AutomationService, so every job here is also independently callable via
app.routes.automation for manual triggering/testing without waiting for
a schedule to fire.

Uses APScheduler's AsyncIOScheduler, started/stopped from main.py's
lifespan context manager. Disabled entirely if settings.scheduler_enabled
is False (useful for local dev, or running multiple app instances behind
a load balancer where only one process should run the scheduler -
APScheduler here has no distributed locking, so don't enable it on more
than one instance against the same database).
"""
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.core.config import settings
from app.core.database import database
from app.core.logging import get_logger
from app.services.automation_service import AutomationService

logger = get_logger(__name__)

scheduler = AsyncIOScheduler(timezone="Africa/Nairobi")


async def _job_billing_cycle():
    result = await AutomationService(database.db).run_billing_cycle()
    logger.info(f"[scheduler] billing_cycle: {result}")


async def _job_expiry_sweep():
    result = await AutomationService(database.db).run_expiry_sweep()
    logger.info(f"[scheduler] expiry_sweep: {result}")


async def _job_suspension_sweep():
    result = await AutomationService(database.db).run_suspension_sweep()
    logger.info(f"[scheduler] suspension_sweep: {result}")


async def _job_restoration_sweep():
    result = await AutomationService(database.db).run_restoration_sweep()
    logger.info(f"[scheduler] restoration_sweep: {result}")


async def _job_payment_reconciliation():
    result = await AutomationService(database.db).run_payment_reconciliation()
    logger.info(f"[scheduler] payment_reconciliation: {result}")


def start_scheduler() -> None:
    if not settings.scheduler_enabled:
        logger.info("Scheduler disabled (SCHEDULER_ENABLED=false)")
        return

    # Billing runs once daily, early morning.
    scheduler.add_job(_job_billing_cycle, CronTrigger(hour=6, minute=0), id="billing_cycle", replace_existing=True)

    # Expiry and suspension run hourly - frequent enough that a suspended
    # customer's service comes back promptly after paying (though the
    # instant restoration hook in MpesaService handles the common case
    # immediately; this is the safety net for everything else, cash
    # payments included).
    scheduler.add_job(_job_expiry_sweep, IntervalTrigger(hours=1), id="expiry_sweep", replace_existing=True)
    scheduler.add_job(_job_suspension_sweep, IntervalTrigger(hours=1), id="suspension_sweep", replace_existing=True)
    scheduler.add_job(_job_restoration_sweep, IntervalTrigger(hours=1), id="restoration_sweep", replace_existing=True)

    # Reconciliation runs more often - it's cheap and closes the gap on
    # any STK push whose callback never arrived.
    scheduler.add_job(_job_payment_reconciliation, IntervalTrigger(minutes=15), id="payment_reconciliation", replace_existing=True)

    scheduler.start()
    logger.info("Scheduler started: billing daily@06:00, expiry/suspension/restoration hourly, reconciliation every 15min")


def stop_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")
