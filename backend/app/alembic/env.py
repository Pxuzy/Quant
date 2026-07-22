"""Alembic env — reads DB URL from project settings so tests and app share the same config."""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# Alembic Config object
config = context.config

# Set up loggers
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Import all models so autogenerate can detect them
from backend.app.db.base import Base  # noqa: E402
from backend.app.models import entities  # noqa: E402, F401

target_metadata = Base.metadata

# Prefer the URL explicitly supplied by Alembic (including test/app overrides).
# Fall back to project settings only when the config has no URL.
url = config.get_main_option("sqlalchemy.url")
if not url or url.startswith("driver://"):
    try:
        from backend.app.db.session import get_database_url

        url = get_database_url()
    except Exception:
        url = None


def run_migrations_offline() -> None:
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    # Alembic creates its own engine so it's independent of app lifecycle
    cfg = config.get_section(config.config_ini_section, {})
    cfg["sqlalchemy.url"] = url
    connectable = engine_from_config(
        cfg,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
