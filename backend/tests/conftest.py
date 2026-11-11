import os
import tempfile

os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="reality-test-")

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import delete

from app.db import Base, Session


@pytest.fixture(scope="session", autouse=True)
def migrate():
    command.upgrade(Config("alembic.ini"), "head")


@pytest.fixture(autouse=True)
def clean(migrate):
    with Session.begin() as db:
        for table in reversed(Base.metadata.sorted_tables):
            db.execute(delete(table))
