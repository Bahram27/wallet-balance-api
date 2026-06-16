import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field

from app.models.wallet import WalletStatus, TransactionType, TransactionStatus


class WalletCreateRequest(BaseModel):
    owner_id: str = Field(..., min_length=1, max_length=255)
    currency: str = Field(..., min_length=3, max_length=3)
    is_default: bool = False


class WalletResponse(BaseModel):
    id: uuid.UUID
    owner_id: str
    currency: str
    balance: Decimal
    locked_balance: Decimal
    available_balance: Decimal
    status: WalletStatus
    is_default: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DepositRequest(BaseModel):
    idempotency_key: str = Field(..., min_length=8, max_length=255)
    amount: Decimal = Field(..., gt=0, decimal_places=8)
    reference_id: Optional[str] = None
    description: Optional[str] = None


class WithdrawalRequest(BaseModel):
    idempotency_key: str = Field(..., min_length=8, max_length=255)
    amount: Decimal = Field(..., gt=0, decimal_places=8)
    reference_id: Optional[str] = None
    description: Optional[str] = None


class TransferRequest(BaseModel):
    idempotency_key: str = Field(..., min_length=8, max_length=255)
    to_wallet_id: uuid.UUID
    amount: Decimal = Field(..., gt=0, decimal_places=8)
    description: Optional[str] = None


class LedgerEntryResponse(BaseModel):
    id: uuid.UUID
    idempotency_key: str
    wallet_id: uuid.UUID
    type: TransactionType
    status: TransactionStatus
    amount: Decimal
    balance_before: Decimal
    balance_after: Decimal
    reference_id: Optional[str]
    description: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}
