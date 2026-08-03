import asyncio
import threading
import time

import pytest

from app.libraries import password_hasher as password_hasher_module
from app.libraries.password_hasher import (PasswordHashExecutor, hash_password,
                                           validate_password_policy, verify_password)


def test_password_hash_round_trip():
    hashed_password = hash_password("Password123!")

    assert verify_password("Password123!", hashed_password) is True


def test_password_policy_rejects_short_password():
    is_valid, message = validate_password_policy("short")

    assert is_valid is False
    assert message == "Password must be at least 12 characters long"


@pytest.mark.asyncio
async def test_password_hash_executor_runs_hash_and_verify_in_worker_thread(monkeypatch):
    calls: list[tuple[str, str]] = []
    main_thread_name = threading.current_thread().name

    def tracked_hash(raw_password: str) -> str:
        calls.append(("hash", threading.current_thread().name))
        return f"hashed:{raw_password}"

    def tracked_verify(raw_password: str, hashed_password: str) -> bool:
        calls.append(("verify", threading.current_thread().name))
        return hashed_password == f"hashed:{raw_password}"

    monkeypatch.setattr(password_hasher_module, "hash_password", tracked_hash)
    monkeypatch.setattr(password_hasher_module, "verify_password", tracked_verify)
    executor = PasswordHashExecutor(max_workers=1)
    try:
        hashed_password = await executor.hash("Password123!")

        assert await executor.verify("Password123!", hashed_password) is True
        assert await executor.verify("wrong-password", hashed_password) is False
    finally:
        executor.shutdown()
    assert calls == [
        ("hash", "password-hash_0"),
        ("verify", "password-hash_0"),
        ("verify", "password-hash_0"),
    ]
    assert all(thread_name != main_thread_name for _, thread_name in calls)


@pytest.mark.asyncio
async def test_password_hash_executor_queues_work_instead_of_failing(monkeypatch):
    calls = []

    def slow_hash(raw_password: str) -> str:
        calls.append(raw_password)
        time.sleep(0.01)
        return f"hashed:{raw_password}"

    monkeypatch.setattr(password_hasher_module, "hash_password", slow_hash)
    executor = PasswordHashExecutor(max_workers=1)
    try:
        results = await asyncio.gather(
            executor.hash("first-password"),
            executor.hash("second-password"),
        )
    finally:
        executor.shutdown()

    assert results == ["hashed:first-password", "hashed:second-password"]
    assert calls == ["first-password", "second-password"]


def test_password_hash_executor_shutdown_closes_executor():
    executor = PasswordHashExecutor(max_workers=1)

    executor.shutdown()

    assert executor._executor._shutdown is True
