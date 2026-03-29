"""
Хэндлеры команд бота
"""
import re
from datetime import datetime

from aiogram import Bot, Router, F
from aiogram.types import Message, ChatMemberUpdated, ChatPermissions
from aiogram.filters import ChatMemberUpdatedFilter, IS_MEMBER, IS_NOT_MEMBER
from aiogram.enums import ParseMode, ChatType
from aiogram.exceptions import TelegramBadRequest

from config import MESSAGES
from utils import (
    is_user_admin, bot_has_ban_rights, bot_has_mute_rights, is_target_admin,
    parse_user_target, extract_args_without_user,
    parse_duration, format_duration, format_remaining_time,
    add_ban, get_ban_list,
    add_mute, remove_mute, get_mute_list,
    get_welcome, set_welcome_text, set_welcome_photo, is_valid_image_url,
    get_rules, set_rules
)

# Создаём роутер
router = Router()

# Фильтр: только групповые чаты
router.message.filter(F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}))
router.chat_member.filter(F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}))


# ============== Вспомогательные функции ==============

async def reply_in_topic(message: Message, text: str, **kwargs):
    """Ответ в той же теме, где написана команда"""
    # Убираем только то, что мы сами будем задавать
    kwargs.pop('parse_mode', None)

    await message.answer(
        text,
        parse_mode=ParseMode.HTML,
        **kwargs
    )


async def reply_photo_in_topic(message: Message, photo: str, caption: str, **kwargs):
    """Отправка фото в той же теме"""
    kwargs.pop('parse_mode', None)
    kwargs.pop('caption', None)   # на всякий случай

    await message.answer_photo(
        photo=photo,
        caption=caption,
        parse_mode=ParseMode.HTML,
        **kwargs
    )


def extract_command_args(message: Message, command_patterns: list) -> str:
    """Извлечение аргументов команды"""
    text = message.text or ""

    for pattern in command_patterns:
        match = re.match(rf"^{pattern}\s*(.*)", text, re.IGNORECASE | re.DOTALL)
        if match:
            return match.group(1).strip()

    return ""


# ============== Хэндлер бана ==============

@router.message(F.text.regexp(r"^[!]?(?:бан|кик)\b", flags=re.IGNORECASE))
async def ban_handler(message: Message, bot: Bot):
    """Обработка команды бана"""
    # Проверка прав пользователя
    if not await is_user_admin(bot, message.chat.id, message.from_user.id):
        await reply_in_topic(message, MESSAGES["no_admin_rights"])
        return

    # Проверка прав бота
    if not await bot_has_ban_rights(bot, message.chat.id):
        await reply_in_topic(message, MESSAGES["bot_no_ban_rights"])
        return

    # Извлекаем аргументы
    args = extract_command_args(message, [r"[!]?бан", r"[!]?кик"])

    # Получаем целевого пользователя
    target = await parse_user_target(bot, message, args)

    if not target:
        await reply_in_topic(message, MESSAGES["ban_no_target"])
        return

    user_id, user_name = target

    # Проверка, не является ли целевой пользователь админом
    if await is_target_admin(bot, message.chat.id, user_id):
        await reply_in_topic(message, MESSAGES["ban_cannot_ban_admin"])
        return

    try:
        # Баним пользователя
        await bot.ban_chat_member(message.chat.id, user_id)

        # Добавляем в список забаненных
        add_ban(message.chat.id, user_id, user_name)

        # Отправляем сообщение об успехе
        await reply_in_topic(
            message,
            MESSAGES["ban_success"].format(user_id=user_id, user_name=user_name)
        )

    except TelegramBadRequest as e:
        if "user not found" in str(e).lower():
            await reply_in_topic(message, MESSAGES["ban_user_not_found"])
        else:
            await reply_in_topic(message, f"❌ Ошибка: {e}")


# ============== Хэндлер списка банов ==============

@router.message(F.text.regexp(r"^(?:баны|банлист)$", flags=re.IGNORECASE))
async def ban_list_handler(message: Message, bot: Bot):
    """Показ списка забаненных пользователей"""
    ban_list = get_ban_list(message.chat.id)

    if not ban_list:
        await reply_in_topic(message, MESSAGES["ban_list_empty"])
        return

    text = MESSAGES["ban_list_header"]

    for user_id, info in ban_list.items():
        user_name = info.get("name", "Неизвестный")
        banned_at = info.get("banned_at", "")

        # Форматируем дату, если есть
        date_str = ""
        if banned_at:
            try:
                dt = datetime.fromisoformat(banned_at)
                date_str = f" ({dt.strftime('%d.%m.%Y')})"
            except:
                pass

        text += f"• <a href='tg://user?id={user_id}'>{user_name}</a>{date_str}\n"

    await reply_in_topic(message, text)


# ============== Хэндлер мута ==============

@router.message(F.text.regexp(r"^[!]?(?:мут|мьют)\b", flags=re.IGNORECASE))
async def mute_handler(message: Message, bot: Bot):
    """Обработка команды мута"""
    # Проверка прав пользователя
    if not await is_user_admin(bot, message.chat.id, message.from_user.id):
        await reply_in_topic(message, MESSAGES["no_admin_rights"])
        return

    # Проверка прав бота
    if not await bot_has_mute_rights(bot, message.chat.id):
        await reply_in_topic(message, MESSAGES["bot_no_mute_rights"])
        return

    # Извлекаем аргументы
    args = extract_command_args(message, [r"[!]?мут", r"[!]?мьют"])

    # Получаем целевого пользователя
    target = await parse_user_target(bot, message, args)

    if not target:
        await reply_in_topic(message, MESSAGES["mute_no_target"])
        return

    user_id, user_name = target

    # Проверка, не является ли целевой пользователь админом
    if await is_target_admin(bot, message.chat.id, user_id):
        await reply_in_topic(message, MESSAGES["mute_cannot_mute_admin"])
        return

    # Извлекаем время из аргументов
    # Если ответ на сообщение - всё время в args
    # Если указан пользователь - убираем его из args
    if message.reply_to_message:
        duration_text = args
    else:
        duration_text = extract_args_without_user(args)

    if not duration_text:
        await reply_in_topic(message, MESSAGES["mute_no_duration"])
        return

    duration_seconds = parse_duration(duration_text)

    if duration_seconds is None:
        await reply_in_topic(message, MESSAGES["mute_invalid_duration"])
        return

    if duration_seconds < 60:
        await reply_in_topic(message, MESSAGES["mute_min_duration"])
        return

    try:
        # Мутим пользователя навсегда (до ручного размута)
        await bot.restrict_chat_member(
            chat_id=message.chat.id,
            user_id=user_id,
            permissions=ChatPermissions(
                can_send_messages=False,
                can_send_audios=False,
                can_send_documents=False,
                can_send_photos=False,
                can_send_videos=False,
                can_send_video_notes=False,
                can_send_voice_notes=False,
                can_send_polls=False,
                can_send_other_messages=False,
                can_add_web_page_previews=False
            )
        )

        # Добавляем в список замученных
        add_mute(message.chat.id, user_id, user_name, duration_seconds)

        # Отправляем сообщение об успехе
        duration_formatted = format_duration(duration_seconds)
        await reply_in_topic(
            message,
            MESSAGES["mute_success"].format(
                user_id=user_id,
                user_name=user_name,
                duration=duration_formatted
            )
        )

    except TelegramBadRequest as e:
        if "user not found" in str(e).lower():
            await reply_in_topic(message, MESSAGES["mute_user_not_found"])
        else:
            await reply_in_topic(message, f"❌ Ошибка: {e}")


# ============== Хэндлер списка мутов ==============

@router.message(F.text.regexp(r"^(?:муты|мутлист)$", flags=re.IGNORECASE))
async def mute_list_handler(message: Message, bot: Bot):
    """Показ списка замученных пользователей"""
    mute_list = get_mute_list(message.chat.id)

    # Фильтруем истекшие муты
    now = datetime.now().timestamp()
    active_mutes = {
        uid: info for uid, info in mute_list.items()
        if info.get("end_time", 0) > now
    }

    if not active_mutes:
        await reply_in_topic(message, MESSAGES["mute_list_empty"])
        return

    text = MESSAGES["mute_list_header"]

    for user_id, info in active_mutes.items():
        user_name = info.get("name", "Неизвестный")
        end_time = info.get("end_time", 0)
        remaining = format_remaining_time(end_time)

        text += f"• <a href='tg://user?id={user_id}'>{user_name}</a> — осталось: {remaining}\n"

    await reply_in_topic(message, text)


# ============== Хэндлер приветствия новых участников ==============

@router.chat_member(ChatMemberUpdatedFilter(IS_NOT_MEMBER >> IS_MEMBER))
async def welcome_handler(event: ChatMemberUpdated, bot: Bot):
    """Приветствие нового участника"""
    user = event.new_chat_member.user

    if user.is_bot:
        return

    welcome_text, welcome_photo = get_welcome(event.chat.id)

    # Подставляем данные пользователя
    formatted_text = welcome_text.format(
        user_id=user.id,
        user_name=user.full_name,
        first_name=user.first_name or "",
        last_name=user.last_name or "",
        username=user.username or ""
    )

    # Получаем ID темы (для супергрупп с темами)
    # В ChatMemberUpdated нет прямого доступа к теме, поэтому используем General тему
    # или отправляем в основной чат

    try:
        if welcome_photo:
            await bot.send_photo(
                chat_id=event.chat.id,
                photo=welcome_photo,
                caption=formatted_text,
                parse_mode=ParseMode.HTML
            )
        else:
            await bot.send_message(
                chat_id=event.chat.id,
                text=formatted_text,
                parse_mode=ParseMode.HTML
            )
    except Exception as e:
        print(f"Ошибка отправки приветствия: {e}")


# ============== Хэндлер изменения приветствия ==============

@router.message(F.text.regexp(r"^!приветствие\s+фото\s+", flags=re.IGNORECASE))
async def set_welcome_photo_handler(message: Message, bot: Bot):
    """Установка фото приветствия"""
    # Проверка прав пользователя
    if not await is_user_admin(bot, message.chat.id, message.from_user.id):
        await reply_in_topic(message, MESSAGES["no_admin_rights"])
        return

    # Извлекаем URL фото
    match = re.match(r"^!приветствие\s+фото\s+(.+)", message.text, re.IGNORECASE)
    if not match:
        await reply_in_topic(message, MESSAGES["welcome_no_photo"])
        return

    photo_url = match.group(1).strip()

    if not is_valid_image_url(photo_url):
        await reply_in_topic(message, MESSAGES["welcome_photo_invalid"])
        return

    set_welcome_photo(message.chat.id, photo_url)
    await reply_in_topic(message, MESSAGES["welcome_photo_updated"])


@router.message(F.text.regexp(r"^!приветствие\s*\n", flags=re.IGNORECASE))
async def set_welcome_text_handler(message: Message, bot: Bot):
    """Установка текста приветствия"""
    # Проверка прав пользователя
    if not await is_user_admin(bot, message.chat.id, message.from_user.id):
        await reply_in_topic(message, MESSAGES["no_admin_rights"])
        return

    # Извлекаем текст приветствия (всё после первой строки)
    lines = message.text.split("\n", 1)
    if len(lines) < 2 or not lines[1].strip():
        await reply_in_topic(message, MESSAGES["welcome_no_text"])
        return

    welcome_text = lines[1].strip()

    set_welcome_text(message.chat.id, welcome_text)
    await reply_in_topic(message, MESSAGES["welcome_text_updated"])


# ============== Хэндлер правил ==============

@router.message(F.text.regexp(r"^правила$", flags=re.IGNORECASE))
async def rules_handler(message: Message, bot: Bot):
    """Показ правил чата"""
    rules = get_rules(message.chat.id)
    await reply_in_topic(message, rules)


# ============== Хэндлер изменения правил ==============

@router.message(F.text.regexp(r"^!правила\s*\n", flags=re.IGNORECASE))
async def set_rules_handler(message: Message, bot: Bot):
    """Установка правил чата"""
    # Проверка прав пользователя
    if not await is_user_admin(bot, message.chat.id, message.from_user.id):
        await reply_in_topic(message, MESSAGES["no_admin_rights"])
        return

    # Извлекаем текст правил (всё после первой строки)
    lines = message.text.split("\n", 1)
    if len(lines) < 2 or not lines[1].strip():
        await reply_in_topic(message, MESSAGES["rules_no_text"])
        return

    rules_text = lines[1].strip()

    set_rules(message.chat.id, rules_text)
    await reply_in_topic(message, MESSAGES["rules_updated"])


# ============== Хэндлер для игнорирования личных сообщений ==============

private_router = Router()


@private_router.message(F.chat.type == ChatType.PRIVATE)
async def ignore_private_messages(message: Message):
    """Игнорируем все личные сообщения"""
    pass  # Просто ничего не делаем
