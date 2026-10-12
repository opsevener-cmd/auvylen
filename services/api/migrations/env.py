from aevyra_api.commercial import models as commercial_models
from aevyra_api.config import Settings
from aevyra_api.credits import models as credit_models
from aevyra_api.database import Base, build_engine
from aevyra_api.models import FoundationRecord
from aevyra_api.preferences import models as preference_models
from aevyra_api.research import models as research_models
from alembic import context

target_metadata = Base.metadata
assert FoundationRecord.__table__.metadata is target_metadata
assert commercial_models.Product.__table__.metadata is target_metadata
assert credit_models.Wallet.__table__.metadata is target_metadata
assert research_models.ResearchJob.__table__.metadata is target_metadata
assert preference_models.PreferenceDataset.__table__.metadata is target_metadata


def run_migrations() -> None:
    settings = Settings()
    if context.is_offline_mode():
        context.configure(
            url=settings.database_url.get_secret_value(),
            target_metadata=target_metadata,
            literal_binds=True,
            dialect_opts={"paramstyle": "named"},
        )
        with context.begin_transaction():
            context.run_migrations()
    else:
        supplied = context.config.attributes.get("connection")
        if supplied is not None:
            context.configure(
                connection=supplied,
                target_metadata=target_metadata,
                render_as_batch=supplied.dialect.name == "sqlite",
            )
            with context.begin_transaction():
                context.run_migrations()
            return
        engine = build_engine(settings)
        try:
            with engine.connect() as connection:
                context.configure(connection=connection, target_metadata=target_metadata)
                with context.begin_transaction():
                    context.run_migrations()
        finally:
            engine.dispose()


run_migrations()
