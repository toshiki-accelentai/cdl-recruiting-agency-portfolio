"""VAPI-shaped request. Only the fields we use are modelled; the rest is kept raw."""
from datetime import datetime
from zoneinfo import ZoneInfo

from pydantic import BaseModel as _Base, ConfigDict, field_validator

BUSINESS_TZ = ZoneInfo("America/Vancouver")


class BaseModel(_Base):
    # Keep fields we do not model so raw_payload stores what VAPI really sent.
    model_config = ConfigDict(extra="allow")


class IntakeArguments(BaseModel):
    name: str
    phoneNumber: str
    city: str = ""
    state: str = ""
    zipCode: str = ""
    experience: str = ""
    readiness: str = ""
    preferredCallbackTime: datetime | None = None

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("name must not be blank")
        return v.strip()

    @field_validator("preferredCallbackTime")
    @classmethod
    def naive_means_vancouver(cls, v: datetime | None) -> datetime | None:
        # VAPI sends e.g. "2026-09-25T10:00:00" with no offset: business-local time.
        if v is not None and v.tzinfo is None:
            return v.replace(tzinfo=BUSINESS_TZ)
        return v


class ToolFunction(BaseModel):
    name: str
    arguments: IntakeArguments


class ToolCall(BaseModel):
    id: str
    function: ToolFunction


class CallInfo(BaseModel):
    id: str


class Message(BaseModel):
    toolCalls: list[ToolCall]
    call: CallInfo

    @field_validator("toolCalls")
    @classmethod
    def at_least_one(cls, v: list[ToolCall]) -> list[ToolCall]:
        if not v:
            raise ValueError("toolCalls must not be empty")
        return v


class IntakeRequest(BaseModel):
    message: Message
