"""Automation service - the actual logic behind every scheduled job.

Kept as one service (rather than scattering logic across the scheduler
module) so every job is independently callable, testable, and
admin-triggerable via app.routes.automation, with the APScheduler wiring
in app.core.scheduler being nothing more than "call these methods on a
timer."

Every run_* method:
  - never lets one record's failure abort the whole batch (try/except
    per item, errors collected into the summary instead of raised)
  - returns a plain dict summary suitable for logging and for the
    /api/v1/automation/status admin endpoint
  - is safe to call concurrently with itself (idempotent per-record:
    re-running finds nothing left to do rather than double-processing)
"""
from datetime import datetime, timedelta, timezone
from typing import Optional

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.config import settings
from app.core.logging import get_logger
from app.models.notification import NotificationType
from app.services.invoice_service import InvoiceService
from app.services.mpesa_service import MpesaService
from app.services.notification_service import NotificationService
from app.services.router_service import RouterService
from app.services.subscription_service import SubscriptionService
from app.services.voucher_service import VoucherService

logger = get_logger(__name__)

OVERDUE_STATUSES = ["sent", "viewed", "partial"]  # pre-overdue states that can age into "overdue"
UNSETTLED_STATUSES = ["sent", "viewed", "partial", "overdue"]  # anything still owed


class AutomationService:
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.notifications = NotificationService(db)

    async def _log_run(self, job_name: str, summary: dict) -> None:
        await self.db.automation_runs.insert_one({
            "job_name": job_name, "summary": summary, "ran_at": datetime.now(timezone.utc),
        })

    # ------------------------------------------------------------------ #
    # 1. Scheduled billing
    # ------------------------------------------------------------------ #
    async def run_billing_cycle(self) -> dict:
        sub_service = SubscriptionService(self.db)
        invoice_service = InvoiceService(self.db)

        due_subs = await sub_service.get_billable_subscriptions()
        invoiced, failed = 0, 0
        errors = []

        for sub in due_subs:
            try:
                invoice = await invoice_service.generate_from_subscription(sub.id, created_by=None)
                invoiced += 1

                customer = await self.db.customers.find_one({"_id": ObjectId(sub.customer_id)})
                if customer:
                    await self.notifications.notify(
                        subject="New invoice", 
                        body=f"Hi {customer.get('full_name', '')}, invoice {invoice.invoice_number} for KES {invoice.total_kes:,.2f} has been generated. Due {invoice.due_date.strftime('%d %b %Y')}.",
                        customer_id=sub.customer_id, phone=customer.get("phone"),
                        notification_type=NotificationType.INVOICE_GENERATED,
                    )
            except Exception as exc:  # noqa: BLE001
                failed += 1
                errors.append(f"subscription {sub.id}: {exc}")
                logger.warning(f"Billing failed for subscription {sub.id}: {exc}")

        summary = {"due": len(due_subs), "invoiced": invoiced, "failed": failed, "errors": errors[:20]}
        await self._log_run("billing_cycle", summary)
        return summary

    # ------------------------------------------------------------------ #
    # 2. Expiry checks
    # ------------------------------------------------------------------ #
    async def run_expiry_sweep(self) -> dict:
        now = datetime.now(timezone.utc)

        # Invoices that have passed their due date but were never marked
        # overdue (nothing else in the system does this - it was purely
        # a read-side filter before Phase 11).
        result = await self.db.invoices.update_many(
            {"status": {"$in": OVERDUE_STATUSES}, "due_date": {"$lt": now}},
            {"$set": {"status": "overdue", "updated_at": now}},
        )
        invoices_marked_overdue = result.modified_count

        # Vouchers - VoucherService already had this from Phase 8, just
        # never had anything actually calling it on a schedule.
        voucher_service = VoucherService(self.db)
        voucher_result = await voucher_service.expire_sweep()

        summary = {
            "invoices_marked_overdue": invoices_marked_overdue,
            "vouchers_expired": voucher_result["expired"],
        }
        await self._log_run("expiry_sweep", summary)
        return summary

    # ------------------------------------------------------------------ #
    # 3. Suspension
    # ------------------------------------------------------------------ #
    async def run_suspension_sweep(self) -> dict:
        now = datetime.now(timezone.utc)
        grace_cutoff = now - timedelta(days=settings.billing_grace_period_days)

        # Customers with at least one unsettled invoice whose due_date is
        # older than the grace period, who aren't already suspended.
        overdue_customer_ids = await self.db.invoices.distinct(
            "customer_id", {"status": {"$in": UNSETTLED_STATUSES}, "due_date": {"$lt": grace_cutoff}}
        )

        suspended, kicked, failed = 0, 0, []
        for customer_id in overdue_customer_ids:
            try:
                customer = await self.db.customers.find_one({"_id": ObjectId(customer_id)})
                if not customer or customer.get("status") == "suspended":
                    continue

                await self.db.customers.update_one(
                    {"_id": ObjectId(customer_id)},
                    {"$set": {"status": "suspended", "updated_at": now}},
                )
                await self.db.subscriptions.update_many(
                    {"customer_id": customer_id, "status": "active"},
                    {"$set": {"status": "suspended", "updated_at": now}},
                )
                suspended += 1

                # Best-effort immediate cutoff: kick any active RADIUS
                # session right now rather than waiting for their next
                # natural re-auth. Never let this fail the suspension
                # itself - the DB status change is what RADIUS actually
                # enforces on the next auth attempt regardless.
                try:
                    radius_user = await self.db.radius_users.find_one({"customer_id": customer_id})
                    if radius_user:
                        session = await self.db.radius_sessions.find_one({"customer_id": customer_id, "status": "online"})
                        if session and session.get("nas_ip_address"):
                            router_doc = await self.db.routers.find_one({"ip_address": session["nas_ip_address"]})
                            if router_doc:
                                router_service = RouterService(self.db)
                                await router_service.disconnect_pppoe_user(str(router_doc["_id"]), radius_user["username"])
                                kicked += 1
                except Exception as kick_exc:  # noqa: BLE001
                    logger.info(f"Could not proactively kick session for customer {customer_id} (will still be blocked on next auth): {kick_exc}")

                await self.notifications.notify(
                    subject="Service suspended",
                    body=f"Hi {customer.get('full_name', '')}, your internet service has been suspended due to an overdue balance. Please make payment to restore access.",
                    customer_id=customer_id, phone=customer.get("phone"),
                    notification_type=NotificationType.SERVICE_SUSPENDED,
                )
            except Exception as exc:  # noqa: BLE001
                failed.append(f"customer {customer_id}: {exc}")
                logger.warning(f"Suspension failed for customer {customer_id}: {exc}")

        summary = {"candidates": len(overdue_customer_ids), "suspended": suspended, "sessions_kicked": kicked, "errors": failed[:20]}
        await self._log_run("suspension_sweep", summary)
        return summary

    # ------------------------------------------------------------------ #
    # 4. Restoration
    # ------------------------------------------------------------------ #
    async def try_restore_customer(self, customer_id: str) -> bool:
        """Instant, event-driven restoration - called right after a
        payment settles (see MpesaService._settle_transaction) so a
        customer isn't stuck waiting for the next sweep. Returns True if
        restored."""
        customer = await self.db.customers.find_one({"_id": ObjectId(customer_id)})
        if not customer or customer.get("status") != "suspended":
            return False

        still_owed = await self.db.invoices.count_documents({
            "customer_id": customer_id, "status": {"$in": UNSETTLED_STATUSES},
        })
        if still_owed > 0:
            return False

        now = datetime.now(timezone.utc)
        await self.db.customers.update_one({"_id": ObjectId(customer_id)}, {"$set": {"status": "active", "updated_at": now}})
        await self.db.subscriptions.update_many(
            {"customer_id": customer_id, "status": "suspended"},
            {"$set": {"status": "active", "updated_at": now}},
        )
        await self.notifications.notify(
            subject="Service restored",
            body=f"Hi {customer.get('full_name', '')}, your payment has been received and your internet service has been restored. Thank you!",
            customer_id=customer_id, phone=customer.get("phone"),
            notification_type=NotificationType.SERVICE_RESTORED,
        )
        return True

    async def run_restoration_sweep(self) -> dict:
        """Safety-net sweep for restorations that weren't triggered
        instantly (e.g. a manual/cash payment recorded outside the
        M-Pesa flow, which has no callback to hook into)."""
        suspended_ids = await self.db.customers.distinct("_id", {"status": "suspended"})
        restored = 0
        for oid in suspended_ids:
            if await self.try_restore_customer(str(oid)):
                restored += 1
        summary = {"checked": len(suspended_ids), "restored": restored}
        await self._log_run("restoration_sweep", summary)
        return summary

    # ------------------------------------------------------------------ #
    # 5. Payment reconciliation
    # ------------------------------------------------------------------ #
    async def run_payment_reconciliation(self, max_age_hours: int = 24) -> dict:
        mpesa_service = MpesaService(self.db)
        try:
            updated = await mpesa_service.reconcile_pending(max_age_hours=max_age_hours)
            summary = {"reconciled": len(updated)}
        except Exception as exc:  # noqa: BLE001
            summary = {"reconciled": 0, "error": str(exc)}
            logger.warning(f"Payment reconciliation failed: {exc}")
        await self._log_run("payment_reconciliation", summary)
        return summary

    # ------------------------------------------------------------------ #
    # Orchestration
    # ------------------------------------------------------------------ #
    async def run_full_cycle(self) -> dict:
        """Runs every stage in dependency order. Each stage is
        independently wrapped so one failing stage doesn't block the
        rest (e.g. a billing bug shouldn't stop suspension/reconciliation
        from running)."""
        results = {}
        for name, fn in [
            ("billing_cycle", self.run_billing_cycle),
            ("expiry_sweep", self.run_expiry_sweep),
            ("suspension_sweep", self.run_suspension_sweep),
            ("restoration_sweep", self.run_restoration_sweep),
            ("payment_reconciliation", self.run_payment_reconciliation),
        ]:
            try:
                results[name] = await fn()
            except Exception as exc:  # noqa: BLE001
                results[name] = {"error": str(exc)}
                logger.error(f"Automation stage '{name}' crashed: {exc}")
        return results

    async def get_recent_runs(self, job_name: Optional[str] = None, limit: int = 20) -> list:
        query = {"job_name": job_name} if job_name else {}
        cursor = self.db.automation_runs.find(query).sort("ran_at", -1).limit(limit)
        runs = []
        async for doc in cursor:
            doc["_id"] = str(doc["_id"])
            runs.append(doc)
        return runs
