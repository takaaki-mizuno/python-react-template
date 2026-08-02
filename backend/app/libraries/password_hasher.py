import asyncio
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import TypeVar

from pwdlib import PasswordHash

password_hash = PasswordHash.recommended()
T = TypeVar("T")


def validate_password_policy(raw_password: str) -> tuple[bool, str | None]:
    if len(raw_password) < 12:
        return False, "Password must be at least 12 characters long"
    if len(raw_password) > 128:
        return False, "Password must be 128 characters or fewer"
    return True, None


def hash_password(raw_password: str) -> str:
    return password_hash.hash(raw_password)


def verify_password(raw_password: str, hashed_password: str) -> bool:
    return password_hash.verify(raw_password, hashed_password)


class PasswordHashExecutor:

    def __init__(self, max_workers: int) -> None:
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="password-hash",
        )

    async def hash(self, raw_password: str) -> str:
        return await self._run(hash_password, raw_password)

    async def verify(self, raw_password: str, hashed_password: str) -> bool:
        return await self._run(verify_password, raw_password, hashed_password)

    async def _run(self, func: Callable[..., T], *args: object) -> T:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._executor, func, *args)

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)
