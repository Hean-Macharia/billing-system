"""Customer portal service.

Portal "login" deliberately reuses the existing AuthService/JWT flow as-is
(POST /api/v1/auth/login) - a customer IS a User row with role=customer,
so nothing new was needed there. This service only covers what's actually
portal-specific: self-service account activation (linking a Customer to a
new User), and read-side aggregation (dashboard summary, usage) that pulls
from several collections a customer should never query directly.
"""
from datetime import datetime, timedelta, timezone
from typing import Optional

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.exceptions import AuthenticationError, ConflictError, NotFoundError
from app.core.security import hash_password
from app.models.user import UserInDB, UserRole, UserStatus, get_permissions_for_role
from app.schemas.portal import PortalRegisterRequest


class PortalService:
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db

    # ------------------------------------------------------------------ #
    # Self-service activation
    # ------------------------------------------------------------------ #
    async def register(self, data: PortalRegisterRequest) -> UserInDB:
        customer = await self.db.customers.find_one({"customer_code": data.customer_code})
        if not customer:
            raise AuthenticationError("We couldn't verify those details. Check your customer code and phone number.")

        # Normalize phone comparison loosely (strip spaces/leading +) since
        # staff may have entered it in slightly different formats.
        on_file = (customer.get("phone") or "").replace(" ", "").replace("+", "")
        supplied = data.phone.replace(" ", "").replace("+", "")
        if on_file != supplied:
            raise AuthenticationError("We couldn't verify those details. Check your customer code and phone number.")

        if customer.get("user_id"):
            raise ConflictError("This account already has portal access. Try logging in, or use 'forgot password'.")

        existing_user = await self.db.users.find_one({"email": data.email})
        if existing_user:
            raise ConflictError("That email is already registered to an account.")

        now = datetime.now(timezone.utc)
        permissions = get_permissions_for_role(UserRole.CUSTOMER)
        user_doc = {
            "email": data.email,
            "username": data.customer_code,
            "full_name": customer.get("full_name", data.customer_code),
            "hashed_password": hash_password(data.password),
            "role": UserRole.CUSTOMER.value,
            "status": UserStatus.ACTIVE.value,
            "phone": customer.get("phone"),
            "permissions": permissions,
            "is_email_verified": False,
            "failed_login_attempts": 0,
            "created_at": now,
            "updated_at": now,
            "created_by": None,
            "refresh_tokens": [],
        }
        result = await self.db.users.insert_one(user_doc)
        user_doc["_id"] = str(result.inserted_id)

        update = {"user_id": user_doc["_id"], "updated_at": now}
        if not customer.get("email"):
            update["email"] = data.email
        await self.db.customers.update_one({"_id": customer["_id"]}, {"$set": update})

        return UserInDB(**user_doc)

    # ------------------------------------------------------------------ #
    # Identity resolution
    # ------------------------------------------------------------------ #
    async def get_customer_for_user(self, user_id: str) -> dict:
        customer = await self.db.customers.find_one({"user_id": user_id})
        if not customer:
            raise NotFoundError("No customer account is linked to this login.")
        customer["_id"] = str(customer["_id"])
        return customer

    # ------------------------------------------------------------------ #
    # Dashboard
    # ------------------------------------------------------------------ #
    async def get_dashboard(self, customer: dict) -> dict:
        customer_id = customer["_id"]

        subscription = await self.db.subscriptions.find_one({"customer_id": customer_id, "status": "active"})
        plan = None
        if subscription and subscription.get("plan_id"):
            plan = await self.db.service_plans.find_one({"_id": ObjectId(subscription["plan_id"])})

        unpaid_cursor = self.db.invoices.find({"customer_id": customer_id, "status": {"$in": ["unpaid", "partially_paid", "overdue"]}})
        balance_due = 0.0
        overdue_count = 0
        async for inv in unpaid_cursor:
            balance_due += inv.get("balance_due_kes", 0)
            if inv.get("status") == "overdue":
                overdue_count += 1

        last_payment = await self.db.payments.find_one({"customer_id": customer_id, "status": "completed"}, sort=[("created_at", -1)])

        usage = await self.get_usage(customer, days=30)

        return {
            "customer": {
                "full_name": customer.get("full_name"), "customer_code": customer.get("customer_code"),
                "status": customer.get("status"), "phone": customer.get("phone"), "email": customer.get("email"),
            },
            "subscription": {
                "status": subscription.get("status") if subscription else None,
                "plan_name": plan.get("name") if plan else None,
                "monthly_price_kes": subscription.get("monthly_price_kes") if subscription else None,
                "next_billing_date": subscription.get("next_billing_date") if subscription else None,
            } if subscription else None,
            "balance_due_kes": balance_due,
            "overdue_invoice_count": overdue_count,
            "last_payment": {
                "amount_kes": last_payment.get("amount_kes"), "date": last_payment.get("created_at"),
                "method": last_payment.get("payment_method"),
            } if last_payment else None,
            "usage_last_30_days": usage["totals"],
            "currently_online": usage["currently_online"],
        }

    # ------------------------------------------------------------------ #
    # Usage
    # ------------------------------------------------------------------ #
    async def get_usage(self, customer: dict, days: int = 30) -> dict:
        customer_id = customer["_id"]
        since = datetime.now(timezone.utc) - timedelta(days=days)

        usernames = [
            doc["username"]
            async for doc in self.db.radius_users.find({"customer_id": customer_id}, {"username": 1})
        ]

        daily: dict[str, dict] = {}
        total_in = 0
        total_out = 0
        if usernames:
            cursor = self.db.radius_accounting.find({"username": {"$in": usernames}, "acct_start_time": {"$gte": since}})
            async for rec in cursor:
                day = (rec.get("acct_start_time") or since).strftime("%Y-%m-%d")
                bucket = daily.setdefault(day, {"date": day, "input_bytes": 0, "output_bytes": 0})
                bucket["input_bytes"] += rec.get("acct_input_octets", 0)
                bucket["output_bytes"] += rec.get("acct_output_octets", 0)
                total_in += rec.get("acct_input_octets", 0)
                total_out += rec.get("acct_output_octets", 0)

        currently_online = False
        if usernames:
            online_doc = await self.db.radius_sessions.find_one({"customer_id": customer_id, "status": "online"})
            currently_online = online_doc is not None

        return {
            "daily": sorted(daily.values(), key=lambda d: d["date"]),
            "totals": {
                "input_mb": round(total_in / (1024 * 1024), 2),
                "output_mb": round(total_out / (1024 * 1024), 2),
                "total_mb": round((total_in + total_out) / (1024 * 1024), 2),
            },
            "currently_online": currently_online,
        }
