import os
import tempfile
from collections.abc import AsyncIterator

import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


@pytest_asyncio.fixture
async def temp_db_url() -> AsyncIterator[str]:
    """Provides a fresh sqlite file URL per test, with the schema created."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    url = f"sqlite+aiosqlite:///{path}"
    os.environ["DB_URL"] = url

    # Recreate engine + tables under the temp URL.
    from importlib import reload
    from app import config as cfg, db as db_mod, models as models_mod  # noqa: F401
    reload(cfg)
    reload(db_mod)
    reload(models_mod)

    engine = create_async_engine(url)
    async with engine.begin() as conn:
        await conn.run_sync(db_mod.Base.metadata.create_all)
    await engine.dispose()

    yield url

    try:
        os.remove(path)
    except OSError:
        pass


@pytest_asyncio.fixture
async def session_maker(temp_db_url):
    from app import db as db_mod
    return db_mod.SessionLocal
