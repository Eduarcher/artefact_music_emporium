import os

import pytest

from emporium.config import PROJECT_ROOT

RAW_DATA_DIR = PROJECT_ROOT / "data" / "raw"

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://emporium:emporium@localhost:5433/emporium_test",
)
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")


@pytest.fixture
async def engine():
    from emporium.db.engine import create_engine
    from emporium.db.init_db import init_db

    eng = create_engine(TEST_DATABASE_URL)
    await init_db(eng)
    yield eng
    await eng.dispose()


@pytest.fixture
async def session_factory(engine):
    from emporium.db.engine import create_session_factory

    return create_session_factory(engine)


@pytest.fixture
def embedder():
    from langchain_ollama import OllamaEmbeddings

    return OllamaEmbeddings(model="bge-m3", base_url=OLLAMA_BASE_URL)
