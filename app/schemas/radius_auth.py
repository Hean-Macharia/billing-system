"""RADIUS auth/accounting schemas for FreeRADIUS rlm_rest integration.

These schemas define the JSON payloads exchanged between FreeRADIUS and FastAPI.
"""
from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator


_INTEGER_ENUM_ATTRIBUTES_STORED_AS_STRINGS = {
    "NAS-Port",
    "NAS-Port-Type",
    "Service-Type",
    "Framed-Protocol",
    "Acct-Authentic",
    "Acct-Terminate-Cause",
}

_ACCT_STATUS_TYPE_CODES = {
    1: "Start",
    2: "Stop",
    3: "Interim-Update",
    7: "Accounting-On",
    8: "Accounting-Off",
}


class RadiusRequestModel(BaseModel):
    """Accept flat test payloads and FreeRADIUS rlm_rest JSON attributes."""

    model_config = {"populate_by_name": True}

    @model_validator(mode="before")
    @classmethod
    def flatten_freeradius_attributes(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value

        flattened = {}
        for name, attribute in value.items():
            attribute_name = name.rsplit(":", 1)[-1]
            if isinstance(attribute, dict) and "value" in attribute:
                attribute = attribute["value"]
            if isinstance(attribute, list):
                attribute = attribute[0] if attribute else None
            if attribute_name == "Acct-Status-Type" and (
                type(attribute) is int
                or isinstance(attribute, str) and attribute.isdecimal()
            ):
                status_code = int(attribute)
                attribute = _ACCT_STATUS_TYPE_CODES.get(status_code, str(status_code))
            elif (
                attribute_name in _INTEGER_ENUM_ATTRIBUTES_STORED_AS_STRINGS
                and type(attribute) is int
            ):
                attribute = str(attribute)
            flattened[attribute_name] = attribute
        return flattened



class RadiusAuthRequest(RadiusRequestModel):
    """Incoming auth request from FreeRADIUS rlm_rest."""

    User_Name: Optional[str] = Field(alias="User-Name", default=None)
    User_Password: Optional[str] = Field(alias="User-Password", default=None)
    NAS_IP_Address: Optional[str] = Field(alias="NAS-IP-Address", default=None)
    NAS_Port: Optional[str] = Field(alias="NAS-Port", default=None)
    NAS_Identifier: Optional[str] = Field(alias="NAS-Identifier", default=None)
    NAS_Port_Type: Optional[str] = Field(alias="NAS-Port-Type", default=None)
    Service_Type: Optional[str] = Field(alias="Service-Type", default=None)
    Framed_Protocol: Optional[str] = Field(alias="Framed-Protocol", default=None)
    Acct_Session_Id: Optional[str] = Field(alias="Acct-Session-Id", default=None)
    Calling_Station_Id: Optional[str] = Field(alias="Calling-Station-Id", default=None)
    Called_Station_Id: Optional[str] = Field(alias="Called-Station-Id", default=None)
    CHAP_Password: Optional[str] = Field(alias="CHAP-Password", default=None)
    CHAP_Challenge: Optional[str] = Field(alias="CHAP-Challenge", default=None)
    MS_CHAP_Challenge: Optional[str] = Field(alias="MS-CHAP-Challenge", default=None)
    MS_CHAP_Response: Optional[str] = Field(alias="MS-CHAP-Response", default=None)
    MS_CHAP2_Response: Optional[str] = Field(alias="MS-CHAP2-Response", default=None)


class RadiusAuthResponse(BaseModel):
    """Outgoing auth response to FreeRADIUS rlm_rest.

    FreeRADIUS rlm_rest expects:
      control:Auth-Type = Accept | Reject
      reply:Attribute-Name = value
    """
    model_config = {"populate_by_name": True}

    control_Auth_Type: str = Field(default="Accept", alias="control:Auth-Type")
    reply_Mikrotik_Rate_Limit: Optional[str] = Field(default=None, alias="reply:Mikrotik-Rate-Limit")
    reply_Session_Timeout: Optional[int] = Field(default=None, alias="reply:Session-Timeout")
    reply_Idle_Timeout: Optional[int] = Field(default=None, alias="reply:Idle-Timeout")
    reply_Framed_IP_Address: Optional[str] = Field(default=None, alias="reply:Framed-IP-Address")
    reply_Framed_Pool: Optional[str] = Field(default=None, alias="reply:Framed-Pool")
    reply_Acct_Interim_Interval: Optional[int] = Field(default=300, alias="reply:Acct-Interim-Interval")
    reply_Service_Type: Optional[str] = Field(default=None, alias="reply:Service-Type")
    reply_Class: Optional[str] = Field(default=None, alias="reply:Class")
    reply_Simultaneous_Use: Optional[int] = Field(default=None, alias="reply:Simultaneous-Use")
    reply_Mikrotik_Recv_Limit: Optional[int] = Field(default=None, alias="reply:Mikrotik-Recv-Limit")
    reply_Mikrotik_Xmit_Limit: Optional[int] = Field(default=None, alias="reply:Mikrotik-Xmit-Limit")
    reply_Mikrotik_Total_Limit: Optional[int] = Field(default=None, alias="reply:Mikrotik-Total-Limit")
    reply_Mikrotik_Total_Limit_Gigawords: Optional[int] = Field(
        default=None,
        alias="reply:Mikrotik-Total-Limit-Gigawords",
    )
    reply_Mikrotik_Hostspot_Max_Original_Url: Optional[str] = Field(default=None, alias="reply:Mikrotik-Hostspot-Max-Original-Url")
    reply_Reply_Message: Optional[str] = Field(default=None, alias="reply:Reply-Message")


class RadiusAccountingRequest(RadiusRequestModel):
    """Incoming accounting request from FreeRADIUS rlm_rest."""

    Acct_Status_Type: str = Field(alias="Acct-Status-Type")
    User_Name: Optional[str] = Field(alias="User-Name", default=None)
    NAS_IP_Address: Optional[str] = Field(alias="NAS-IP-Address", default=None)
    NAS_Port: Optional[str] = Field(alias="NAS-Port", default=None)
    NAS_Identifier: Optional[str] = Field(alias="NAS-Identifier", default=None)
    NAS_Port_Type: Optional[str] = Field(alias="NAS-Port-Type", default=None)
    Acct_Session_Id: Optional[str] = Field(alias="Acct-Session-Id", default=None)
    Acct_Authentic: Optional[str] = Field(alias="Acct-Authentic", default=None)
    Acct_Session_Time: Optional[int] = Field(alias="Acct-Session-Time", default=0)
    Acct_Input_Octets: Optional[int] = Field(alias="Acct-Input-Octets", default=0)
    Acct_Output_Octets: Optional[int] = Field(alias="Acct-Output-Octets", default=0)
    Acct_Input_Gigawords: Optional[int] = Field(alias="Acct-Input-Gigawords", default=0)
    Acct_Output_Gigawords: Optional[int] = Field(alias="Acct-Output-Gigawords", default=0)
    Calling_Station_Id: Optional[str] = Field(alias="Calling-Station-Id", default=None)
    Called_Station_Id: Optional[str] = Field(alias="Called-Station-Id", default=None)
    Acct_Terminate_Cause: Optional[str] = Field(alias="Acct-Terminate-Cause", default=None)
    Framed_IP_Address: Optional[str] = Field(alias="Framed-IP-Address", default=None)
    Framed_Protocol: Optional[str] = Field(alias="Framed-Protocol", default=None)
    Service_Type: Optional[str] = Field(alias="Service-Type", default=None)
    Event_Timestamp: Optional[datetime] = Field(alias="Event-Timestamp", default=None)
    Class: Optional[str] = Field(alias="Class", default=None)
    Acct_Delay_Time: Optional[int] = Field(alias="Acct-Delay-Time", default=0)

    @field_validator("Event_Timestamp", mode="before")
    @classmethod
    def normalize_event_timestamp(cls, value: object) -> object:
        if value is None:
            return None

        if isinstance(value, bool):
            raise ValueError("Event-Timestamp must be an ISO-8601 date or Unix timestamp")

        if isinstance(value, int):
            try:
                return datetime.fromtimestamp(value, tz=timezone.utc)
            except (OverflowError, OSError, ValueError) as exc:
                raise ValueError("Event-Timestamp Unix value is out of range") from exc

        if isinstance(value, str):
            normalized = value.strip()
            if normalized.lstrip("+-").isdigit():
                try:
                    return datetime.fromtimestamp(int(normalized), tz=timezone.utc)
                except (OverflowError, OSError, ValueError) as exc:
                    raise ValueError("Event-Timestamp Unix value is out of range") from exc

            if normalized.endswith(("Z", "z")):
                normalized = f"{normalized[:-1]}+00:00"
            try:
                parsed = datetime.fromisoformat(normalized)
            except ValueError:
                return value

            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)

        return value