import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
import redis.asyncio as redis

from app.core.database import get_db
from app.core.redis import get_redis
from app.schemas.wallet import (
    WalletCreateRequest, WalletResponse,
    DepositRequest, WithdrawalRequest, TransferRequest,
    LedgerEntryResponse,
)
from app.services.wallet_service import WalletService

router = APIRouter(prefix="/wallets", tags=["Wallets"])


def get_service(
    db: AsyncSession = Depends(get_db),
    redis_client: redis.Redis = Depends(get_redis),
) -> WalletService:
    return WalletService(db=db, redis_client=redis_client)


@router.post("/", response_model=WalletResponse, status_code=status.HTTP_201_CREATED)
async def create_wallet(
    request: WalletCreateRequest,
    service: WalletService = Depends(get_service),
):
    """Create a new wallet for an owner."""
    wallet = await service.create_wallet(request)
    return WalletResponse.model_validate(wallet)


@router.get("/{wallet_id}", response_model=WalletResponse)
async def get_wallet(
    wallet_id: uuid.UUID,
    service: WalletService = Depends(get_service),
):
    """Get wallet details and current balance."""
    wallet = await service.get_wallet(wallet_id)
    if not wallet:
        raise HTTPException(status_code=404, detail="Wallet not found")
    return WalletResponse.model_validate(wallet)


@router.post("/{wallet_id}/deposit", response_model=LedgerEntryResponse)
async def deposit(
    wallet_id: uuid.UUID,
    request: DepositRequest,
    service: WalletService = Depends(get_service),
):
    """
    Deposit funds into a wallet.
    Uses idempotency key to prevent duplicate deposits.
    Distributed lock prevents concurrent balance corruption.
    """
    try:
        entry = await service.deposit(wallet_id, request)
        return LedgerEntryResponse.model_validate(entry)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{wallet_id}/withdraw", response_model=LedgerEntryResponse)
async def withdraw(
    wallet_id: uuid.UUID,
    request: WithdrawalRequest,
    service: WalletService = Depends(get_service),
):
    """
    Withdraw funds from a wallet.
    Checks available balance (balance - locked_balance).
    """
    try:
        entry = await service.withdraw(wallet_id, request)
        return LedgerEntryResponse.model_validate(entry)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{wallet_id}/transfer", response_model=List[LedgerEntryResponse])
async def transfer(
    wallet_id: uuid.UUID,
    request: TransferRequest,
    service: WalletService = Depends(get_service),
):
    """
    Transfer funds between two wallets atomically.
    Uses ordered locking to prevent deadlocks.
    Both wallets must have the same currency.
    """
    try:
        debit, credit = await service.transfer(wallet_id, request)
        return [
            LedgerEntryResponse.model_validate(debit),
            LedgerEntryResponse.model_validate(credit),
        ]
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{wallet_id}/ledger", response_model=List[LedgerEntryResponse])
async def get_ledger(
    wallet_id: uuid.UUID,
    limit: int = 20,
    offset: int = 0,
    service: WalletService = Depends(get_service),
):
    """Get paginated ledger history for a wallet."""
    entries = await service.get_ledger(wallet_id, limit, offset)
    return [LedgerEntryResponse.model_validate(e) for e in entries]
