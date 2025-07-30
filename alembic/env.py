from logging.config import fileConfig
from sqlalchemy import pool
from alembic import context

import sys
import os

# Add your app root to the path for imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Load SYNC_DATABASE_URL and Base
from app.database import SYNC_DATABASE_URL, Base

# Import all models for 'autogenerate' support
from app.models import User, Company, Plan, CompanySubscription, APIUsage, Invoice, AllowedDomain, NavigationLog, NavigationLogHistory, TurnLog

# Alembic config object
config = context.config

# Set up Python logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Use SYNC_DATABASE_URL (not async) for migrations
config.set_main_option("sqlalchemy.url", SYNC_DATABASE_URL)
target_metadata = Base.metadata

def include_object(object, name, type_, reflected, compare_to):
    # Only manage your own tables, not 'auth_*' etc.
    if type_ == "table" and name.startswith("auth_"):
        return False
    return True

def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        include_object=include_object,
        # ...other args
    )
    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    from sqlalchemy import create_engine

    connectable = create_engine(
        config.get_main_option("sqlalchemy.url"),
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=include_object,
            # ...other args
        )
        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()





