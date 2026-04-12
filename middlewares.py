"""
Middleware для бота
"""
import time
import asyncio
import logging
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import Message

logger = logging.getLogger(__name__)


class RateLimitMiddleware(BaseMiddleware):
    def __init__(self, rate_limit: float = 2.0):
        """
        :param rate_limit: минимальный интервал между сообщениями в секундах
        """
        self.rate_limit = rate_limit
        # {user_id: last_message_timestamp}
        self._last_message: Dict[int, float] = {}
        self._lock = asyncio.Lock()

    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: Dict[str, Any]
    ) -> Any:
        user = event.from_user
        if user is None:
            return await handler(event, data)

        user_id = user.id
        now = time.monotonic()

        async with self._lock:
            last = self._last_message.get(user_id, 0.0)
            delta = now - last

            if delta < self.rate_limit:
                logger.debug(
                    "Rate limit: user_id=%s, delta=%.2fs < %.2fs",
                    user_id, delta, self.rate_limit
                )
                return  # молча игнорируем

            self._last_message[user_id] = now

        return await handler(event, data)