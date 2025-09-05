from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from alembic import context
import os
import sys
from pathlib import Path

ROOT_PATH = Path(__file__).parent.parent
sys.path.append(str(ROOT_PATH))

from app.models.base import Base
from app.models import *

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

def get_url():
    from app.config import settings
    db_url = settings.DATABASE_URL

    # ✅ CRITICAL FIX: Convert async URLs to sync URLs
    if db_url.startswith('sqlite+aiosqlite:'):
        sync_url = db_url.replace('sqlite+aiosqlite:', 'sqlite:')
        print(f"🔄 Converted URL for Alembic: aiosqlite -> sqlite")
        return sync_url

    if db_url.startswith('postgresql+asyncpg:'):
        sync_url = db_url.replace('postgresql+asyncpg:', 'postgresql+psycopg2:')
        print(f"🔄 Converted URL for Alembic: asyncpg -> psycopg2")
        return sync_url

    return db_url

def run_migrations_offline() -> None:
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online() -> None:
    configuration = config.get_section(config.config_ini_section, {})

    configuration["sqlalchemy.url"] = get_url()

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
