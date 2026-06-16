import uuid
from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import String, Numeric, DateTime, ForeignKey, Text, Enum, Boolean
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.core.database import Base


class WalletStatus(str, PyEnum):
    ACTIVE = "active"
    FROZEN = "frozen"
    CLOSED = "closed"


class TransactionType(str, PyEnum):
    DEPOSIT = "deposit"
    WITHDRAWAL = "withdrawal"
    TRANSFER_IN = "transfer_in"
    TRANSFER_OUT = "transfer_out"
    FEE = "fee"
    REFUND = "refund"


class TransactionStatus(str, PyEnum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    REVERSED = "reversed"


class Wallet(Base):
    __tablename__ = "wallets"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    owner_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    balance: Mapped[float] = mapped_column(Numeric(18, 8), nullable=False, default=0)
    locked_balance: Mapped[float] = mapped_column(Numeric(18, 8), nullable=False, default=0)
    status: Mapped[str] = mapped_column(
        Enum(WalletStatus), default=WalletStatus.ACTIVE, nullable=False
    )
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    ledger_entries: Mapped[list["LedgerEntry"]] = relationship(
        "LedgerEntry", back_populates="wallet"
    )

    @property
    def available_balance(self) -> float:
        return float(self.balance) - float(self.locked_balance)


class LedgerEntry(Base):
    """
    Immutable ledger — every balance change is recorded here.
    Never update or delete ledger entries.
    """
    __tablename__ = "ledger_entries"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    idempotency_key: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    wallet_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("wallets.id"), nullable=False, index=True
    )
    type: Mapped[str] = mapped_column(Enum(TransactionType), nullable=False)
    status: Mapped[str] = mapped_column(
        Enum(TransactionStatus), default=TransactionStatus.PENDING, nullable=False
    )
    amount: Mapped[float] = mapped_column(Numeric(18, 8), nullable=False)
    balance_before: Mapped[float] = mapped_column(Numeric(18, 8), nullable=False)
    balance_after: Mapped[float] = mapped_column(Numeric(18, 8), nullable=False)
    reference_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)

    wallet: Mapped["Wallet"] = relationship("Wallet", back_populates="ledger_entries")
