"""
Вспомогательные функции для бота
"""
import json
import re
import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Tuple, Dict, Any, List

import aiohttp
from lxml import html as lxml_html

from aiogram import Bot
from aiogram.types import Message, ChatMemberAdministrator, ChatMemberOwner
from aiogram.exceptions import TelegramBadRequest

from config import (
    DATA_DIR, BANS_FILE, MUTES_FILE, WELCOME_FILE, RULES_FILE,
    DEFAULT_ADMINS, DEFAULT_WELCOME_TEXT, DEFAULT_WELCOME_PHOTO, DEFAULT_RULES,
    UPDATES_FILE, UPDATES_CHECK_INTERVAL, UPDATES_CHAT_ID, UPDATES_THREAD_ID,
    UPDATES_URL
)


# ============== Инициализация ==============

def init_data_files():
    """Создание директории и файлов данных при первом запуске"""
    DATA_DIR.mkdir(exist_ok=True)

    if not BANS_FILE.exists():
        save_json(BANS_FILE, {"chats": {}})

    if not MUTES_FILE.exists():
        save_json(MUTES_FILE, {"chats": {}})

    if not WELCOME_FILE.exists():
        save_json(WELCOME_FILE, {
            "chats": {},
            "default_text": DEFAULT_WELCOME_TEXT,
            "default_photo": DEFAULT_WELCOME_PHOTO
        })

    if not RULES_FILE.exists():
        save_json(RULES_FILE, {
            "chats": {},
            "default": DEFAULT_RULES
        })

    if not UPDATES_FILE.exists():
        save_json(UPDATES_FILE, {
            "enabled": False,
            "last_version": None,
            "last_check": None
        })


# ============== Работа с JSON ==============

def load_json(filepath: Path) -> Dict[str, Any]:
    """Загрузка данных из JSON файла"""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_json(filepath: Path, data: Dict[str, Any]):
    """Сохранение данных в JSON файл"""
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ============== Проверка прав ==============

async def is_user_admin(bot: Bot, chat_id: int, user_id: int) -> bool:
    """Проверка, является ли пользователь администратором чата"""
    if user_id in DEFAULT_ADMINS:
        return True

    try:
        member = await bot.get_chat_member(chat_id, user_id)
        return isinstance(member, (ChatMemberAdministrator, ChatMemberOwner))
    except TelegramBadRequest:
        return False


async def bot_has_ban_rights(bot: Bot, chat_id: int) -> bool:
    """Проверка, есть ли у бота права на бан"""
    try:
        bot_member = await bot.get_chat_member(chat_id, bot.id)
        if isinstance(bot_member, ChatMemberAdministrator):
            return bot_member.can_restrict_members
        return isinstance(bot_member, ChatMemberOwner)
    except TelegramBadRequest:
        return False


async def bot_has_mute_rights(bot: Bot, chat_id: int) -> bool:
    """Проверка, есть ли у бота права на мут"""
    return await bot_has_ban_rights(bot, chat_id)


async def is_target_admin(bot: Bot, chat_id: int, user_id: int) -> bool:
    """Проверка, является ли целевой пользователь администратором"""
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        return isinstance(member, (ChatMemberAdministrator, ChatMemberOwner))
    except TelegramBadRequest:
        return False


# ============== Парсинг пользователя ==============

async def parse_user_target(bot: Bot, message: Message, args: str) -> Optional[Tuple[int, str]]:
    """
    Парсинг целевого пользователя из сообщения.
    Возвращает (user_id, user_name) или None.
    """
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

    if target.isdigit():
        user_id = int(target)
        try:
            chat_member = await bot.get_chat_member(message.chat.id, user_id)
            if chat_member.user:
                return user_id, chat_member.user.full_name
        except TelegramBadRequest:
            return None

    if target.startswith("@"):
        if message.entities:
            for entity in message.entities:
                if entity.type == "text_mention" and entity.user:
                    return entity.user.id, entity.user.full_name
        return None

    tme_pattern = r"(?:https?://)?t\.me/(\w+)"
    match = re.match(tme_pattern, target)
    if match:
        return None

    return None


def extract_args_without_user(args: str) -> str:
    """Извлечение аргументов без упоминания пользователя"""
    if not args:
        return ""

    parts = args.split(maxsplit=1)
    if len(parts) < 2:
        return ""

    first = parts[0]
    if first.startswith("@") or first.isdigit() or "t.me/" in first:
        return parts[1] if len(parts) > 1 else ""

    return args


# ============== Парсинг времени ==============

def parse_duration(text: str) -> Optional[int]:
    """
    Парсинг длительности из текста.
    Возвращает количество секунд или None.
    """
    text = text.lower().strip()

    patterns = [
        (r"(\d+)\s*(?:час(?:а|ов)?|ч)", 3600),
        (r"(\d+)\s*(?:минут(?:а|ы|у)?|мин|м)", 60),
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
    """Форматирование длительности в читаемый вид"""
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
    """Форматирование оставшегося времени"""
    remaining = int(end_timestamp - datetime.now().timestamp())
    if remaining <= 0:
        return "истекло"
    return format_duration(remaining)


def pluralize(n: int, form1: str, form2: str, form5: str) -> str:
    """Склонение слов в зависимости от числа"""
    n = abs(n) % 100
    n1 = n % 10

    if 10 < n < 20:
        return form5
    if 1 < n1 < 5:
        return form2
    if n1 == 1:
        return form1
    return form5

def format_last_check(last_check_str: Optional[str]) -> str:
    """Форматирует время последней проверки в виде '15 минут назад'"""
    if not last_check_str or last_check_str == "никогда":
        return "никогда"

    try:
        dt = datetime.fromisoformat(last_check_str.replace("Z", "+00:00"))  # на всякий случай
        now = datetime.now()
        delta_seconds = int((now - dt).total_seconds())

        if delta_seconds < 60:
            return f"{delta_seconds} секунд назад"

        elif delta_seconds < 3600:
            minutes = delta_seconds // 60
            return f"{minutes} {pluralize(minutes, 'минуту', 'минуты', 'минут')} назад"

        elif delta_seconds < 86400:  # меньше суток
            hours = delta_seconds // 3600
            return f"{hours} {pluralize(hours, 'час', 'часа', 'часов')} назад"

        else:
            days = delta_seconds // 86400
            return f"{days} {pluralize(days, 'день', 'дня', 'дней')} назад"

    except Exception:
        return last_check_str  # если вдруг ошибка — показываем как было

# ============== Управление банами ==============

def add_ban(chat_id: int, user_id: int, user_name: str):
    """Добавление пользователя в список забаненных"""
    data = load_json(BANS_FILE)
    chat_key = str(chat_id)

    if chat_key not in data.get("chats", {}):
        data.setdefault("chats", {})[chat_key] = {}

    data["chats"][chat_key][str(user_id)] = {
        "name": user_name,
        "banned_at": datetime.now().isoformat()
    }

    save_json(BANS_FILE, data)


def get_ban_list(chat_id: int) -> Dict[str, Dict]:
    """Получение списка забаненных пользователей чата"""
    data = load_json(BANS_FILE)
    return data.get("chats", {}).get(str(chat_id), {})


def remove_ban(chat_id: int, user_id: int):
    """Удаление пользователя из списка забаненных"""
    data = load_json(BANS_FILE)
    chat_key = str(chat_id)
    if chat_key in data.get("chats", {}) and str(user_id) in data["chats"][chat_key]:
        del data["chats"][chat_key][str(user_id)]
        save_json(BANS_FILE, data)


# ============== Управление мутами ==============

def add_mute(chat_id: int, user_id: int, user_name: str, duration_seconds: int):
    """Добавление пользователя в список замученных"""
    data = load_json(MUTES_FILE)
    chat_key = str(chat_id)

    if chat_key not in data.get("chats", {}):
        data.setdefault("chats", {})[chat_key] = {}

    end_time = datetime.now().timestamp() + duration_seconds

    data["chats"][chat_key][str(user_id)] = {
        "name": user_name,
        "end_time": end_time,
        "muted_at": datetime.now().isoformat()
    }

    save_json(MUTES_FILE, data)


def remove_mute(chat_id: int, user_id: int):
    """Удаление пользователя из списка замученных"""
    data = load_json(MUTES_FILE)
    chat_key = str(chat_id)

    if chat_key in data.get("chats", {}) and str(user_id) in data["chats"][chat_key]:
        del data["chats"][chat_key][str(user_id)]
        save_json(MUTES_FILE, data)


def get_mute_list(chat_id: int) -> Dict[str, Dict]:
    """Получение списка замученных пользователей чата"""
    data = load_json(MUTES_FILE)
    return data.get("chats", {}).get(str(chat_id), {})


def get_all_mutes() -> Dict[str, Dict]:
    """Получение всех мутов для всех чатов"""
    data = load_json(MUTES_FILE)
    return data.get("chats", {})


def cleanup_expired_mutes():
    """Очистка истекших мутов из файла"""
    data = load_json(MUTES_FILE)
    now = datetime.now().timestamp()
    changed = False

    for chat_id, users in data.get("chats", {}).items():
        expired = [uid for uid, info in users.items() if info.get("end_time", 0) <= now]
        for uid in expired:
            del users[uid]
            changed = True

    if changed:
        save_json(MUTES_FILE, data)


# ============== Управление приветствиями ==============

def get_welcome(chat_id: int) -> Tuple[str, str]:
    """Получение приветствия для чата (текст, фото)"""
    data = load_json(WELCOME_FILE)
    chat_data = data.get("chats", {}).get(str(chat_id), {})

    text = chat_data.get("text", data.get("default_text", DEFAULT_WELCOME_TEXT))
    photo = chat_data.get("photo", data.get("default_photo", DEFAULT_WELCOME_PHOTO))

    return text, photo


def set_welcome_text(chat_id: int, text: str):
    """Установка текста приветствия для чата"""
    data = load_json(WELCOME_FILE)
    chat_key = str(chat_id)

    if chat_key not in data.get("chats", {}):
        data.setdefault("chats", {})[chat_key] = {}

    data["chats"][chat_key]["text"] = text
    save_json(WELCOME_FILE, data)


def set_welcome_photo(chat_id: int, photo_url: str):
    """Установка фото приветствия для чата"""
    data = load_json(WELCOME_FILE)
    chat_key = str(chat_id)

    if chat_key not in data.get("chats", {}):
        data.setdefault("chats", {})[chat_key] = {}

    data["chats"][chat_key]["photo"] = photo_url
    save_json(WELCOME_FILE, data)


def is_valid_image_url(url: str) -> bool:
    """Проверка, является ли URL ссылкой на изображение"""
    url_lower = url.lower().strip()
    return url_lower.endswith(('.png', '.jpg', '.jpeg'))


# ============== Управление правилами ==============

def get_rules(chat_id: int) -> str:
    """Получение правил для чата"""
    data = load_json(RULES_FILE)
    return data.get("chats", {}).get(str(chat_id), data.get("default", DEFAULT_RULES))


def set_rules(chat_id: int, text: str):
    """Установка правил для чата"""
    data = load_json(RULES_FILE)
    chat_key = str(chat_id)

    data.setdefault("chats", {})[chat_key] = text
    save_json(RULES_FILE, data)


# ============== Управление обновлениями ==============

def get_updates_settings() -> Dict[str, Any]:
    """Получение настроек парсера"""
    return load_json(UPDATES_FILE)


def set_updates_enabled(enabled: bool):
    """Включение/выключение парсера"""
    data = load_json(UPDATES_FILE)
    data["enabled"] = enabled
    save_json(UPDATES_FILE, data)


def save_last_version(version: str):
    """Сохранение последней версии"""
    data = load_json(UPDATES_FILE)
    data["last_version"] = version
    data["last_check"] = datetime.now().isoformat()
    save_json(UPDATES_FILE, data)


# ============== Планировщик проверки обновлений ==============

class UpdateChecker:
    """Планировщик проверки обновлений на сайте"""

    VERSION_PATTERNS = [
        r"Обновление\s+([\d.]+)",
        r"Патч\s+LonaRPG\s+Online\s+([\d.]+)",
        r"Скачать\s+версию\s+Beta\s+([\d.]+)",
        r"(?:Версия|Version|v\.?)\s*([\d.]+)",
    ]

    def __init__(self, bot: Bot):
        self.bot = bot
        self._running = False
        self._task: Optional[asyncio.Task] = None

    async def start(self):
        """Запуск планировщика"""
        self._running = True
        self._task = asyncio.create_task(self._check_updates_loop())

    async def stop(self):
        """Остановка планировщика"""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _check_updates_loop(self):
        """Цикл проверки обновлений"""
        while self._running:
            try:
                settings = get_updates_settings()
                if settings.get("enabled", False):
                    await self._check_for_updates()
            except Exception as e:
                print(f"Ошибка при проверке обновлений: {e}")

            await asyncio.sleep(UPDATES_CHECK_INTERVAL)

    def _extract_version(self, text: str) -> Optional[str]:
        """Извлечение версии из текста несколькими способами"""
        for pattern in self.VERSION_PATTERNS:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1)
        return None

    def _clean_text(self, text: str) -> str:
        """Очистка текста от лишних пробелов и переносов"""
        if not text:
            return ""
        # Заменяем множественные пробелы/переносы на один пробел
        text = re.sub(r'\s+', ' ', text)
        return text.strip()

    def _extract_patch_content(self, tree) -> Tuple[Optional[str], Optional[str], str, str]:
        """
        Извлечение информации о патче.
        Возвращает: (версия, дата, полный_контент, краткий_итог)
        """
        version = None
        date = None
        content_parts = []
        summary = ""  # Краткий итог

        # Способ 1: Из <title>
        title_elements = tree.xpath("//title/text()")
        if title_elements:
            version = self._extract_version(title_elements[0])

        # Способ 2: Ищем заголовок патча по эмодзи ✨
        patch_headers = tree.xpath("//h2[contains(text(), '✨') and contains(text(), 'Патч')]")

        if not patch_headers:
            patch_headers = tree.xpath("//h2[contains(text(), 'Патч LonaRPG')]")

        if patch_headers:
            patch_h2 = patch_headers[0]
            header_text = self._clean_text(patch_h2.text_content())

            if not version:
                version = self._extract_version(header_text)

            content_parts.append(f"<b>{header_text}</b>")

            # Собираем контент до следующего <hr> или заголовка старых версий
            current = patch_h2.getnext()
            while current is not None:
                if current.tag == 'hr':
                    break
                if current.tag == 'h2' and (
                        '🧾' in current.text_content() or 'прошлых версиях' in current.text_content().lower()):
                    break

                if current.tag == 'h3':
                    text = self._clean_text(current.text_content())
                    if '📅' in text:
                        date = text
                        content_parts.append(f"\n{date}")
                    else:
                        content_parts.append(f"\n\n<b>{text}</b>")

                elif current.tag == 'p':
                    text = self._clean_text(current.text_content())
                    if text:
                        content_parts.append(f"\n{text}")

                elif current.tag == 'ul':
                    items = current.xpath(".//li")
                    for item in items[:3]:  # Только 3 пункта на секцию
                        item_text = self._clean_text(item.text_content())
                        if item_text:
                            content_parts.append(f"\n• {item_text}")
                    if len(items) > 3:
                        content_parts.append(f"\n<i>...и ещё {len(items) - 3}</i>")

                elif current.tag == 'div' and 'warning-box' in current.get('class', ''):
                    text = self._clean_text(current.text_content())
                    if '🔥 Итог' in text:
                        summary = text  # Сохраняем итог отдельно
                        content_parts.append(f"\n\n{text}")

                current = current.getnext()

        full_content = "\n".join(content_parts) if content_parts else ""
        return version, date, full_content, summary

    async def _check_for_updates(self):
        """Проверка обновлений на сайте"""
        try:
            async with aiohttp.ClientSession() as session:
                headers = {
                    'User-Agent': 'LonaRPG-Bot/1.0'
                }
                async with session.get(UPDATES_URL, headers=headers, timeout=30) as response:
                    if response.status != 200:
                        print(f"Ошибка загрузки страницы: {response.status}")
                        return

                    page_content = await response.text()

            tree = lxml_html.fromstring(page_content)
            current_version, date, content, summary = self._extract_patch_content(tree)

            if not current_version:
                print("Не удалось определить версию")
                return

            settings = get_updates_settings()
            last_version = settings.get("last_version")

            print(f"Проверка обновлений: текущая={current_version}, последняя={last_version}")

            if last_version is not None and current_version != last_version:
                await self._send_update_notification(current_version, content, summary)

            save_last_version(current_version)

        except asyncio.TimeoutError:
            print("Таймаут при загрузке страницы")
        except Exception as e:
            print(f"Ошибка парсинга: {e}")
            import traceback
            traceback.print_exc()

    async def _send_update_notification(self, version: str, content: str, summary: str = ""):
        """Отправка уведомления об обновлении"""
        from aiogram.enums import ParseMode

        # Базовая часть сообщения
        header = f"🎮 <b>Вышло обновление LonaRPG Online!</b>\n"
        header += f"📦 <b>Версия:</b> {version}\n"
        footer = f"\n\n🔗 <a href='{UPDATES_URL}'>Подробнее на сайте</a>"

        # Проверяем, помещается ли полный контент
        full_message = header + "\n" + content + footer

        if len(full_message) <= 4000:
            # Полный контент помещается
            message_text = full_message
        elif summary:
            # Отправляем краткую версию с итогом
            message_text = header + f"\n{summary}" + footer
        else:
            # Совсем краткая версия
            message_text = header + footer

        try:
            await self.bot.send_message(
                chat_id=UPDATES_CHAT_ID,
                message_thread_id=UPDATES_THREAD_ID,
                text=message_text,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True
            )
            print(f"Уведомление об обновлении отправлено: {version}")
        except Exception as e:
            print(f"Ошибка отправки уведомления: {e}")

    async def force_check(self) -> str:
        """Принудительная проверка (для тестов). Возвращает статус."""
        try:
            settings = get_updates_settings()
            old_version = settings.get("last_version", "не определена")

            await self._check_for_updates()

            settings = get_updates_settings()
            new_version = settings.get("last_version", "не определена")

            return f"✅ Проверка завершена\nБыла: {old_version}\nСейчас: {new_version}"
        except Exception as e:
            return f"❌ Ошибка: {e}"


# ============== Планировщик автоматического размута ==============

class MuteScheduler:
    """Планировщик автоматического размута"""

    def __init__(self, bot: Bot):
        self.bot = bot
        self._running = False
        self._task: Optional[asyncio.Task] = None

    async def start(self):
        """Запуск планировщика"""
        self._running = True
        self._task = asyncio.create_task(self._check_mutes_loop())

    async def stop(self):
        """Остановка планировщика"""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _check_mutes_loop(self):
        """Цикл проверки истекших мутов"""
        while self._running:
            try:
                await self._process_expired_mutes()
            except Exception as e:
                print(f"Ошибка при проверке мутов: {e}")

            await asyncio.sleep(30)

    async def _process_expired_mutes(self):
        """Обработка истекших мутов"""
        from aiogram.types import ChatPermissions

        now = datetime.now().timestamp()
        all_mutes = get_all_mutes()

        for chat_id, users in all_mutes.items():
            for user_id, info in list(users.items()):
                end_time = info.get("end_time", 0)

                if end_time <= now:
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
                        remove_mute(int(chat_id), int(user_id))

                    except Exception as e:
                        print(f"Ошибка при размуте {user_id} в чате {chat_id}: {e}")
                        remove_mute(int(chat_id), int(user_id))