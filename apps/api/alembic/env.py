import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.models import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# URL lay tu bien moi truong — khong bao gio hard-code vao file
url = os.getenv("DATABASE_URL", "postgresql://dataops:dataops@localhost:5432/dataops")

# Secret Manager giu dang "postgresql://" vi psycopg thuan (API, Sync Job)
# doc truc tiep duoc. Nhung SQLAlchemy lai anh xa dang do sang psycopg2 —
# thu minh khong cai. Ep ve driver psycopg v3 o day de mot secret duy nhat
# dung duoc cho ca hai.
if url.startswith("postgresql://"):
    url = url.replace("postgresql://", "postgresql+psycopg://", 1)
config.set_main_option("sqlalchemy.url", url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=url, target_metadata=target_metadata,
        literal_binds=True, dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.", poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
