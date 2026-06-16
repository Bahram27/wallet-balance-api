import json
import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import redis.asyncio as redis

from app.core.config import settings
from app.core.redis import DistributedLock
from app.models.wallet import Wallet, LedgerEntry, WalletStatus, TransactionType, TransactionStatus
from app.schemas.wallet import (
    WalletCreateRequest, DepositRequest, WithdrawalRequest, TransferRequest
)


class WalletService:
    def __init__(self, db: AsyncSession, redis_client: redis.Redis):
        self.db = db
        self.redis = redis_client

    async def create_wallet(self, request: WalletCreateRequest) -> Wallet:
        wallet = Wallet(
            owner_id=request.owner_id,
            currency=request.currency,
            balance=Decimal("0"),
            locked_balance=Decimal("0"),
            is_default=request.is_default,
        )
        self.db.add(wallet)
        await self.db.flush()
        return wallet

    async def get_wallet(self, wallet_id: uuid.UUID) -> Wallet | None:
        # Try Redis cache first
        cached = await self.redis.get(f"wallet:{wallet_id}")
        if cached:
            pass  # In production: deserialize and return

        result = await self.db.execute(
            select(Wallet).where(Wallet.id == wallet_id)
        )
        return result.scalar_one_or_none()

    async def deposit(self, wallet_id: uuid.UUID, request: DepositRequest) -> LedgerEntry:
        # Idempotency check
        existing = await self._get_ledger_by_idempotency(request.idempotency_key)
        if existing:
            return existing

        # Distributed lock — prevents concurrent balance updates
        async with DistributedLock(self.redis, f"wallet:{wallet_id}", settings.LOCK_TTL):
            wallet = await self.get_wallet(wallet_id)
            if not wallet:
                raise ValueError(f"Wallet {wallet_id} not found")
            if wallet.status != WalletStatus.ACTIVE:
                raise ValueError(f"Wallet is {wallet.status}, cannot deposit")

            balance_before = Decimal(str(wallet.balance))
            balance_after = balance_before + request.amount

            # Update balance
            wallet.balance = balance_after

            # Create immutable ledger entry
            entry = LedgerEntry(
                idempotency_key=request.idempotency_key,
                wallet_id=wallet_id,
                type=TransactionType.DEPOSIT,
                status=TransactionStatus.COMPLETED,
                amount=request.amount,
                balance_before=balance_before,
                balance_after=balance_after,
                reference_id=request.reference_id,
                description=request.description,
            )
            self.db.add(entry)
            await self.db.flush()

            # Invalidate cache
            await self.redis.delete(f"wallet:{wallet_id}")

        return entry

    async def withdraw(self, wallet_id: uuid.UUID, request: WithdrawalRequest) -> LedgerEntry:
        # Idempotency check
        existing = await self._get_ledger_by_idempotency(request.idempotency_key)
        if existing:
            return existing

        async with DistributedLock(self.redis, f"wallet:{wallet_id}", settings.LOCK_TTL):
            wallet = await self.get_wallet(wallet_id)
            if not wallet:
                raise ValueError(f"Wallet {wallet_id} not found")
            if wallet.status != WalletStatus.ACTIVE:
                raise ValueError(f"Wallet is {wallet.status}, cannot withdraw")

            available = Decimal(str(wallet.balance)) - Decimal(str(wallet.locked_balance))
            if available < request.amount:
                raise ValueError(
                    f"Insufficient balance. Available: {available}, Requested: {request.amount}"
                )

            balance_before = Decimal(str(wallet.balance))
            balance_after = balance_before - request.amount
            wallet.balance = balance_after

            entry = LedgerEntry(
                idempotency_key=request.idempotency_key,
                wallet_id=wallet_id,
                type=TransactionType.WITHDRAWAL,
                status=TransactionStatus.COMPLETED,
                amount=request.amount,
                balance_before=balance_before,
                balance_after=balance_after,
                reference_id=request.reference_id,
                description=request.description,
            )
            self.db.add(entry)
            await self.db.flush()

            await self.redis.delete(f"wallet:{wallet_id}")

        return entry

    async def transfer(self, from_wallet_id: uuid.UUID, request: TransferRequest) -> tuple[LedgerEntry, LedgerEntry]:
        """
        Atomic transfer between two wallets.
        Uses ordered locking to prevent deadlocks.
        """
        # Always lock in consistent order to prevent deadlocks
        first_id, second_id = sorted([str(from_wallet_id), str(request.to_wallet_id)])

        async with DistributedLock(self.redis, f"wallet:{first_id}", settings.LOCK_TTL):
            async with DistributedLock(self.redis, f"wallet:{second_id}", settings.LOCK_TTL):
                from_wallet = await self.get_wallet(from_wallet_id)
                to_wallet = await self.get_wallet(request.to_wallet_id)

                if not from_wallet or not to_wallet:
                    raise ValueError("One or both wallets not found")
                if from_wallet.currency != to_wallet.currency:
                    raise ValueError("Cannot transfer between different currencies")

                available = Decimal(str(from_wallet.balance)) - Decimal(str(from_wallet.locked_balance))
                if available < request.amount:
                    raise ValueError(f"Insufficient balance. Available: {available}")

                # Debit from sender
                from_balance_before = Decimal(str(from_wallet.balance))
                from_wallet.balance = from_balance_before - request.amount

                debit_entry = LedgerEntry(
                    idempotency_key=f"{request.idempotency_key}:out",
                    wallet_id=from_wallet_id,
                    type=TransactionType.TRANSFER_OUT,
                    status=TransactionStatus.COMPLETED,
                    amount=request.amount,
                    balance_before=from_balance_before,
                    balance_after=Decimal(str(from_wallet.balance)),
                    description=request.description,
                )

                # Credit to receiver
                to_balance_before = Decimal(str(to_wallet.balance))
                to_wallet.balance = to_balance_before + request.amount

                credit_entry = LedgerEntry(
                    idempotency_key=f"{request.idempotency_key}:in",
                    wallet_id=request.to_wallet_id,
                    type=TransactionType.TRANSFER_IN,
                    status=TransactionStatus.COMPLETED,
                    amount=request.amount,
                    balance_before=to_balance_before,
                    balance_after=Decimal(str(to_wallet.balance)),
                    description=request.description,
                )

                self.db.add(debit_entry)
                self.db.add(credit_entry)
                await self.db.flush()

                await self.redis.delete(f"wallet:{from_wallet_id}")
                await self.redis.delete(f"wallet:{request.to_wallet_id}")

        return debit_entry, credit_entry

    async def get_ledger(
        self, wallet_id: uuid.UUID, limit: int = 20, offset: int = 0
    ) -> list[LedgerEntry]:
        result = await self.db.execute(
            select(LedgerEntry)
            .where(LedgerEntry.wallet_id == wallet_id)
            .order_by(LedgerEntry.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return result.scalars().all()

    async def _get_ledger_by_idempotency(self, key: str) -> LedgerEntry | None:
        result = await self.db.execute(
            select(LedgerEntry).where(LedgerEntry.idempotency_key == key)
        )
        return result.scalar_one_or_none()
