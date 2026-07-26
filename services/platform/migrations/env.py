"""Alembic environment (sync).

The URL comes from application settings, not alembic.ini, so migrations and the
app never disagree about which database they target. ``target_metadata`` is None
until domain models exist (M2); the baseline revision is intentionally empty.
"""

import contextlib
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# Import model modules for their side effect: registering tables on Base.metadata
# so autogenerate and `target_metadata` see the full schema.
import app.applicants.domain
import app.cases.domain
import app.shared.records  # noqa: F401  (registration side effect)
from app.core.config import get_settings
from app.shared.db import Base

config = context.config
config.set_main_option("sqlalchemy.url", get_settings().database_url)

# alembic.ini here omits the logging sections, so guard fileConfig.
if config.config_file_name is not None:
    with contextlib.suppress(Exception):
        fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
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
