from alembic import context
from sqlalchemy import create_engine

from ctxvcs.config import settings

config = context.config


def run_migrations_offline() -> None:
    context.configure(url=settings().database_url, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(settings().database_url)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=None)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
