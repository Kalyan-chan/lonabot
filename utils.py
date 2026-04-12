"""
Вспомогательные функции для бота
"""
import json
import re
import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple, Dict, Any
import aiofiles
from aiogram import Bot
from aiogram.types import Message, ChatMemberAdministrator, ChatMemberOwner, ChatPermissions
from aiogram.exceptions import TelegramBadRequest

from config import (
    DATA_DIR, BANS_FILE, MUTES_FILE, WELCOME_FILE, RULES_FILE, UPDATES_FILE,
    DEFAULT_ADMINS, DEFAULT_WELCOME_TEXT, DEFAULT_WELCOME_PHOTO, DEFAULT_RULES, MAPS_FILE
)

logger = logging.getLogger(__name__)


# ============== Блокировки для файлов ==============

_file_locks: Dict[str, asyncio.Lock] = {}


def _get_file_lock(filepath: Path) -> asyncio.Lock:
    key = str(filepath)
    if key not in _file_locks:
        _file_locks[key] = asyncio.Lock()
    return _file_locks[key]


# ============== Инициализация ==============

def init_data_files():
    """Создание директории и файлов данных при первом запуске"""
    DATA_DIR.mkdir(exist_ok=True)

    if not BANS_FILE.exists():
        _save_json_sync(BANS_FILE, {"chats": {}})

    if not MUTES_FILE.exists():
        _save_json_sync(MUTES_FILE, {"chats": {}})

    if not WELCOME_FILE.exists():
        _save_json_sync(WELCOME_FILE, {
            "chats": {},
            "default_text": DEFAULT_WELCOME_TEXT,
            "default_photo": DEFAULT_WELCOME_PHOTO
        })

    if not RULES_FILE.exists():
        _save_json_sync(RULES_FILE, {
            "chats": {},
            "default": DEFAULT_RULES
        })

    if not UPDATES_FILE.exists():
        _save_json_sync(UPDATES_FILE, {
            "enabled": False,
            "last_version": None,
            "last_check": None
        })


# ============== Работа с JSON ==============

def _save_json_sync(filepath: Path, data: Dict[str, Any]):
    """Синхронная запись — только для init при старте бота."""
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_json(filepath: Path) -> Dict[str, Any]:
    """
    Синхронная читалка — используется только в init_data_files
    и в местах, где async недоступен (например, синхронные вспомогательные функции).
    Для всего остального используй load_json_async.
    """
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


async def load_json_async(filepath: Path) -> Dict[str, Any]:
    """Асинхронное чтение JSON с блокировкой на файл."""
    lock = _get_file_lock(filepath)
    async with lock:
        try:
            async with aiofiles.open(filepath, "r", encoding="utf-8") as f:
                content = await f.read()
            return json.loads(content)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}


async def save_json_async(filepath: Path, data: Dict[str, Any]):
    """Асинхронная запись JSON с блокировкой на файл."""
    lock = _get_file_lock(filepath)
    async with lock:
        async with aiofiles.open(filepath, "w", encoding="utf-8") as f:
            await f.write(json.dumps(data, ensure_ascii=False, indent=2))


# ============== Общая вспомогательная функция ответа ==============

async def reply_in_topic(message: Message, text: str, **kwargs):
    """Универсальная функция ответа с HTML parse_mode."""
    from aiogram.enums import ParseMode
    kwargs.pop("parse_mode", None)
    await message.answer(text, parse_mode=ParseMode.HTML, **kwargs)


# ============== Проверка прав ==============

async def is_user_admin(bot: Bot, chat_id: int, user_id: int) -> bool:
    if user_id in DEFAULT_ADMINS:
        return True
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        return isinstance(member, (ChatMemberAdministrator, ChatMemberOwner))
    except TelegramBadRequest:
        return False


async def bot_has_ban_rights(bot: Bot, chat_id: int) -> bool:
    try:
        bot_member = await bot.get_chat_member(chat_id, bot.id)
        if isinstance(bot_member, ChatMemberAdministrator):
            return bot_member.can_restrict_members
        return isinstance(bot_member, ChatMemberOwner)
    except TelegramBadRequest:
        return False


async def bot_has_mute_rights(bot: Bot, chat_id: int) -> bool:
    return await bot_has_ban_rights(bot, chat_id)


async def is_target_admin(bot: Bot, chat_id: int, user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        return isinstance(member, (ChatMemberAdministrator, ChatMemberOwner))
    except TelegramBadRequest:
        return False


# ============== Парсинг пользователя ==============

async def parse_user_target(bot: Bot, message: Message, args: str) -> Optional[Tuple[int, str]]:
    """
    Определяет целевого пользователя из:
    1. reply на сообщение
    2. text_mention entity (упоминание без @, у пользователей без username)
    3. числового user_id в аргументах
    """
    # 1. Reply
    if message.reply_to_message:
        user = message.reply_to_message.from_user
        if user:
            return user.id, user.full_name

    if not args:
        return None

    parts = args.split()
    if not parts:
        return None

    target = parts[0]

    # 2. text_mention entity — упоминание пользователя без username
    #    (type="mention" с @ резолвить через Telegram API нельзя напрямую)
    if target.startswith("@"):
        if message.entities:
            for entity in message.entities:
                if entity.type == "text_mention" and entity.user:
                    return entity.user.id, entity.user.full_name
        # @username без text_mention — резолвинг недоступен через Bot API
        logger.debug("Получен @username без text_mention entity, резолвинг недоступен")
        return None

    # 3. Числовой user_id
    if target.lstrip("-").isdigit():
        user_id = int(target)
        try:
            chat_member = await bot.get_chat_member(message.chat.id, user_id)
            if chat_member.user:
                return user_id, chat_member.user.full_name
        except TelegramBadRequest:
            return None

    return None


def extract_args_without_user(args: str) -> str:
    if not args:
        return ""

    parts = args.split(maxsplit=1)
    if len(parts) < 2:
        return ""

    first = parts[0]
    if first.startswith("@") or first.lstrip("-").isdigit() or "t.me/" in first:
        return parts[1]

    return args


# ============== Парсинг времени ==============

def parse_duration(text: str) -> Optional[int]:
    text = text.lower().strip()

    patterns = [
        (r"(\d+)\s*(?:час(?:а|ов)?|ч\b)", 3600),
        (r"(\d+)\s*(?:минут(?:а|ы|у)?|мин\b|м\b)", 60),
    ]

    total_seconds = 0
    found = False

    for pattern, multiplier in patterns:
        matches = re.findall(pattern, text)
        for match in matches:
            total_seconds += int(match) * multiplier
            found = True

    return total_seconds if found else None


def format_duration(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds} секунд"

    hours = seconds // 3600
    minutes = (seconds % 3600) // 60

    parts = []
    if hours > 0:
        parts.append(f"{hours} {pluralize(hours, 'час', 'часа', 'часов')}")
    if minutes > 0:
        parts.append(f"{minutes} {pluralize(minutes, 'минуту', 'минуты', 'минут')}")

    return " ".join(parts)


def format_remaining_time(end_timestamp: float) -> str:
    remaining = int(end_timestamp - datetime.now().timestamp())
    if remaining <= 0:
        return "истекло"
    return format_duration(remaining)


def pluralize(n: int, form1: str, form2: str, form5: str) -> str:
    n = abs(n) % 100
    n1 = n % 10

    if 10 < n < 20:
        return form5
    if 1 < n1 < 5:
        return form2
    if n1 == 1:
        return form1
    return form5


# ============== Управление банами ==============

async def add_ban(chat_id: int, user_id: int, user_name: str):
    data = await load_json_async(BANS_FILE)
    chat_key = str(chat_id)
    data.setdefault("chats", {}).setdefault(chat_key, {})
    data["chats"][chat_key][str(user_id)] = {
        "name": user_name,
        "banned_at": datetime.now().isoformat()
    }
    await save_json_async(BANS_FILE, data)


async def get_ban_list(chat_id: int) -> Dict[str, Dict]:
    data = await load_json_async(BANS_FILE)
    return data.get("chats", {}).get(str(chat_id), {})


async def remove_ban(chat_id: int, user_id: int):
    data = await load_json_async(BANS_FILE)
    chat_key = str(chat_id)
    if chat_key in data.get("chats", {}) and str(user_id) in data["chats"][chat_key]:
        del data["chats"][chat_key][str(user_id)]
        await save_json_async(BANS_FILE, data)


# ============== Управление мутами ==============

async def add_mute(chat_id: int, user_id: int, user_name: str, duration_seconds: int):
    data = await load_json_async(MUTES_FILE)
    chat_key = str(chat_id)
    data.setdefault("chats", {}).setdefault(chat_key, {})
    end_time = datetime.now().timestamp() + duration_seconds
    data["chats"][chat_key][str(user_id)] = {
        "name": user_name,
        "end_time": end_time,
        "muted_at": datetime.now().isoformat()
    }
    await save_json_async(MUTES_FILE, data)


async def remove_mute(chat_id: int, user_id: int):
    data = await load_json_async(MUTES_FILE)
    chat_key = str(chat_id)
    if chat_key in data.get("chats", {}) and str(user_id) in data["chats"][chat_key]:
        del data["chats"][chat_key][str(user_id)]
        await save_json_async(MUTES_FILE, data)


async def get_mute_list(chat_id: int) -> Dict[str, Dict]:
    data = await load_json_async(MUTES_FILE)
    return data.get("chats", {}).get(str(chat_id), {})


async def get_all_mutes() -> Dict[str, Dict]:
    data = await load_json_async(MUTES_FILE)
    return data.get("chats", {})


async def cleanup_expired_mutes():
    data = await load_json_async(MUTES_FILE)
    now = datetime.now().timestamp()
    changed = False

    for chat_id, users in data.get("chats", {}).items():
        expired = [uid for uid, info in users.items() if info.get("end_time", 0) <= now]
        for uid in expired:
            del users[uid]
            changed = True

    if changed:
        await save_json_async(MUTES_FILE, data)


# ============== Управление приветствиями ==============

async def get_welcome(chat_id: int) -> Tuple[str, str]:
    data = await load_json_async(WELCOME_FILE)
    chat_data = data.get("chats", {}).get(str(chat_id), {})
    text = chat_data.get("text", data.get("default_text", DEFAULT_WELCOME_TEXT))
    photo = chat_data.get("photo", data.get("default_photo", DEFAULT_WELCOME_PHOTO))
    return text, photo


async def set_welcome_text(chat_id: int, text: str):
    data = await load_json_async(WELCOME_FILE)
    data.setdefault("chats", {}).setdefault(str(chat_id), {})["text"] = text
    await save_json_async(WELCOME_FILE, data)


async def set_welcome_photo(chat_id: int, photo_url: str):
    data = await load_json_async(WELCOME_FILE)
    data.setdefault("chats", {}).setdefault(str(chat_id), {})["photo"] = photo_url
    await save_json_async(WELCOME_FILE, data)


def is_valid_image_url(url: str) -> bool:
    from urllib.parse import urlparse
    try:
        parsed = urlparse(url.strip())
        if parsed.scheme not in ("http", "https"):
            return False
        return parsed.path.lower().endswith((".png", ".jpg", ".jpeg"))
    except Exception:
        return False


# ============== Управление правилами ==============

async def get_rules(chat_id: int) -> str:
    data = await load_json_async(RULES_FILE)
    return data.get("chats", {}).get(str(chat_id), data.get("default", DEFAULT_RULES))


async def set_rules(chat_id: int, text: str):
    data = await load_json_async(RULES_FILE)
    data.setdefault("chats", {})[str(chat_id)] = text
    await save_json_async(RULES_FILE, data)


# ============== Планировщик автоматического размута ==============

class MuteScheduler:
    def __init__(self, bot: Bot):
        self.bot = bot
        self._running = False
        self._task: Optional[asyncio.Task] = None

    async def start(self):
        self._running = True
        self._task = asyncio.create_task(self._check_mutes_loop())

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _check_mutes_loop(self):
        while self._running:
            try:
                await self._process_expired_mutes()
            except Exception as e:
                logger.error("Ошибка при проверке мутов: %s", e)
            await asyncio.sleep(30)

    async def _process_expired_mutes(self):
        now = datetime.now().timestamp()
        all_mutes = await get_all_mutes()

        for chat_id, users in all_mutes.items():
            for user_id, info in list(users.items()):
                if info.get("end_time", 0) <= now:
                    try:
                        await self.bot.restrict_chat_member(
                            chat_id=int(chat_id),
                            user_id=int(user_id),
                            permissions=ChatPermissions(
                                can_send_messages=True,
                                can_send_audios=True,
                                can_send_documents=True,
                                can_send_photos=True,
                                can_send_videos=True,
                                can_send_video_notes=True,
                                can_send_voice_notes=True,
                                can_send_polls=True,
                                can_send_other_messages=True,
                                can_add_web_page_previews=True,
                                can_change_info=False,
                                can_invite_users=True,
                                can_pin_messages=False,
                                can_manage_topics=False
                            )
                        )
                    except Exception as e:
                        logger.error("Ошибка при размуте %s в чате %s: %s", user_id, chat_id, e)
                    finally:
                        await remove_mute(int(chat_id), int(user_id))