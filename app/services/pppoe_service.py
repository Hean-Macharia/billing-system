"""PPPoE subscriber lifecycle using existing subscriptions and RADIUS users.

Provisioning creates a pending account only. It cannot grant network access;
the account becomes active after the existing verified payment settlement path
activates the associated subscription.
"""
from datetime import datetime, timezone
from typing import Any, Optional

from bson import ObjectId
from pymongo.errors import DuplicateKeyError

from app.core.crypto import encrypt_value
from app.core.exceptions import ConflictError, NotFoundError, ValidationError


def _ref(value: Any) -> dict:
    text = str(value or "").strip()
    if not text:
        raise ValidationError("A valid site, router, NAS, customer, and package assignment is required")
    try:
        oid = ObjectId(text)
    except Exception:
        return {"_id": text}
    return {"$or": [{"_id": oid}, {"_id": text}]}


class PppoeService:
    def __init__(self, db: Any):
        self.db = db

    async def _resolve_assignments(self, *, customer_id: str, plan_id: str,
                                   site_id: str, router_id: str,
                                   nas_client_id: str) -> tuple[dict, dict, dict, dict]:
        customer = await self.db.customers.find_one(_ref(customer_id))
        plan = await self.db.service_plans.find_one(_ref(plan_id))
        site = await self.db.sites.find_one(_ref(site_id))
        router = await self.db.routers.find_one(_ref(router_id))
        nas = await self.db.nas_clients.find_one(_ref(nas_client_id))
        if not customer:
            raise NotFoundError("Customer not found")
        if customer.get("status", "active") in {"suspended", "blocked", "inactive"}:
            raise ValidationError("Customer account is not active")
        if not plan or str(plan.get("status", "active")).lower() != "active":
            raise ValidationError("An active internet package is required")
        if str(plan.get("service_type", "")).lower() == "hotspot":
            raise ValidationError("A HotSpot package cannot be assigned to a PPPoE subscriber")
        if not site or str(site.get("status", "")).lower() != "active":
            raise ValidationError("The selected site does not exist or is not active")
        if not router or str(router.get("status", "unknown")).lower() == "disabled":
            raise ValidationError("The selected router does not exist or is disabled")
        if not nas or str(nas.get("status", "active")).lower() in {"inactive", "disabled"}:
            raise ValidationError("The selected RADIUS NAS does not exist or is inactive")
        if str(router.get("site_id") or "") != str(site_id) or str(nas.get("site_id") or "") != str(site_id):
            raise ValidationError("Router and NAS must belong to the selected site")
        if str(router.get("nas_client_id") or "") != str(nas_client_id):
            raise ValidationError("The selected NAS is not linked to the selected router")
        available_sites = plan.get("available_site_ids") or []
        if available_sites and str(site_id) not in {str(value) for value in available_sites}:
            raise ValidationError("The package is not available at the selected site")
        return customer, plan, site, router

    async def create_subscriber(self, data: Any) -> dict:
        customer, plan, site, router = await self._resolve_assignments(
            customer_id=data.customer_id, plan_id=data.plan_id,
            site_id=data.site_id, router_id=data.router_id,
            nas_client_id=data.nas_client_id,
        )
        username = data.username.strip()
        existing_sub = await self.db.subscriptions.find_one({"pppoe_username": username, "service_type": "pppoe"})
        existing_user = await self.db.radius_users.find_one({"username": username})
        if existing_sub:
            same_mapping = all(str(existing_sub.get(key) or "") == value for key, value in (
                ("customer_id", str(customer["_id"])), ("site_id", str(site["_id"])),
                ("router_id", str(router["_id"])), ("nas_client_id", str(data.nas_client_id)),
            ))
            if not same_mapping or str(existing_sub.get("plan_id") or existing_sub.get("service_id") or "") != str(plan["_id"]):
                raise ConflictError("PPPoE username is already assigned to another subscriber")
            if existing_user:
                if (
                    existing_user.get("status") != "pending"
                    or existing_user.get("subscription_id") not in (None, str(existing_sub["_id"]))
                    or str(existing_user.get("customer_id") or "") != str(customer["_id"])
                    or str(existing_user.get("site_id") or "") != str(site["_id"])
                    or str(existing_user.get("router_id") or "") != str(router["_id"])
                    or str(existing_user.get("nas_client_id") or "") != str(data.nas_client_id)
                ):
                    raise ConflictError("PPPoE username is already assigned to another subscriber")
                await self.db.radius_users.update_one(
                    {"_id": existing_user["_id"], "status": "pending", "subscription_id": {"$in": [None, str(existing_sub["_id"])]}},
                    {"$set": {"subscription_id": str(existing_sub["_id"]), "updated_at": datetime.now(timezone.utc)}},
                )
            else:
                # Recover the rare partial state where the subscription was
                # written but its RADIUS row was not. The supplied reset
                # credential is stored encrypted, and remains pending.
                record = {
                    "username": username, "password": encrypt_value(data.password),
                    "password_encrypted": True, "user_type": "pppoe",
                    "customer_id": str(customer["_id"]), "service_id": str(plan["_id"]),
                    "subscription_id": str(existing_sub["_id"]), "site_id": str(site["_id"]),
                    "router_id": str(router["_id"]), "nas_client_id": str(data.nas_client_id),
                    "package_id": str(plan["_id"]), "status": "pending",
                    "rate_limit": f"{int(plan['upload_speed_mbps'])}M/{int(plan['download_speed_mbps'])}M",
                    "data_cap_bytes": int(plan["data_cap_gb"] * 1024**3) if plan.get("data_cap_gb") else None,
                    "created_at": datetime.now(timezone.utc), "updated_at": datetime.now(timezone.utc),
                }
                try:
                    await self.db.radius_users.insert_one(record)
                except DuplicateKeyError as exc:
                    raise ConflictError("PPPoE account recovery conflicted with an existing username") from exc
            return self._public(existing_sub)
        if existing_user and (
            existing_user.get("status") != "pending"
            or existing_user.get("subscription_id")
            or str(existing_user.get("customer_id") or "") != str(customer["_id"])
            or str(existing_user.get("site_id") or "") != str(site["_id"])
            or str(existing_user.get("router_id") or "") != str(router["_id"])
            or str(existing_user.get("nas_client_id") or "") != str(data.nas_client_id)
        ):
            raise ConflictError("PPPoE username already exists")

        now = datetime.now(timezone.utc)
        password_record = {
            "username": username,
            "password": encrypt_value(data.password),
            "password_encrypted": True,
            "user_type": "pppoe",
            "customer_id": str(customer["_id"]),
            "service_id": str(plan["_id"]),
            "subscription_id": None,
            "site_id": str(site["_id"]),
            "router_id": str(router["_id"]),
            "nas_client_id": data.nas_client_id,
            "package_id": str(plan["_id"]),
            "framed_ip_address": data.ip_address,
            "framed_ip_pool": data.framed_ip_pool,
            "rate_limit": f"{int(plan['upload_speed_mbps'])}M/{int(plan['download_speed_mbps'])}M",
            "data_cap_bytes": int(plan["data_cap_gb"] * 1024**3) if plan.get("data_cap_gb") else None,
            "status": "pending",
            "created_at": now,
            "updated_at": now,
        }
        if existing_user:
            user_id = existing_user["_id"]
            await self.db.radius_users.update_one(
                    {"_id": existing_user["_id"], "status": "pending", "subscription_id": None},
                    {"$set": password_record},
                )
        else:
            try:
                user_id = (await self.db.radius_users.insert_one(password_record)).inserted_id
            except DuplicateKeyError as exc:
                raise ConflictError("PPPoE username already exists") from exc
        
        cycle = plan.get("billing_cycle", "monthly")
        sub_doc = {
            "customer_id": str(customer["_id"]),
            "customer_code": customer.get("customer_code"),
            "customer_name": customer.get("full_name"),
            "plan_id": str(plan["_id"]),
            "service_id": str(plan["_id"]),
            "plan_code": plan.get("plan_code"),
            "plan_name": plan.get("name"),
            "service_type": "pppoe",
            "billing_cycle": cycle,
            "status": "pending",
            "site_id": str(site["_id"]),
            "router_id": str(router["_id"]),
            "nas_client_id": str(data.nas_client_id),
            "pppoe_username": username,
            "pppoe_password": None,
            "start_date": now,
            "end_date": None,
            "next_billing_date": now,
            "monthly_price_kes": float(plan["base_price_kes"]),
            "setup_fee_kes": float(plan.get("setup_fee_kes", 0) or 0),
            "equipment_fee_kes": float(plan.get("equipment_fee_kes", 0) or 0),
            "data_cap_gb": plan.get("data_cap_gb"),
            "data_used_gb": 0,
            "created_at": now,
            "updated_at": now,
        }
        sub_result = await self.db.subscriptions.insert_one(sub_doc)
        sub_doc["_id"] = sub_result.inserted_id
        await self.db.radius_users.update_one(
            {"_id": user_id, "status": "pending"},
            {"$set": {"subscription_id": str(sub_result.inserted_id), "updated_at": now}},
        )
        return self._public(sub_doc)

    @staticmethod
    def _public(sub: dict) -> dict:
        return {
            "_id": str(sub.get("_id")),
            "customer_id": str(sub.get("customer_id")),
            "customer_name": sub.get("customer_name"),
            "plan_id": str(sub.get("plan_id")),
            "plan_name": sub.get("plan_name"),
            "site_id": str(sub.get("site_id")),
            "router_id": str(sub.get("router_id")),
            "nas_client_id": str(sub.get("nas_client_id")),
            "username": sub.get("pppoe_username"),
            "status": sub.get("status"),
            "start_date": sub.get("start_date"),
            "end_date": sub.get("end_date"),
            "ip_address": sub.get("ip_address"),
            "framed_ip_pool": sub.get("framed_ip_pool"),
        }

    async def list_subscribers(self, site_id: Optional[str] = None, status: Optional[str] = None,
                               page: int = 1, limit: int = 50) -> tuple[list[dict], int]:
        query: dict = {"service_type": "pppoe"}
        if site_id:
            query["site_id"] = site_id
        if status:
            query["status"] = status
        page, limit = max(1, page), min(max(1, limit), 100)
        total = await self.db.subscriptions.count_documents(query)
        rows = await self.db.subscriptions.find(query).sort("created_at", -1).skip((page - 1) * limit).limit(limit).to_list(length=limit)
        return [self._public(row) for row in rows], total

    async def get_subscriber(self, subscription_id: str) -> dict:
        try:
            row = await self.db.subscriptions.find_one({"_id": ObjectId(subscription_id), "service_type": "pppoe"})
        except Exception as exc:
            raise NotFoundError("PPPoE subscriber not found") from exc
        if not row:
            raise NotFoundError("PPPoE subscriber not found")
        return self._public(row)

    async def set_status(self, subscription_id: str, status: str, reason: Optional[str] = None) -> dict:
        if status != "suspended":
            raise ValidationError("Unsupported PPPoE status transition")
        try:
            subscription_oid = ObjectId(subscription_id)
        except Exception as exc:
            raise NotFoundError("PPPoE subscriber not found") from exc
        sub = await self.db.subscriptions.find_one({"_id": subscription_oid, "service_type": "pppoe"})
        if not sub:
            raise NotFoundError("PPPoE subscriber not found")
        await self.db.subscriptions.update_one(
            {"_id": sub["_id"], "service_type": "pppoe"},
            {"$set": {"status": status, "status_reason": reason, "updated_at": datetime.now(timezone.utc)}},
        )
        await self.db.radius_users.update_one(
            {"subscription_id": str(sub["_id"]), "user_type": "pppoe"},
            {"$set": {"status": status, "updated_at": datetime.now(timezone.utc)}},
        )
        return await self.get_subscriber(subscription_id)

    async def reset_password(self, subscription_id: str, password: str) -> None:
        try:
            subscription_oid = ObjectId(subscription_id)
        except Exception as exc:
            raise NotFoundError("PPPoE subscriber not found") from exc
        sub = await self.db.subscriptions.find_one({"_id": subscription_oid, "service_type": "pppoe"})
        if not sub:
            raise NotFoundError("PPPoE subscriber not found")
        result = await self.db.radius_users.update_one(
            {"subscription_id": str(sub["_id"]), "user_type": "pppoe"},
            {"$set": {"password": encrypt_value(password), "password_encrypted": True,
                      "updated_at": datetime.now(timezone.utc)}},
        )
        if result.matched_count != 1:
            raise NotFoundError("PPPoE RADIUS account not found")

    async def update_package(self, subscription_id: str, plan_id: str) -> dict:
        try:
            subscription_oid = ObjectId(subscription_id)
        except Exception as exc:
            raise NotFoundError("PPPoE subscriber not found") from exc
        sub = await self.db.subscriptions.find_one({"_id": subscription_oid, "service_type": "pppoe"})
        if not sub:
            raise NotFoundError("PPPoE subscriber not found")
        _, plan, _, _ = await self._resolve_assignments(
            customer_id=str(sub["customer_id"]), plan_id=plan_id,
            site_id=str(sub["site_id"]), router_id=str(sub["router_id"]),
            nas_client_id=str(sub["nas_client_id"]),
        )
        rate = f"{int(plan['upload_speed_mbps'])}M/{int(plan['download_speed_mbps'])}M"
        await self.db.subscriptions.update_one({"_id": sub["_id"]}, {"$set": {
            "plan_id": str(plan["_id"]), "service_id": str(plan["_id"]),
            "plan_name": plan.get("name"), "plan_code": plan.get("plan_code"),
            "monthly_price_kes": float(plan["base_price_kes"]), "updated_at": datetime.now(timezone.utc),
        }})
        await self.db.radius_users.update_one({"subscription_id": str(sub["_id"])}, {"$set": {
            "package_id": str(plan["_id"]), "service_id": str(plan["_id"]),
            "rate_limit": rate,
            "data_cap_bytes": int(plan["data_cap_gb"] * 1024**3) if plan.get("data_cap_gb") else None,
            "updated_at": datetime.now(timezone.utc),
        }})
        return await self.get_subscriber(subscription_id)
