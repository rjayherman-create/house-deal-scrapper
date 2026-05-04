import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

# Get DATABASE_URL from Railway
raw_db_url = os.getenv("DATABASE_URL")
if raw_db_url is None:
    raise RuntimeError("DATABASE_URL is not set")

# FORCE asyncpg driver
# Convert postgres:// → postgresql+asyncpg://
if raw_db_url.startswith("postgres://"):
    raw_db_url = raw_db_url.replace("postgres://", "postgresql+asyncpg://", 1)

# If it already starts with postgresql://, convert it too
if raw_db_url.startswith("postgresql://"):
    raw_db_url = raw_db_url.replace("postgresql://", "postgresql+asyncpg://", 1)

engine = create_async_engine(
    raw_db_url,
    echo=False,
    future=True
)

AsyncSessionLocal = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
