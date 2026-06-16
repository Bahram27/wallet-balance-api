# Wallet Balance API

Production-ready wallet and balance management API with idempotent transactions, distributed locking, and immutable ledger.

## Tech Stack

- **FastAPI** — async REST API
- **PostgreSQL** + **SQLAlchemy** — persistent storage
- **Redis** — distributed locking & caching
- **Alembic** — database migrations
- **Docker** + **docker-compose** — containerization

## Key Features

- Idempotent deposit/withdrawal (safe to retry)
- Distributed lock prevents concurrent balance corruption
- Immutable ledger — every balance change is recorded
- Atomic transfers with deadlock prevention
- Available balance = balance - locked_balance

## Architecture

```
Client Request
      │
      ▼
 FastAPI Layer
      │
      ▼
 WalletService
   ├── Idempotency Check (Redis)
   ├── Distributed Lock (Redis)
   ├── Balance Update (PostgreSQL)
   └── Ledger Entry (PostgreSQL — immutable)
```

## Quick Start

```bash
git clone https://github.com/Bahram27/wallet-balance-api.git
cd wallet-balance-api
docker-compose up -d
```

API docs: http://localhost:8002/docs

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/wallets` | Create wallet |
| GET | `/api/v1/wallets/{id}` | Get wallet & balance |
| POST | `/api/v1/wallets/{id}/deposit` | Deposit funds |
| POST | `/api/v1/wallets/{id}/withdraw` | Withdraw funds |
| POST | `/api/v1/wallets/{id}/transfer` | Transfer between wallets |
| GET | `/api/v1/wallets/{id}/ledger` | Transaction history |

## Concurrency Safety

Two requests arriving simultaneously for the same wallet:
1. Both try to acquire Redis distributed lock
2. First request acquires lock, updates balance, releases lock
3. Second request acquires lock, reads updated balance, proceeds safely

No race conditions, no double-spending.
