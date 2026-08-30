"""RADIUS Authentication, Authorization, and Accounting service.

This is the core AAA engine. FreeRADIUS rlm_rest calls these endpoints:
  - POST /api/v1/radius/auth      (authenticate/authorize)
  - POST /api/v1/radius/accounting (accounting start/stop/interim)

Auth flow:
  MikroTik → FreeRADIUS → rlm_rest → FastAPI → MongoDB → response
"""
from datetime import datetime, timezone
from typing import Optional

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.config import settings
from app.core.exceptions import NotFoundError, ValidationError
from app.core.logging import get_logger
from app.models.radius import RadiusAccounting, RadiusUser, RadiusUserType
from app.schemas.radius_auth import RadiusAccountingRequest, RadiusAuthRequest, RadiusAuthResponse

logger = get_logger(__name__)


class RadiusAuthService:
    """Handles RADIUS auth and accounting from FreeRADIUS."""

    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.user_collection = db.radius_users
        self.acct_collection = db.radius_accounting
        self.session_collection = db.radius_sessions
        self.nas_collection = db.nas_clients
        self.voucher_collection = db.vouchers
        self.customer_collection = db.customers
        self.subscription_collection = db.subscriptions

    # ── AUTHENTICATION & AUTHORIZATION ──

    async def authenticate(self, req: RadiusAuthRequest) -> RadiusAuthResponse:
        """Process Access-Request from FreeRADIUS.

        Returns Accept with attributes OR Reject with reason.
        """
        username = req.User_Name
        password = req.User_Password
        nas_ip = req.NAS_IP_Address
        calling_station = req.Calling_Station_Id

        if not username:
            logger.warning("RADIUS auth: missing username")
            return RadiusAuthResponse(control_Auth_Type="Reject", reply_Reply_Message="Missing username")

        logger.info(f"RADIUS auth request: user={username}, nas={nas_ip}, mac={calling_station}")

        # 1. Find user by username
        user_doc = await self.user_collection.find_one({"username": username})

        # 2. If not found, check for voucher (HotSpot voucher codes)
        if not user_doc:
            voucher = await self._check_voucher(username)
            if voucher:
                return await self._authorize_voucher(voucher, nas_ip, calling_station)
            logger.warning(f"RADIUS auth: user not found: {username}")
            return RadiusAuthResponse(control_Auth_Type="Reject", reply_Reply_Message="Invalid credentials")

        user = RadiusUser(**{**user_doc, "_id": str(user_doc["_id"])})

        # 3. Verify password (cleartext comparison for RADIUS)
        # In production, you may want to hash passwords. For RADIUS PAP, cleartext is common.
        if password and user.password != password:
            logger.warning(f"RADIUS auth: wrong password for {username}")
            return RadiusAuthResponse(control_Auth_Type="Reject", reply_Reply_Message="Invalid credentials")

        # 4. Check user status
        if user.status == "suspended":
            return RadiusAuthResponse(control_Auth_Type="Reject", reply_Reply_Message="Account suspended")
        if user.status == "expired":
            return RadiusAuthResponse(control_Auth_Type="Reject", reply_Reply_Message="Account expired")
        if user.status != "active":
            return RadiusAuthResponse(control_Auth_Type="Reject", reply_Reply_Message="Account inactive")

        # 5. Check customer status
        if user.customer_id:
            customer = await self.customer_collection.find_one({"_id": ObjectId(user.customer_id)})
            if customer and customer.get("status") in ("suspended", "blocked"):
                return RadiusAuthResponse(control_Auth_Type="Reject", reply_Reply_message="Customer suspended")

        # 6. Check subscription status
        if user.subscription_id:
            sub = await self.subscription_collection.find_one({"_id": ObjectId(user.subscription_id)})
            if sub:
                sub_status = sub.get("status")
                if sub_status in ("suspended", "expired", "cancelled", "terminated"):
                    return RadiusAuthResponse(
                        control_Auth_Type="Reject",
                        reply_Reply_Message=f"Subscription {sub_status}",
                    )
                # Check data cap
                if user.data_cap_bytes and sub.get("data_used_bytes", 0) >= user.data_cap_bytes:
                    return RadiusAuthResponse(
                        control_Auth_Type="Reject",
                        reply_Reply_message="Data limit exceeded",
                    )

        # 7. Update last login info
        await self.user_collection.update_one(
            {"_id": ObjectId(user.id)},
            {
                "$set": {
                    "last_login": datetime.now(timezone.utc),
                    "last_nas_ip": nas_ip,
                    "updated_at": datetime.now(timezone.utc),
                }
            },
        )

        # 8. Build authorization attributes
        reply = RadiusAuthResponse(control_Auth_Type="Accept")

        if user.rate_limit:
            reply.reply_Mikrotik_Rate_Limit = user.rate_limit
        if user.session_timeout:
            reply.reply_Session_Timeout = user.session_timeout
        if user.idle_timeout:
            reply.reply_Idle_Timeout = user.idle_timeout
        if user.framed_ip_address:
            reply.reply_Framed_IP_Address = user.framed_ip_address
        if user.framed_ip_pool:
            reply.reply_Framed_Pool = user.framed_ip_pool
        if user.simultaneous_use:
            reply.reply_Simultaneous_Use = user.simultaneous_use

        # Set accounting interim interval (5 minutes)
        reply.reply_Acct_Interim_Interval = 300

        # For HotSpot users, add session timeout from voucher if applicable
        if user.user_type == RadiusUserType.HOTSPOT_VOUCHER and user.session_timeout:
            reply.reply_Session_Timeout = user.session_timeout

        # Add class attribute for accounting linkage
        reply.reply_Class = f"uid:{user.id}"

        logger.info(f"RADIUS auth ACCEPT: {username} -> rate={user.rate_limit}, pool={user.framed_ip_pool}")
        return reply

    async def _check_voucher(self, code: str) -> Optional[dict]:
        """Check if username is actually a voucher code."""
        voucher = await self.voucher_collection.find_one({
            "voucher_code": code,
            "status": "active",
        })
        if not voucher:
            return None

        # Check expiry
        expiry = voucher.get("expiry_date")
        if expiry and expiry < datetime.now(timezone.utc):
            await self.voucher_collection.update_one(
                {"_id": voucher["_id"]},
                {"$set": {"status": "expired", "updated_at": datetime.now(timezone.utc)}},
            )
            return None

        return voucher

    async def _authorize_voucher(self, voucher: dict, nas_ip: str, calling_station: str) -> RadiusAuthResponse:
        """Authorize a HotSpot voucher."""
        # Mark as used
        await self.voucher_collection.update_one(
            {"_id": voucher["_id"]},
            {
                "$set": {
                    "status": "used",
                    "used_at": datetime.now(timezone.utc),
                    "nas_ip": nas_ip,
                    "calling_station_id": calling_station,
                    "updated_at": datetime.now(timezone.utc),
                }
            },
        )

        reply = RadiusAuthResponse(control_Auth_Type="Accept")

        # Duration limit
        duration = voucher.get("duration_hours")
        if duration:
            reply.reply_Session_Timeout = duration * 3600

        # Data limit
        data_mb = voucher.get("data_allowance_mb")
        if data_mb:
            reply.reply_Mikrotik_Recv_Limit = data_mb * 1024 * 1024
            reply.reply_Mikrotik_Xmit_Limit = data_mb * 1024 * 1024

        reply.reply_Acct_Interim_Interval = 300
        reply.reply_Class = f"voucher:{str(voucher['_id'])}"

        logger.info(f"RADIUS voucher ACCEPT: {voucher['voucher_code']} duration={duration}h data={data_mb}MB")
        return reply

    # ── ACCOUNTING ──

    async def accounting(self, req: RadiusAccountingRequest) -> None:
        """Process Accounting-Request from FreeRADIUS.

        Handles Start, Stop, and Interim-Update.
        """
        acct_type = req.Acct_Status_Type
        username = req.User_Name
        session_id = req.Acct_Session_Id
        nas_ip = req.NAS_IP_Address

        if not session_id:
            logger.warning("RADIUS accounting: missing Acct-Session-Id")
            return

        logger.debug(f"RADIUS accounting: {acct_type} | user={username} | session={session_id}")

        if acct_type == "Start":
            await self._accounting_start(req)
        elif acct_type == "Stop":
            await self._accounting_stop(req)
        elif acct_type == "Interim-Update":
            await self._accounting_interim(req)
        elif acct_type == "Accounting-On":
            logger.info(f"NAS {nas_ip} sent Accounting-On")
        elif acct_type == "Accounting-Off":
            logger.info(f"NAS {nas_ip} sent Accounting-Off")
        else:
            logger.warning(f"Unknown accounting type: {acct_type}")

    async def _accounting_start(self, req: RadiusAccountingRequest) -> None:
        """Handle Accounting-Start."""
        now = datetime.now(timezone.utc)

        # Extract customer info from Class attribute if present
        customer_id = None
        subscription_id = None
        voucher_id = None
        if req.Class:
            if req.Class.startswith("uid:"):
                user_id = req.Class[4:]
                user = await self.user_collection.find_one({"_id": ObjectId(user_id)})
                if user:
                    customer_id = user.get("customer_id")
                    subscription_id = user.get("subscription_id")
            elif req.Class.startswith("voucher:"):
                voucher_id = req.Class[8:]

        doc = {
            "acct_session_id": req.Acct_Session_Id,
            "acct_unique_id": req.Acct_Session_Id,  # Will be updated if available
            "username": req.User_Name or "unknown",
            "nas_ip_address": req.NAS_IP_Address or "",
            "nas_port_id": req.NAS_Port,
            "nas_port_type": req.NAS_Port_Type,
            "acct_start_time": now,
            "acct_session_time": 0,
            "acct_input_octets": 0,
            "acct_output_octets": 0,
            "acct_input_gigawords": 0,
            "acct_output_gigawords": 0,
            "calling_station_id": req.Calling_Station_Id,
            "called_station_id": req.Called_Station_Id,
            "acct_terminate_cause": "N/A",
            "service_type": req.Service_Type,
            "framed_protocol": req.Framed_Protocol,
            "framed_ip_address": req.Framed_IP_Address,
            "class_attr": req.Class,
            "customer_id": customer_id,
            "subscription_id": subscription_id,
            "voucher_id": voucher_id,
            "created_at": now,
            "updated_at": now,
        }

        await self.acct_collection.insert_one(doc)

        # Upsert live session
        await self.session_collection.update_one(
            {"acct_session_id": req.Acct_Session_Id},
            {
                "$set": {
                    "acct_session_id": req.Acct_Session_Id,
                    "username": req.User_Name or "unknown",
                    "nas_ip_address": req.NAS_IP_Address or "",
                    "nas_port_id": req.NAS_Port,
                    "framed_ip_address": req.Framed_IP_Address,
                    "calling_station_id": req.Calling_Station_Id,
                    "customer_id": customer_id,
                    "subscription_id": subscription_id,
                    "site_id": None,  # Can be resolved from NAS
                    "acct_start_time": now,
                    "acct_session_time": 0,
                    "acct_input_octets": 0,
                    "acct_output_octets": 0,
                    "status": "online",
                    "last_seen": now,
                }
            },
            upsert=True,
        )

        # Update user session count
        if req.User_Name:
            await self.user_collection.update_one(
                {"username": req.User_Name},
                {"$inc": {"total_sessions": 1}},
            )

        logger.info(f"RADIUS acct START: {req.User_Name} | session={req.Acct_Session_Id} | ip={req.Framed_IP_Address}")

    async def _accounting_stop(self, req: RadiusAccountingRequest) -> None:
        """Handle Accounting-Stop."""
        now = datetime.now(timezone.utc)
        session_time = req.Acct_Session_Time or 0
        input_octets = req.Acct_Input_Octets or 0
        output_octets = req.Acct_Output_Octets or 0

        # Calculate total bytes including gigawords
        total_input = input_octets + ((req.Acct_Input_Gigawords or 0) * 2**32)
        total_output = output_octets + ((req.Acct_Output_Gigawords or 0) * 2**32)

        # Update accounting record
        result = await self.acct_collection.update_one(
            {"acct_session_id": req.Acct_Session_Id},
            {
                "$set": {
                    "acct_stop_time": now,
                    "acct_session_time": session_time,
                    "acct_input_octets": total_input,
                    "acct_output_octets": total_output,
                    "acct_input_gigawords": req.Acct_Input_Gigawords or 0,
                    "acct_output_gigawords": req.Acct_Output_Gigawords or 0,
                    "acct_terminate_cause": req.Acct_Terminate_Cause or "N/A",
                    "connectinfo_stop": req.Called_Station_Id,
                    "updated_at": now,
                }
            },
        )

        # Update live session to offline
        await self.session_collection.update_one(
            {"acct_session_id": req.Acct_Session_Id},
            {
                "$set": {
                    "status": "offline",
                    "acct_session_time": session_time,
                    "acct_input_octets": total_input,
                    "acct_output_octets": total_output,
                    "last_seen": now,
                }
            },
        )

        # Update user totals
        if req.User_Name:
            await self.user_collection.update_one(
                {"username": req.User_Name},
                {
                    "$inc": {
                        "total_online_time_sec": session_time,
                        "total_input_bytes": total_input,
                        "total_output_bytes": total_output,
                    }
                },
            )

        # Update subscription data usage
        acct_doc = await self.acct_collection.find_one({"acct_session_id": req.Acct_Session_Id})
        if acct_doc and acct_doc.get("subscription_id"):
            await self.subscription_collection.update_one(
                {"_id": ObjectId(acct_doc["subscription_id"])},
                {
                    "$inc": {
                        "data_used_bytes": total_input + total_output,
                        "total_session_time_sec": session_time,
                    }
                },
            )

        logger.info(f"RADIUS acct STOP: {req.User_Name} | session={req.Acct_Session_Id} | time={session_time}s | in={total_input} | out={total_output}")

    async def _accounting_interim(self, req: RadiusAccountingRequest) -> None:
        """Handle Interim-Update."""
        now = datetime.now(timezone.utc)
        session_time = req.Acct_Session_Time or 0
        input_octets = req.Acct_Input_Octets or 0
        output_octets = req.Acct_Output_Octets or 0
        total_input = input_octets + ((req.Acct_Input_Gigawords or 0) * 2**32)
        total_output = output_octets + ((req.Acct_Output_Gigawords or 0) * 2**32)

        # Update accounting record
        await self.acct_collection.update_one(
            {"acct_session_id": req.Acct_Session_Id},
            {
                "$set": {
                    "acct_update_time": now,
                    "acct_session_time": session_time,
                    "acct_input_octets": total_input,
                    "acct_output_octets": total_output,
                    "framed_ip_address": req.Framed_IP_Address,
                    "updated_at": now,
                }
            },
        )

        # Update live session
        await self.session_collection.update_one(
            {"acct_session_id": req.Acct_Session_Id},
            {
                "$set": {
                    "acct_session_time": session_time,
                    "acct_input_octets": total_input,
                    "acct_output_octets": total_output,
                    "framed_ip_address": req.Framed_IP_Address,
                    "last_seen": now,
                }
            },
        )

        # Check data cap and disconnect if exceeded
        acct_doc = await self.acct_collection.find_one({"acct_session_id": req.Acct_Session_Id})
        if acct_doc and acct_doc.get("subscription_id"):
            sub = await self.subscription_collection.find_one(
                {"_id": ObjectId(acct_doc["subscription_id"])}
            )
            if sub and sub.get("data_cap_bytes"):
                used = sub.get("data_used_bytes", 0) + total_input + total_output
                if used >= sub["data_cap_bytes"]:
                    logger.warning(f"Data cap exceeded for subscription {acct_doc['subscription_id']}, user {req.User_Name}")
                    # Note: Actual disconnect would require CoA or waiting for next auth
                    # For now, we log it. CoA implementation is Phase 7/8.

    # ── SESSION QUERIES ──

    async def get_online_sessions(
        self, site_id: Optional[str] = None, nas_ip: Optional[str] = None, page: int = 1, limit: int = 50
    ):
        query = {"status": "online"}
        if site_id:
            query["site_id"] = site_id
        if nas_ip:
            query["nas_ip_address"] = nas_ip

        skip = (page - 1) * limit
        total = await self.session_collection.count_documents(query)
        cursor = self.session_collection.find(query).skip(skip).limit(limit).sort("acct_start_time", -1)

        sessions = []
        async for doc in cursor:
            doc["_id"] = str(doc["_id"])
            sessions.append(doc)
        return sessions, total

    async def disconnect_session(self, session_id: str) -> bool:
        """Mark a session for disconnection (CoA will be implemented in Phase 7)."""
        result = await self.session_collection.update_one(
            {"acct_session_id": session_id},
            {"$set": {"status": "pending_disconnect", "updated_at": datetime.now(timezone.utc)}},
        )
        return result.modified_count > 0