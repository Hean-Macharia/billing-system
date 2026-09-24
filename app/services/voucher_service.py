"""Voucher management service.

Owns the full lifecycle described in app.models.voucher: batch generation,
admin activation, RADIUS-driven consumption (read-only from this side -
app.services.radius_auth_service does the actual marking of a voucher as
"used" during HotSpot authentication), expiry sweeping, and printable
output (CSV export + PDF voucher cards).
"""
import csv
import io
import secrets
import string
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo.errors import BulkWriteError

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.core.logging import get_logger
from app.models.voucher import Voucher, VoucherBatch, VoucherStatus
from app.schemas.voucher import VoucherBatchCreate

logger = get_logger(__name__)

# Excludes ambiguous characters (0/O, 1/I/L) so printed/handwritten codes
# are easy to read and type into a HotSpot login page.
_CODE_ALPHABET = "".join(c for c in (string.ascii_uppercase + string.digits) if c not in "0O1IL")


def _generate_code(length: int, prefix: str = "") -> str:
    body = "".join(secrets.choice(_CODE_ALPHABET) for _ in range(length))
    return f"{prefix}{body}" if prefix else body


class VoucherService:
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.batches = db.voucher_batches
        self.vouchers = db.vouchers
        self.plans = db.hotspot_plans

    # ------------------------------------------------------------------ #
    # Batch generation
    # ------------------------------------------------------------------ #
    async def create_batch(self, data: VoucherBatchCreate, created_by: Optional[str] = None) -> VoucherBatch:
        duration_hours = data.duration_hours
        data_allowance_mb = data.data_allowance_mb
        rate_limit = data.rate_limit
        price = data.price
        currency = data.currency

        if data.plan_id:
            plan = await self.plans.find_one({"_id": self._oid(data.plan_id, "Plan")})
            if not plan:
                raise NotFoundError("HotSpot plan not found")
            duration_hours = duration_hours or plan.get("duration_hours")
            data_allowance_mb = data_allowance_mb or plan.get("data_allowance_mb")
            rate_limit = rate_limit or plan.get("rate_limit")
            price = price or plan.get("price", 0.0)
            currency = currency or plan.get("currency", "KES")

        if not duration_hours:
            raise ValidationError("duration_hours is required (directly or via plan_id)")

        now = datetime.now(timezone.utc)
        batch_doc = {
            "batch_name": data.batch_name,
            "site_id": data.site_id,
            "router_id": data.router_id,
            "quantity": data.quantity,
            "code_prefix": data.code_prefix,
            "code_length": data.code_length,
            "duration_hours": duration_hours,
            "data_allowance_mb": data_allowance_mb,
            "rate_limit": rate_limit,
            "price": price,
            "currency": currency,
            "activate_on_generation": data.activate_on_generation,
            "validity_days_after_generation": data.validity_days_after_generation,
            "generated_count": 0,
            "activated_count": 0,
            "used_count": 0,
            "created_by": created_by,
            "created_at": now,
            "updated_at": now,
        }
        batch_result = await self.batches.insert_one(batch_doc)
        batch_id = str(batch_result.inserted_id)

        vouchers = self._build_voucher_docs(data, batch_id, now)
        inserted = await self._insert_with_retry(vouchers, data.code_length, data.code_prefix)

        activated_count = sum(1 for v in inserted if v["status"] == VoucherStatus.ACTIVE.value)
        await self.batches.update_one(
            {"_id": batch_result.inserted_id},
            {"$set": {"generated_count": len(inserted), "activated_count": activated_count, "updated_at": datetime.now(timezone.utc)}},
        )

        logger.info(f"Voucher batch '{data.batch_name}' generated: {len(inserted)} codes (activate_on_generation={data.activate_on_generation})")
        batch_doc["_id"] = batch_id
        batch_doc["generated_count"] = len(inserted)
        batch_doc["activated_count"] = activated_count
        return VoucherBatch(**batch_doc)

    def _build_voucher_docs(self, data: VoucherBatchCreate, batch_id: str, now: datetime) -> List[dict]:
        activate_now = data.activate_on_generation
        expiry_date = None
        if activate_now:
            expiry_date = now + timedelta(hours=data.duration_hours) if data.duration_hours else None
        elif data.validity_days_after_generation:
            # Hard cutoff even if never activated/sold - common for "must be redeemed within 30 days".
            expiry_date = now + timedelta(days=data.validity_days_after_generation)

        docs = []
        for _ in range(data.quantity):
            docs.append(
                {
                    "batch_id": batch_id,
                    "voucher_code": _generate_code(data.code_length, data.code_prefix),
                    "status": (VoucherStatus.ACTIVE if activate_now else VoucherStatus.GENERATED).value,
                    "site_id": data.site_id,
                    "router_id": data.router_id,
                    "duration_hours": data.duration_hours,
                    "data_allowance_mb": data.data_allowance_mb,
                    "rate_limit": data.rate_limit,
                    "price": data.price,
                    "currency": data.currency,
                    "expiry_date": expiry_date,
                    "activated_at": now if activate_now else None,
                    "activated_by": None,
                    "used_at": None,
                    "nas_ip": None,
                    "calling_station_id": None,
                    "printed": False,
                    "printed_at": None,
                    "created_at": now,
                    "updated_at": now,
                }
            )
        return docs

    async def _insert_with_retry(self, docs: List[dict], code_length: int, code_prefix: str, max_attempts: int = 5) -> List[dict]:
        """Insert vouchers, regenerating codes on the rare unique-index collision."""
        remaining = docs
        inserted: List[dict] = []
        for attempt in range(max_attempts):
            if not remaining:
                break
            try:
                result = await self.vouchers.insert_many(remaining, ordered=False)
                for doc, _id in zip(remaining, result.inserted_ids):
                    doc["_id"] = str(_id)
                inserted.extend(remaining)
                remaining = []
            except BulkWriteError as exc:
                write_errors = exc.details.get("writeErrors", [])
                failed_indexes = {e["index"] for e in write_errors if e.get("code") == 11000}
                succeeded = [d for i, d in enumerate(remaining) if i not in failed_indexes]
                # inserted_ids on partial failure aren't reliably ordered across drivers,
                # so re-fetch the succeeded ones by code to get their real _id.
                if succeeded:
                    codes = [d["voucher_code"] for d in succeeded]
                    cursor = self.vouchers.find({"voucher_code": {"$in": codes}})
                    by_code = {doc["voucher_code"]: doc async for doc in cursor}
                    for d in succeeded:
                        saved = by_code.get(d["voucher_code"])
                        if saved:
                            d["_id"] = str(saved["_id"])
                            inserted.append(d)
                failed = [remaining[i] for i in failed_indexes]
                for d in failed:
                    d["voucher_code"] = _generate_code(code_length, code_prefix)
                remaining = failed
                logger.warning(f"Voucher code collision, regenerating {len(failed)} code(s) (attempt {attempt + 1})")
        if remaining:
            raise ConflictError(f"Failed to generate {len(remaining)} unique voucher code(s) after {max_attempts} attempts")
        return inserted

    # ------------------------------------------------------------------ #
    # Listing / retrieval
    # ------------------------------------------------------------------ #
    def _oid(self, id_str: str, label: str = "Resource") -> ObjectId:
        try:
            return ObjectId(id_str)
        except Exception as exc:
            raise NotFoundError(f"{label} not found") from exc

    async def get_batch(self, batch_id: str) -> VoucherBatch:
        doc = await self.batches.find_one({"_id": self._oid(batch_id, "Voucher batch")})
        if not doc:
            raise NotFoundError("Voucher batch not found")
        doc["_id"] = str(doc["_id"])
        return VoucherBatch(**doc)

    async def list_batches(self, site_id: Optional[str] = None, page: int = 1, limit: int = 20):
        query = {}
        if site_id:
            query["site_id"] = site_id
        skip = (page - 1) * limit
        total = await self.batches.count_documents(query)
        cursor = self.batches.find(query).skip(skip).limit(limit).sort("created_at", -1)
        batches = []
        async for doc in cursor:
            doc["_id"] = str(doc["_id"])
            batches.append(VoucherBatch(**doc))
        return batches, total

    async def get_voucher(self, voucher_id: str) -> Voucher:
        doc = await self.vouchers.find_one({"_id": self._oid(voucher_id, "Voucher")})
        if not doc:
            raise NotFoundError("Voucher not found")
        doc["_id"] = str(doc["_id"])
        return Voucher(**doc)

    async def list_vouchers(
        self,
        batch_id: Optional[str] = None,
        status: Optional[str] = None,
        site_id: Optional[str] = None,
        page: int = 1,
        limit: int = 50,
    ):
        query = {}
        if batch_id:
            query["batch_id"] = batch_id
        if status:
            query["status"] = status
        if site_id:
            query["site_id"] = site_id
        skip = (page - 1) * limit
        total = await self.vouchers.count_documents(query)
        cursor = self.vouchers.find(query).skip(skip).limit(limit).sort("created_at", -1)
        vouchers = []
        async for doc in cursor:
            doc["_id"] = str(doc["_id"])
            vouchers.append(Voucher(**doc))
        return vouchers, total

    # ------------------------------------------------------------------ #
    # Activation
    # ------------------------------------------------------------------ #
    async def activate_voucher(self, voucher_id: str, activated_by: Optional[str] = None) -> Voucher:
        doc = await self.vouchers.find_one({"_id": self._oid(voucher_id, "Voucher")})
        if not doc:
            raise NotFoundError("Voucher not found")
        if doc["status"] != VoucherStatus.GENERATED.value:
            raise ConflictError(f"Voucher is '{doc['status']}', can only activate a 'generated' voucher")

        now = datetime.now(timezone.utc)
        expiry_date = now + timedelta(hours=doc["duration_hours"]) if doc.get("duration_hours") else None

        await self.vouchers.update_one(
            {"_id": doc["_id"]},
            {
                "$set": {
                    "status": VoucherStatus.ACTIVE.value,
                    "activated_at": now,
                    "activated_by": activated_by,
                    "expiry_date": expiry_date,
                    "updated_at": now,
                }
            },
        )
        if doc.get("batch_id"):
            await self.batches.update_one({"_id": self._oid(doc["batch_id"])}, {"$inc": {"activated_count": 1}})
        return await self.get_voucher(voucher_id)

    async def activate_batch(self, batch_id: str, voucher_ids: Optional[List[str]] = None, activated_by: Optional[str] = None) -> dict:
        query = {"batch_id": batch_id, "status": VoucherStatus.GENERATED.value}
        if voucher_ids:
            query["_id"] = {"$in": [self._oid(v, "Voucher") for v in voucher_ids]}

        now = datetime.now(timezone.utc)
        activated = 0
        skipped = 0
        cursor = self.vouchers.find(query)
        async for doc in cursor:
            expiry_date = now + timedelta(hours=doc["duration_hours"]) if doc.get("duration_hours") else None
            result = await self.vouchers.update_one(
                {"_id": doc["_id"], "status": VoucherStatus.GENERATED.value},
                {
                    "$set": {
                        "status": VoucherStatus.ACTIVE.value,
                        "activated_at": now,
                        "activated_by": activated_by,
                        "expiry_date": expiry_date,
                        "updated_at": now,
                    }
                },
            )
            if result.modified_count:
                activated += 1
            else:
                skipped += 1

        if activated:
            await self.batches.update_one({"_id": self._oid(batch_id, "Voucher batch")}, {"$inc": {"activated_count": activated}})
        return {"batch_id": batch_id, "activated": activated, "skipped": skipped}

    async def disable_voucher(self, voucher_id: str, reason: Optional[str] = None) -> Voucher:
        doc = await self.vouchers.find_one({"_id": self._oid(voucher_id, "Voucher")})
        if not doc:
            raise NotFoundError("Voucher not found")
        if doc["status"] == VoucherStatus.USED.value:
            raise ConflictError("Cannot disable a voucher that has already been used")

        await self.vouchers.update_one(
            {"_id": doc["_id"]},
            {"$set": {"status": VoucherStatus.DISABLED.value, "updated_at": datetime.now(timezone.utc), "disable_reason": reason}},
        )
        return await self.get_voucher(voucher_id)

    # ------------------------------------------------------------------ #
    # Expiry
    # ------------------------------------------------------------------ #
    async def expire_sweep(self) -> dict:
        """Sweep ACTIVE and GENERATED vouchers whose expiry_date has passed.

        GENERATED vouchers only expire here if validity_days_after_generation
        was set on their batch (a hard "must redeem by" cutoff) - otherwise
        an un-activated voucher has no expiry_date and is left alone.
        """
        now = datetime.now(timezone.utc)
        result = await self.vouchers.update_many(
            {
                "status": {"$in": [VoucherStatus.ACTIVE.value, VoucherStatus.GENERATED.value]},
                "expiry_date": {"$ne": None, "$lt": now},
            },
            {"$set": {"status": VoucherStatus.EXPIRED.value, "updated_at": now}},
        )
        logger.info(f"Voucher expiry sweep: {result.modified_count} voucher(s) expired")
        return {"expired": result.modified_count, "swept_at": now.isoformat()}

    # ------------------------------------------------------------------ #
    # Public HotSpot check (read-only, no auth - used by a captive portal)
    # ------------------------------------------------------------------ #
    async def check_code(self, code: str) -> dict:
        doc = await self.vouchers.find_one({"voucher_code": code})
        if not doc:
            return {"voucher_code": code, "valid": False, "status": "not_found", "reason": "Voucher code not recognized"}

        now = datetime.now(timezone.utc)
        status = doc["status"]

        if status == VoucherStatus.GENERATED.value:
            return {"voucher_code": code, "valid": False, "status": status, "reason": "Voucher has not been activated yet"}
        if status == VoucherStatus.USED.value:
            return {"voucher_code": code, "valid": False, "status": status, "reason": "Voucher has already been used"}
        if status == VoucherStatus.DISABLED.value:
            return {"voucher_code": code, "valid": False, "status": status, "reason": "Voucher has been disabled"}
        if status == VoucherStatus.EXPIRED.value:
            return {"voucher_code": code, "valid": False, "status": status, "reason": "Voucher has expired"}

        # ACTIVE - but double-check expiry lazily in case the sweep hasn't run yet
        expiry = doc.get("expiry_date")
        if expiry and expiry < now:
            await self.vouchers.update_one({"_id": doc["_id"]}, {"$set": {"status": VoucherStatus.EXPIRED.value, "updated_at": now}})
            return {"voucher_code": code, "valid": False, "status": "expired", "reason": "Voucher has expired"}

        return {
            "voucher_code": code,
            "valid": True,
            "status": status,
            "duration_hours": doc.get("duration_hours"),
            "data_allowance_mb": doc.get("data_allowance_mb"),
            "expiry_date": expiry,
        }

    # ------------------------------------------------------------------ #
    # Printing
    # ------------------------------------------------------------------ #
    async def export_batch_csv(self, batch_id: str) -> str:
        """Returns CSV text (code, duration, data, price, status, expiry) for a batch."""
        vouchers, _ = await self.list_vouchers(batch_id=batch_id, limit=100000)
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["voucher_code", "status", "duration_hours", "data_allowance_mb", "price", "currency", "expiry_date"])
        for v in vouchers:
            writer.writerow(
                [
                    v.voucher_code,
                    v.status.value,
                    v.duration_hours or "",
                    v.data_allowance_mb or "",
                    v.price,
                    v.currency,
                    v.expiry_date.isoformat() if v.expiry_date else "",
                ]
            )
        await self.vouchers.update_many({"batch_id": batch_id}, {"$set": {"printed": True, "printed_at": datetime.now(timezone.utc)}})
        return buf.getvalue()

    async def generate_batch_pdf(self, batch_id: str, org_name: str = "ISP Billing") -> bytes:
        """Renders printable voucher cards (3 columns x 8 rows per A4 page) as PDF bytes."""
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import mm
        from reportlab.pdfgen import canvas

        batch = await self.get_batch(batch_id)
        vouchers, _ = await self.list_vouchers(batch_id=batch_id, limit=100000)
        if not vouchers:
            raise ValidationError("Batch has no vouchers to print")

        buf = io.BytesIO()
        page_w, page_h = A4
        cols, rows = 3, 8
        margin = 10 * mm
        card_w = (page_w - 2 * margin) / cols
        card_h = (page_h - 2 * margin) / rows

        c = canvas.Canvas(buf, pagesize=A4)

        for idx, v in enumerate(vouchers):
            pos_in_page = idx % (cols * rows)
            if idx > 0 and pos_in_page == 0:
                c.showPage()
            col = pos_in_page % cols
            row = pos_in_page // cols

            x = margin + col * card_w
            y = page_h - margin - (row + 1) * card_h

            c.roundRect(x + 2, y + 2, card_w - 4, card_h - 4, 4, stroke=1, fill=0)

            c.setFont("Helvetica-Bold", 9)
            c.drawCentredString(x + card_w / 2, y + card_h - 14, org_name)

            c.setFont("Helvetica-Bold", 14)
            c.drawCentredString(x + card_w / 2, y + card_h / 2 + 2, v.voucher_code)

            c.setFont("Helvetica", 7)
            duration_label = f"{v.duration_hours:g}h" if v.duration_hours else "N/A"
            data_label = f"{v.data_allowance_mb}MB" if v.data_allowance_mb else "Unlimited"
            c.drawCentredString(x + card_w / 2, y + card_h / 2 - 12, f"{duration_label} | {data_label}")

            price_label = f"{v.currency} {v.price:g}" if v.price else "Free"
            c.setFont("Helvetica", 7)
            c.drawCentredString(x + card_w / 2, y + 10, price_label)

        c.save()
        buf.seek(0)

        await self.vouchers.update_many({"batch_id": batch_id}, {"$set": {"printed": True, "printed_at": datetime.now(timezone.utc)}})
        logger.info(f"Generated printable PDF for batch {batch_id} ({len(vouchers)} vouchers)")
        return buf.read()
