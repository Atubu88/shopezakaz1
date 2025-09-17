import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine

from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv())

# чтобы можно было импортировать проектные модули
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# импортируем Base со всеми моделями
from database.models import Base  # noqa

# Alembic config
config = context.config

# Логирование Alembic
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Метаданные моделей (для autogenerate)
target_metadata = Base.metadata


def get_sync_url() -> str:
    url = os.getenv("DATABASE_URL_SYNC")
    if not url:
        raise RuntimeError("DATABASE_URL_SYNC is not set in environment")
    return url


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = get_sync_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    url = get_sync_url()
    connectable = create_engine(url)

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
