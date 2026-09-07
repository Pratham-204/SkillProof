from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Import the app's own models/Base and settings rather than duplicating the
# schema here — this is the same Base.metadata db.py's init_db() already
# calls create_all() against, so autogenerate diffs against the real models.
from skillproof.db import Base, _normalize_database_url  # noqa: E402
from skillproof.config import get_settings  # noqa: E402
import skillproof.models  # noqa: E402,F401  (registers tables on Base.metadata)

target_metadata = Base.metadata

# alembic.ini's sqlalchemy.url is a placeholder — always resolve the real URL
# from Settings (env vars / .env), the same source db.py's module-level
# `engine` uses, so a migration run never targets a different database than
# the app itself would connect to.
config.set_main_option("sqlalchemy.url", _normalize_database_url(get_settings().database_url))

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
