import re
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from aevyra_contracts.commercial import AnalysisView


class Credentials(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    login_identifier: str = Field(min_length=3, max_length=120)
    password: str = Field(min_length=12, max_length=128)

    @field_validator("login_identifier")
    @classmethod
    def normalize_identifier(cls, value: str) -> str:
        value = value.strip().lower()
        if not re.fullmatch(r"[a-z0-9][a-z0-9._@+-]{2,119}", value):
            raise ValueError("Use a username or email-like identifier")
        return value


class UserView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    public_user_id: str
    login_identifier: str


class SessionView(BaseModel):
    user: UserView
    csrf_token: str


class RedeemRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    code: str = Field(min_length=1, max_length=40)


class RedemptionView(BaseModel):
    credits_added: int
    balance: int


class CreditAnalysisRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    product_slug: str = Field(min_length=1, max_length=100)
    idempotency_key: UUID


class CreditEntryView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    amount: int
    transaction_type: str
    balance_after: int
    created_at: datetime


class WalletView(BaseModel):
    balance: int
    transactions: list[CreditEntryView]


class CreditProductView(BaseModel):
    slug: str
    name: str
    credit_cost: int
    available: bool


class AccountView(BaseModel):
    user: UserView
    wallet: WalletView
    analyses: list[AnalysisView]
