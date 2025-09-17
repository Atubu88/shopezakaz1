import os
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from database.models import Base
from database.orm_query import orm_add_banner_description, orm_create_categories
from common.texts_for_db import categories, description_for_info_pages

# 🔑 Строка подключения берётся из .env
# Пример в .env:
# DB_URL=postgresql+asyncpg://user:password@localhost:5432/shopezakaz1

DATABASE_URL = os.getenv("DB_URL")
if not DATABASE_URL:
    raise ValueError("❌ DB_URL is not set in .env")

# ⚡️ Создаём движок PostgreSQL
engine = create_async_engine(DATABASE_URL, echo=False, future=True)

# ⚡️ Session factory
session_maker = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def create_db():
    """Создаёт все таблицы и наполняет начальными данными."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_maker() as session:
        await orm_create_categories(session, categories)
        await orm_add_banner_description(session, description_for_info_pages)


async def drop_db():
    """Удаляет все таблицы."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
