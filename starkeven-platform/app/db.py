from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from .config import settings

if settings.environment == "test":
    # Each test runs in its own event loop; pooled asyncpg connections can't cross loops.
    _kwargs: dict = {"poolclass": NullPool}
else:
    _kwargs = {"pool_size": 10, "max_overflow": 20}

engine = create_async_engine(settings.database_url, pool_pre_ping=True, **_kwargs)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def init_db() -> None:
    from .models import Base

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db():
    async with SessionLocal() as session:
        yield session
