"""Configuração do ambiente de migrações Alembic."""

from dotenv import load_dotenv
import os

from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context

#Importa a Base diretamente do módulo infra
from infra.db import Base
#Importa explicitamente todos os modelos para que Base.metadata os conheça
import alert_app.models.models_scraping_errors
import alert_app.models.models_users
import alert_app.models.models_refresh_token
import alert_app.models.models_products
import alert_app.models.models_login_attempt
import alert_app.models.models_comparisons
import alert_app.models.models_alerts

#Carrega o .env do projeto
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))

config = context.config

config.set_main_option("sqlalchemy.url", os.environ["DATABASE_URL"])

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata



def run_migrations_offline() -> None:
    """Executa migrações no modo 'offline'.

    Configura o contexto apenas com a URL de conexão,
    sem criar um Engine. Desse modo, não é necessário
    ter o DBAPI disponível. Chamadas para ``context.execute()``
    apenas emitem o SQL gerado.

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
    """Executa migrações no modo 'online'.

    Nesse cenário é criado um Engine e uma conexão
    é associada ao contexto antes de rodar as migrações.

    """
    configuration = config.get_section(config.config_ini_section)
    configuration["sqlalchemy.url"] = os.environ["DATABASE_URL"]

    connectable = engine_from_config(
        configuration,
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
