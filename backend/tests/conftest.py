"""Shared isolated database and in-process HTTP test fixtures."""

import asyncio
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base, get_db, make_engine
from app.main import app
from app import models  # noqa: F401 - register all tables before create_all


class LocalApiClient:
    """Small synchronous wrapper around httpx's in-process ASGI transport."""

    def __init__(self, application: FastAPI) -> None:
        self.application = application

    def request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        async def send() -> httpx.Response:
            transport = httpx.ASGITransport(app=self.application)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://test"
            ) as client:
                return await client.request(method, path, **kwargs)

        return asyncio.run(send())

    def get(self, path: str, **kwargs: Any) -> httpx.Response:
        return self.request("GET", path, **kwargs)

    def post(self, path: str, **kwargs: Any) -> httpx.Response:
        return self.request("POST", path, **kwargs)

    def patch(self, path: str, **kwargs: Any) -> httpx.Response:
        return self.request("PATCH", path, **kwargs)

    def delete(self, path: str, **kwargs: Any) -> httpx.Response:
        return self.request("DELETE", path, **kwargs)


@pytest.fixture
def test_engine(tmp_path: Path):
    """Use one disposable SQLite file per test; never open the app database."""
    database_file = tmp_path / "isolated-test.db"
    engine = make_engine(f"sqlite:///{database_file.as_posix()}")
    Base.metadata.create_all(bind=engine)
    yield engine
    engine.dispose()


@pytest.fixture
def client(test_engine) -> Iterator[LocalApiClient]:
    test_session_factory = sessionmaker(
        bind=test_engine, autoflush=False, expire_on_commit=False
    )

    def get_test_db():
        session = test_session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = get_test_db
    yield LocalApiClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def db_session(test_engine) -> Iterator[Session]:
    with Session(test_engine, autoflush=False, expire_on_commit=False) as session:
        yield session
