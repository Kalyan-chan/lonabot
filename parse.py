"""
Парсинг обновлений и онлайна LonaRPG
"""
import re
import asyncio
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List

import aiohttp
from lxml import html as lxml_html

from aiogram import Bot, Router, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.enums import ParseMode, ChatType

from config import (
    DEFAULT_ADMINS, UPDATES_FILE, UPDATES_CHECK_INTERVAL,
    UPDATES_CHAT_ID, UPDATES_THREAD_ID, UPDATES_URL,
    VERSION_JSON_URL, ONLINE_API_URL, LAUNCHER_URL, MAPS_FILE
)
from utils import (
    load_json_async, save_json_async,
    is_user_admin, pluralize, reply_in_topic
)

logger = logging.getLogger(__name__)

parse_router = Router()
parse_router.message.filter(F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}))


# ============== Кэш онлайна ==============

_online_cache: Dict[str, Any] = {
    "data": None,
    "timestamp": 0.0
}
ONLINE_CACHE_TTL = 15


# ============== Кэш карт локаций ==============

_maps_cache: Dict[str, str] = {}
_maps_cache_timestamp: float = 0.0
MAPS_CACHE_TTL = 3600  # 1 час


async def load_maps_cache():
    """Загружает карты локаций в кэш"""
    global _maps_cache, _maps_cache_timestamp

    now = datetime.now().timestamp()

    # Проверяем, нужно ли обновить кэш
    if _maps_cache and (now - _maps_cache_timestamp) < MAPS_CACHE_TTL:
        return

    try:
        data = await load_json_async(MAPS_FILE)
        _maps_cache = data
        _maps_cache_timestamp = now
        logger.debug("Карты локаций загружены в кэш")
    except Exception as e:
        logger.error("Ошибка загрузки карт: %s", e)


def get_map_name(map_id: int) -> str:
    """
    Возвращает название локации по map_id из кэша.
    Кэш должен быть предварительно загружен через load_maps_cache().
    """
    return _maps_cache.get(str(map_id), f"Локация #{map_id}")


# ============== Работа с настройками обновлений ==============

async def get_updates_settings() -> Dict[str, Any]:
    return await load_json_async(UPDATES_FILE)


async def set_updates_enabled(enabled: bool):
    data = await load_json_async(UPDATES_FILE)
    data["enabled"] = enabled
    await save_json_async(UPDATES_FILE, data)


async def save_last_version(version: str):
    data = await load_json_async(UPDATES_FILE)
    data["last_version"] = version
    data["last_check"] = datetime.now().isoformat()
    await save_json_async(UPDATES_FILE, data)


def format_last_check(last_check_str: Optional[str]) -> str:
    if not last_check_str or last_check_str == "никогда":
        return "никогда"

    try:
        dt = datetime.fromisoformat(last_check_str.replace("Z", "+00:00"))
        now = datetime.now()
        delta_seconds = int((now - dt).total_seconds())

        if delta_seconds < 60:
            return f"{delta_seconds} секунд назад"
        elif delta_seconds < 3600:
            minutes = delta_seconds // 60
            return f"{minutes} {pluralize(minutes, 'минуту', 'минуты', 'минут')} назад"
        elif delta_seconds < 86400:
            hours = delta_seconds // 3600
            return f"{hours} {pluralize(hours, 'час', 'часа', 'часов')} назад"
        else:
            days = delta_seconds // 86400
            return f"{days} {pluralize(days, 'день', 'дня', 'дней')} назад"
    except Exception:
        return last_check_str


# ============== Получение онлайна с кэшированием ==============

async def fetch_online_data() -> Optional[Dict[str, Any]]:
    global _online_cache

    now = datetime.now().timestamp()

    if (
        _online_cache["data"] is not None
        and (now - _online_cache["timestamp"]) < ONLINE_CACHE_TTL
    ):
        return _online_cache["data"]

    timeout = aiohttp.ClientTimeout(total=10, connect=5)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(ONLINE_API_URL) as response:
                if response.status == 200:
                    data = await response.json()
                    _online_cache["data"] = data
                    _online_cache["timestamp"] = now
                    return data
    except Exception as e:
        logger.error("Ошибка получения онлайна: %s", e)

    return _online_cache["data"]


# ============== Планировщик проверки обновлений ==============

class UpdateChecker:
    def __init__(self, bot: Bot):
        self.bot = bot
        self._running = False
        self._task: Optional[asyncio.Task] = None

    async def start(self):
        self._running = True
        self._task = asyncio.create_task(self._check_updates_loop())

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _check_updates_loop(self):
        while self._running:
            try:
                settings = await get_updates_settings()
                if settings.get("enabled", False):
                    await self._check_for_updates()
            except Exception as e:
                logger.error("Ошибка при проверке обновлений: %s", e)
            await asyncio.sleep(UPDATES_CHECK_INTERVAL)

    async def _fetch_version_info(self) -> Optional[Dict[str, Any]]:
        timeout = aiohttp.ClientTimeout(total=10, connect=5)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(VERSION_JSON_URL) as response:
                    if response.status == 200:
                        return await response.json()
        except Exception as e:
            logger.error("Ошибка получения version.json: %s", e)
        return None

    async def _fetch_patch_content(self) -> str:
        timeout = aiohttp.ClientTimeout(total=30, connect=5)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                headers = {"User-Agent": "LonaRPG-Bot/1.0"}
                async with session.get(UPDATES_URL, headers=headers) as response:
                    if response.status != 200:
                        return ""
                    page_content = await response.text()

            tree = lxml_html.fromstring(page_content)
            return self._extract_patch_content(tree)
        except Exception as e:
            logger.error("Ошибка получения описания патча: %s", e)
        return ""

    def _clean_text(self, text: str) -> str:
        if not text:
            return ""
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    def _extract_patch_content(self, tree) -> str:
        content_parts = []

        patch_headers = tree.xpath("//h2[contains(text(), '✨') and contains(text(), 'Патч')]")
        if not patch_headers:
            patch_headers = tree.xpath("//h2[contains(text(), 'Патч LonaRPG')]")

        if not patch_headers:
            return ""

        patch_h2 = patch_headers[0]
        header_text = self._clean_text(patch_h2.text_content())
        content_parts.append(f"<b>{header_text}</b>")

        current = patch_h2.getnext()
        while current is not None:
            if current.tag == "hr":
                break
            if current.tag == "h2" and (
                "🧾" in current.text_content()
                or "прошлых версиях" in current.text_content().lower()
            ):
                break

            if current.tag == "h3":
                text = self._clean_text(current.text_content())
                if "📅" in text:
                    content_parts.append(f"\n{text}")
                else:
                    content_parts.append(f"\n\n<b>{text}</b>")

            elif current.tag == "p":
                text = self._clean_text(current.text_content())
                if text:
                    content_parts.append(f"\n{text}")

            elif current.tag == "ul":
                items = current.xpath(".//li")
                for item in items[:3]:
                    item_text = self._clean_text(item.text_content())
                    if item_text:
                        content_parts.append(f"\n• {item_text}")
                if len(items) > 3:
                    content_parts.append(f"\n<i>...и ещё {len(items) - 3}</i>")

            elif current.tag == "div" and "warning-box" in current.get("class", ""):
                text = self._clean_text(current.text_content())
                if "🔥 Итог" in text:
                    content_parts.append(f"\n\n{text}")

            current = current.getnext()

        return "\n".join(content_parts) if content_parts else ""

    async def _check_for_updates(self):
        version_info = await self._fetch_version_info()
        if not version_info:
            logger.warning("Не удалось получить version.json")
            return

        current_version = version_info.get("version")
        download_url = version_info.get("download_url", "")

        if not current_version:
            logger.warning("Не удалось определить версию")
            return

        settings = await get_updates_settings()
        last_version = settings.get("last_version")

        logger.info("Проверка обновлений: текущая=%s, последняя=%s", current_version, last_version)

        if last_version is not None and current_version != last_version:
            patch_content = await self._fetch_patch_content()
            await self._send_update_notification(current_version, download_url, patch_content)

        await save_last_version(current_version)

    async def _send_update_notification(self, version: str, download_url: str, content: str = ""):
        header = f"🎮 <b>Вышло обновление LonaRPG Online!</b>\n"
        header += f"📦 <b>Версия:</b> {version}\n"
        footer = f"\n\n🔗 <a href='{UPDATES_URL}'>Подробнее на сайте</a>"

        full_message = header + "\n" + content + footer if content else header + footer

        if len(full_message) > 4000:
            full_message = header + footer

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📥 Скачать",
                    url=download_url if download_url else UPDATES_URL
                ),
                InlineKeyboardButton(text="🚀 Лаунчер", url=LAUNCHER_URL)
            ]
        ])

        try:
            await self.bot.send_message(
                chat_id=UPDATES_CHAT_ID,
                message_thread_id=UPDATES_THREAD_ID,
                text=full_message,
                parse_mode=ParseMode.HTML,
                reply_markup=keyboard,
                disable_web_page_preview=True
            )
            logger.info("Уведомление об обновлении отправлено: %s", version)
        except Exception as e:
            logger.error("Ошибка отправки уведомления: %s", e)

    async def force_check(self) -> str:
        try:
            settings = await get_updates_settings()
            old_version = settings.get("last_version", "не определена")

            await self._check_for_updates()

            settings = await get_updates_settings()
            new_version = settings.get("last_version", "не определена")

            return f"✅ Проверка завершена\nБыла: {old_version}\nСейчас: {new_version}"
        except Exception as e:
            return f"❌ Ошибка: {e}"


# ============== Хэндлеры управления обновлениями ==============

@parse_router.message(F.text.regexp(r"^\+обновы$", flags=re.IGNORECASE))
async def enable_updates_handler(message: Message, bot: Bot):
    if not await is_user_admin(bot, message.chat.id, message.from_user.id):
        return

    await set_updates_enabled(True)
    await reply_in_topic(message, "✅ Уведомления об обновлениях игры включены.")


@parse_router.message(F.text.regexp(r"^-обновы$", flags=re.IGNORECASE))
async def disable_updates_handler(message: Message, bot: Bot):
    if not await is_user_admin(bot, message.chat.id, message.from_user.id):
        return

    await set_updates_enabled(False)
    await reply_in_topic(message, "❌ Уведомления об обновлениях игры выключены.")


@parse_router.message(F.text.regexp(r"^обновы\??$", flags=re.IGNORECASE))
async def updates_status_handler(message: Message, bot: Bot):
    settings = await get_updates_settings()
    enabled = settings.get("enabled", False)
    last_check_raw = settings.get("last_check", "никогда")
    last_version = settings.get("last_version", "—")

    last_check = format_last_check(last_check_raw)
    status = "включены ✅" if enabled else "выключены ❌"

    text = (
        f"📊 <b>Статус:</b> {status}\n"
        f"📅 <b>Проверка:</b> {last_check}\n"
        f"🏷️ <b>Текущая версия:</b> {last_version}"
    )

    await reply_in_topic(message, text)


@parse_router.message(F.text.regexp(r"^!проверить$", flags=re.IGNORECASE))
async def force_check_handler(message: Message, bot: Bot):
    if message.from_user.id not in DEFAULT_ADMINS:
        return

    await reply_in_topic(message, "🔄 Проверяю обновления...")

    if hasattr(bot, "update_checker"):
        result = await bot.update_checker.force_check()
        await reply_in_topic(message, result)
    else:
        await reply_in_topic(message, "❌ Планировщик не инициализирован")


# ============== Хэндлер онлайна (ОПТИМИЗИРОВАННЫЙ) ==============

@parse_router.message(F.text.regexp(r"^(?:[!/]?)онлайн\??$", flags=re.IGNORECASE))
async def online_handler(message: Message, bot: Bot):
    # Загружаем карты в кэш перед обработкой
    await load_maps_cache()

    data = await fetch_online_data()

    if not data or not data.get("ok"):
        await reply_in_topic(message, "❌ Не удалось получить данные")
        return

    players: List[Dict[str, Any]] = data.get("players", [])

    if not players:
        text = "<b>🩸LonaRPG Online</b>\n\n<b>Онлайн:</b> 0\n\n<i>Нет игроков</i>"
        await reply_in_topic(message, text)
        return

    online_total = len(players)

    # Формируем список строк
    lines = [
        "<b>🩸LonaRPG Online</b>",
        f"<b>Онлайн:</b> {online_total}",
        ""
    ]

    # Формируем вывод используя кэшированные карты
    for player in players:
        nick = player.get("nick", "???")
        map_id = player.get("map_id")
        location = get_map_name(map_id) if map_id is not None else " "

        lines.append(f"• {nick}")
        lines.append(f"<code>{location}</code>")

    await reply_in_topic(message, "\n".join(lines))