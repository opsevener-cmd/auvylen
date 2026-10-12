from redis import Redis
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from aevyra_api.config import Settings


class Base(DeclarativeBase):
    pass


def build_engine(settings: Settings) -> Engine:
    return create_engine(
        settings.database_url.get_secret_value(),
        pool_pre_ping=True,
        connect_args={"connect_timeout": 2, "options": "-c statement_timeout=2000"},
        hide_parameters=True,
    )


class DependencyChecks:
    def __init__(self, settings: Settings) -> None:
        self.engine = build_engine(settings)
        self.sessions = sessionmaker(bind=self.engine, expire_on_commit=False)
        self.redis: Redis = Redis.from_url(
            settings.redis_url.get_secret_value(),
            socket_connect_timeout=2,
            socket_timeout=2,
        )

    def database(self) -> None:
        with self.engine.connect() as connection:
            connection.execute(text("SELECT 1"))

    def cache(self) -> None:
        if not self.redis.ping():
            raise ConnectionError("Redis ping failed")

    def close(self) -> None:
        self.redis.close()
        self.engine.dispose()
