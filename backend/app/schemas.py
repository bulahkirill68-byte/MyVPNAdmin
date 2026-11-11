import ipaddress
import re
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Credentials(Strict):
    name: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=256)


class UserInput(Strict):
    name: str = Field(min_length=1, max_length=100)
    comment: str = Field(default="", max_length=2000)
    expires_at: int | None = Field(default=None, ge=1, le=253402300799)
    quota_bytes: int | None = Field(default=None, ge=1, le=10**16)
    policy: Literal["ru-direct", "all-proxy", "custom"] = "ru-direct"


class Action(Strict):
    action: Literal["pause", "resume", "revoke", "renew", "rotate", "delete", "token", "revoke_token"]
    confirm: bool = False
    days: int = Field(default=30, ge=1, le=3650)
    mode: Literal["now", "expiry"] = "expiry"
    expected_expires: int | None = None


class Metadata(Strict):
    ip: str
    port: int = Field(ge=1, le=65535)
    sni: str = Field(min_length=1, max_length=253)
    public_key: str = Field(pattern=r"^[A-Za-z0-9_-]{43}$")
    short_id: str = Field(pattern=r"^(?:[a-fA-F0-9]{2}){0,8}$")
    tag: str = Field(default="vless-reality", min_length=1, max_length=100)

    @field_validator("ip")
    @classmethod
    def ipv4(cls, value):
        addr = ipaddress.IPv4Address(value)
        if not addr.is_global:
            raise ValueError("Нужен публичный IPv4")
        return str(addr)

    @field_validator("sni")
    @classmethod
    def domain(cls, value):
        encoded = value.encode("idna").decode("ascii")
        if not re.fullmatch(r"[A-Za-z0-9.-]+", encoded):
            raise ValueError("Некорректный SNI")
        return encoded


class ImportedUser(Strict):
    name: str = Field(min_length=1, max_length=100)
    uuid: UUID
    email: str = Field(pattern=r"^[A-Za-z0-9_.@+-]{1,150}$")
    expires_at: int | None = Field(default=None, ge=1)


class Onboarding(Strict):
    server: Metadata
    users: list[ImportedUser] = Field(min_length=1, max_length=5000)


class RouteRule(Strict):
    kind: Literal["domain", "ip"]
    values: list[str] = Field(min_length=1, max_length=100)
    outbound: Literal["proxy", "direct", "block"]

    @field_validator("values")
    @classmethod
    def clean(cls, values):
        if any(not v or len(v) > 253 or any(c.isspace() for c in v) for v in values):
            raise ValueError("Некорректные значения правила")
        return values


class Routing(Strict):
    preset: Literal["ru-direct", "all-proxy", "custom"] = "ru-direct"
    rules: list[RouteRule] = Field(default_factory=list, max_length=100)
    user_rules: list[RouteRule] = Field(default_factory=list, max_length=100)
    local_rules: list[RouteRule] = Field(default_factory=list, max_length=100)
