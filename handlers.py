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

from config import DEFAULT_ADMINS, MESSAGES
from utils import (
    is_user_admin, bot_has_ban_rights, bot_has_mute_rights, is_target_admin,
    parse_user_target, extract_args_without_user,
    parse_duration, format_duration, format_remaining_time,
    add_ban, get_ban_list, remove_ban,
    add_mute, remove_mute, get_mute_list,
    get_welcome, set_welcome_text, set_welcome_photo, is_valid_image_url,
    get_rules, set_rules,
    get_updates_settings, set_updates_enabled, format_last_check
)

# Создаём роутер
router = Router()

# Фильтр: только групповые чаты
router.message.filter(F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}))
router.chat_member.filter(F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}))


# ============== Вспомогательные функции ==============

async def reply_in_topic(message: Message, text: str, **kwargs):
    """Ответ в той же теме, где написана команда"""
    kwargs.pop('parse_mode', None)

    await message.answer(
        text,
        parse_mode=ParseMode.HTML,
        **kwargs
    )


async def reply_photo_in_topic(message: Message, photo: str, caption: str, **kwargs):
    """Отправка фото в той же теме"""
    kwargs.pop('parse_mode', None)
    kwargs.pop('caption', None)

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
    if not await is_user_admin(bot, message.chat.id, message.from_user.id):
        await reply_in_topic(message, MESSAGES["no_admin_rights"])
        return

    if not await bot_has_ban_rights(bot, message.chat.id):
        await reply_in_topic(message, MESSAGES["bot_no_ban_rights"])
        return

    args = extract_command_args(message, [r"[!]?бан", r"[!]?кик"])
    target = await parse_user_target(bot, message, args)

    if not target:
        await reply_in_topic(message, MESSAGES["ban_no_target"])
        return

    user_id, user_name = target

    if await is_target_admin(bot, message.chat.id, user_id):
        await reply_in_topic(message, MESSAGES["ban_cannot_ban_admin"])
        return

    try:
        await bot.ban_chat_member(message.chat.id, user_id)
        add_ban(message.chat.id, user_id, user_name)
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

        date_str = ""
        if banned_at:
            try:
                dt = datetime.fromisoformat(banned_at)
                date_str = f" ({dt.strftime('%d.%m.%Y')})"
            except:
                pass

        text += f"• <a href='tg://user?id={user_id}'>{user_name}</a>{date_str}\n"

    await reply_in_topic(message, text)


# ============== Хэндлер команд ==============

@router.message(F.text.regexp(r"^(?:[!/]?)(?:команды|help|хелп)$", flags=re.IGNORECASE))
async def commands_handler(message: Message, bot: Bot):
    """Показ списка доступных команд"""
    is_admin = await is_user_admin(bot, message.chat.id, message.from_user.id)

    user_commands = """📖 <b>Команды:</b>
• <code>правила</code> — правила чата
• <code>баны</code> — список забаненных
• <code>муты</code> — список замученных
• <code>обновы?</code> — статус уведомлений об обновлениях
"""

    admin_commands = """
🛡️ <b>Модерация:</b>
• <code>бан</code> — заблокировать пользователя
• <code>разбан</code> — разблокировать пользователя
• <code>мут @user 30 минут</code> — замутить пользователя
• <code>размут @user</code> — размутить пользователя

⚙️ <b>Настройки:</b>
• <code>!приветствие</code> — изменить приветствие
• <code>!приветствие фото URL</code> — изменить фото
• <code>!правила</code> — изменить правила

🔔 <b>Обновления:</b>
• <code>+обновы</code> — включить уведомления
• <code>-обновы</code> — выключить уведомления
• <code>!проверить</code> — проверить обновления сейчас
"""

    if is_admin:
        text = user_commands + admin_commands
    else:
        text = user_commands

    await reply_in_topic(message, text)


# ============== Хэндлер мута ==============

@router.message(F.text.regexp(r"^[!]?(?:мут|мьют)\b", flags=re.IGNORECASE))
async def mute_handler(message: Message, bot: Bot):
    """Обработка команды мута"""
    if not await is_user_admin(bot, message.chat.id, message.from_user.id):
        await reply_in_topic(message, MESSAGES["no_admin_rights"])
        return

    if not await bot_has_mute_rights(bot, message.chat.id):
        await reply_in_topic(message, MESSAGES["bot_no_mute_rights"])
        return

    args = extract_command_args(message, [r"[!]?мут", r"[!]?мьют"])
    target = await parse_user_target(bot, message, args)

    if not target:
        await reply_in_topic(message, MESSAGES["mute_no_target"])
        return

    user_id, user_name = target

    if await is_target_admin(bot, message.chat.id, user_id):
        await reply_in_topic(message, MESSAGES["mute_cannot_mute_admin"])
        return

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

        add_mute(message.chat.id, user_id, user_name, duration_seconds)

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


# ============== Хэндлер размута ==============

@router.message(F.text.regexp(r"^[!]?(?:размут|анмут)\b", flags=re.IGNORECASE))
async def unmute_handler(message: Message, bot: Bot):
    """Обработка команды размута"""
    if not await is_user_admin(bot, message.chat.id, message.from_user.id):
        await reply_in_topic(message, MESSAGES["no_admin_rights"])
        return

    if not await bot_has_mute_rights(bot, message.chat.id):
        await reply_in_topic(message, MESSAGES["bot_no_mute_rights"])
        return

    args = extract_command_args(message, [r"[!]?размут", r"[!]?анмут"])
    target = await parse_user_target(bot, message, args)

    if not target:
        await reply_in_topic(message, MESSAGES["unmute_no_target"])
        return

    user_id, user_name = target

    try:
        await bot.restrict_chat_member(
            chat_id=message.chat.id,
            user_id=user_id,
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
                can_invite_users=True
            )
        )
        remove_mute(message.chat.id, user_id)
        await reply_in_topic(
            message,
            MESSAGES["unmute_success"].format(user_id=user_id, user_name=user_name)
        )
    except TelegramBadRequest as e:
        if "user not found" in str(e).lower():
            await reply_in_topic(message, MESSAGES["mute_user_not_found"])
        else:
            await reply_in_topic(message, f"❌ Ошибка: {e}")


# ============== Хэндлер разбана ==============

@router.message(F.text.regexp(r"^[!]?(?:разбан|анбан)\b", flags=re.IGNORECASE))
async def unban_handler(message: Message, bot: Bot):
    """Обработка команды разбана"""
    if not await is_user_admin(bot, message.chat.id, message.from_user.id):
        await reply_in_topic(message, MESSAGES["no_admin_rights"])
        return

    if not await bot_has_ban_rights(bot, message.chat.id):
        await reply_in_topic(message, MESSAGES["bot_no_ban_rights"])
        return

    args = extract_command_args(message, [r"[!]?разбан", r"[!]?анбан"])
    target = await parse_user_target(bot, message, args)

    if not target:
        await reply_in_topic(message, MESSAGES["unban_no_target"])
        return

    user_id, user_name = target

    try:
        await bot.unban_chat_member(message.chat.id, user_id, only_if_banned=True)
        remove_ban(message.chat.id, user_id)
        await reply_in_topic(
            message,
            MESSAGES["unban_success"].format(user_id=user_id, user_name=user_name)
        )
    except TelegramBadRequest as e:
        if "user not found" in str(e).lower():
            await reply_in_topic(message, MESSAGES["ban_user_not_found"])
        else:
            await reply_in_topic(message, f"❌ Ошибка: {e}")


# ============== Хэндлеры управления обновлениями ==============

@router.message(F.text.regexp(r"^\+обновы$", flags=re.IGNORECASE))
async def enable_updates_handler(message: Message, bot: Bot):
    """Включение уведомлений об обновлениях"""
    if not await is_user_admin(bot, message.chat.id, message.from_user.id):
        await reply_in_topic(message, MESSAGES["no_admin_rights"])
        return

    set_updates_enabled(True)
    await reply_in_topic(message, "✅ Уведомления об обновлениях игры включены.")


@router.message(F.text.regexp(r"^-обновы$", flags=re.IGNORECASE))
async def disable_updates_handler(message: Message, bot: Bot):
    """Выключение уведомлений об обновлениях"""
    if not await is_user_admin(bot, message.chat.id, message.from_user.id):
        await reply_in_topic(message, MESSAGES["no_admin_rights"])
        return

    set_updates_enabled(False)
    await reply_in_topic(message, "❌ Уведомления об обновлениях игры выключены.")


@router.message(F.text.regexp(r"^обновы\??$", flags=re.IGNORECASE))
async def updates_status_handler(message: Message, bot: Bot):
    """Статус уведомлений об обновлениях"""
    settings = get_updates_settings()
    enabled = settings.get("enabled", False)
    last_check_raw = settings.get("last_check", "никогда")
    last_version = settings.get("last_version", "—")

    last_check = format_last_check(last_check_raw)   # ←←← ИЗМЕНЕНО

    status = "включены ✅" if enabled else "выключены ❌"

    text = f"📊 <b>Статус уведомлений:</b> {status}\n"
    text += f"📅 <b>Последняя проверка:</b> {last_check}\n"   # ←←← теперь красиво
    text += f"🏷️ <b>Текущая версия:</b> {last_version}"

    await reply_in_topic(message, text)


@router.message(F.text.regexp(r"^!проверить$", flags=re.IGNORECASE))
async def force_check_handler(message: Message, bot: Bot):
    """Принудительная проверка обновлений (только для владельцев)"""
    if message.from_user.id not in DEFAULT_ADMINS:
        return

    await reply_in_topic(message, "🔄 Проверяю обновления...")

    if hasattr(bot, 'update_checker'):
        result = await bot.update_checker.force_check()
        await reply_in_topic(message, result)
    else:
        await reply_in_topic(message, "❌ Планировщик не инициализирован")


# ============== Хэндлер приветствия новых участников ==============

@router.chat_member(ChatMemberUpdatedFilter(IS_NOT_MEMBER >> IS_MEMBER))
async def welcome_handler(event: ChatMemberUpdated, bot: Bot):
    """Приветствие нового участника"""
    user = event.new_chat_member.user

    if user.is_bot:
        return

    welcome_text, welcome_photo = get_welcome(event.chat.id)

    formatted_text = welcome_text.format(
        user_id=user.id,
        user_name=user.full_name,
        first_name=user.first_name or "",
        last_name=user.last_name or "",
        username=user.username or ""
    )

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
    if not await is_user_admin(bot, message.chat.id, message.from_user.id):
        await reply_in_topic(message, MESSAGES["no_admin_rights"])
        return

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
    if not await is_user_admin(bot, message.chat.id, message.from_user.id):
        await reply_in_topic(message, MESSAGES["no_admin_rights"])
        return

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
    if not await is_user_admin(bot, message.chat.id, message.from_user.id):
        await reply_in_topic(message, MESSAGES["no_admin_rights"])
        return

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
    pass