from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
import sys
from rodi import Container
from xcov19.infra.models import SQLModel
from sqlmodel import text
from xcov19.app.settings import Settings
from sqlmodel.ext.asyncio.session import AsyncSession as AsyncSessionWrapper
from sqlalchemy.ext.asyncio import (
    create_async_engine,
    AsyncEngine,
    async_sessionmaker,
)

import logging
from sqlalchemy.pool import AsyncAdaptedQueuePool

db_logger = logging.getLogger(__name__)
db_fmt = logging.Formatter(
    "DATABASE:%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
stream_handler = logging.StreamHandler(sys.stdout)
stream_handler.setFormatter(db_fmt)

db_logger.setLevel(logging.INFO)
db_logger.addHandler(stream_handler)


class SessionFactory:
    """Class to remember sessionmaker factory constructor for DI container.

    Use like this to retrieve sessionmaker from DI container:
    container.resolve(SessionFactory)

    It is already added as in `configure_database_session`:
    container.add_singleton_by_factory(SessionFactory(engine), SessionFactory)
    """

    def __init__(self, engine: AsyncEngine):
        self._engine = engine

    def __call__(self) -> async_sessionmaker[AsyncSessionWrapper]:
        return async_sessionmaker(
            self._engine, class_=AsyncSessionWrapper, expire_on_commit=False
        )


async def setup_database(engine: AsyncEngine) -> None:
    """Sets up tables for database."""
    async with engine.begin() as conn:
        # see: https://sqlmodel.tiangolo.com/tutorial/relationship-attributes/cascade-delete-relationships/#enable-foreign-key-support-in-sqlite
        await conn.execute(text("PRAGMA foreign_keys=ON"))
        await conn.run_sync(SQLModel.metadata.create_all)
        await conn.commit()
        db_logger.info("===== Database tables setup. =====")


@asynccontextmanager
async def start_db_session(
    container: Container,
) -> AsyncGenerator[AsyncSessionWrapper, None]:
    """Starts a new database session given SessionFactory."""
    # add LocalAsyncSession
    async_session_factory: async_sessionmaker[AsyncSessionWrapper] = container.resolve(
        async_sessionmaker[AsyncSessionWrapper]
    )
    async with async_session_factory() as local_async_session:
        yield local_async_session


def configure_database_session(container: Container, settings: Settings) -> Container:
    """Configure database session setup for the application."""
    # add engine
    db_logger.info(f"""====== Configuring database session. ======
                   DB_ENGINE_URL: {settings.db_engine_url}
                   """)
    engine = create_async_engine(
        settings.db_engine_url, echo=True, poolclass=AsyncAdaptedQueuePool
    )
    container.add_instance(engine, AsyncEngine)

    # add sessionmaker
    session_factory = SessionFactory(engine)
    container.add_singleton_by_factory(
        session_factory, async_sessionmaker[AsyncSessionWrapper]
    )

    db_logger.info("====== Database session configured. ======")
    return container
