import redis.asyncio as redis
from app.core.config import settings

redis_client: redis.Redis = None


async def get_redis() -> redis.Redis:
    return redis_client


async def init_redis():
    global redis_client
    redis_client = redis.from_url(
        settings.REDIS_URL, encoding="utf-8", decode_responses=True
    )


async def close_redis():
    if redis_client:
        await redis_client.close()


class DistributedLock:
    """
    Redis-based distributed lock to prevent race conditions
    on concurrent balance updates.
    """

    def __init__(self, redis_client: redis.Redis, key: str, ttl: int = 30):
        self.redis = redis_client
        self.key = f"lock:{key}"
        self.ttl = ttl

    async def __aenter__(self):
        acquired = await self.redis.set(
            self.key, "1", nx=True, ex=self.ttl
        )
        if not acquired:
            raise RuntimeError(f"Could not acquire lock for {self.key}")
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.redis.delete(self.key)
