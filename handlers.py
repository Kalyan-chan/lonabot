"""
Хэндлеры команд бота
"""
import re
import logging
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
    add_ban, get_ban_list, remove_ban,
    add_mute, remove_mute, get_mute_list,
    get_welcome, set_welcome_text, set_welcome_photo, is_valid_image_url,
    get_rules, set_rules,
    reply_in_topic
)

logger = logging.getLogger(__name__)

router = Router()
router.message.filter(F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}))
router.chat_member.filter(F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}))


# ============== Вспомогательные функции ==============

def extract_command_args(message: Message, command_patterns: list) -> str:
    text = message.text or ""
    for pattern in command_patterns:
        match = re.match(rf"^{pattern}\s*(.*)", text, re.IGNORECASE | re.DOTALL)
        if match:
            return match.group(1).strip()
    return ""


# ============== Хэндлер бана ==============

@router.message(F.text.regexp(r"^!?(?:бан|кик)\b", flags=re.IGNORECASE))
async def ban_handler(message: Message, bot: Bot):
    if not await is_user_admin(bot, message.chat.id, message.from_user.id):
        await reply_in_topic(message, MESSAGES["no_admin_rights"])
        return

    if not await bot_has_ban_rights(bot, message.chat.id):
        await reply_in_topic(message, MESSAGES["bot_no_ban_rights"])
        return

    args = extract_command_args(message, [r"!?бан", r"!?кик"])
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
        await add_ban(message.chat.id, user_id, user_name)
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
    ban_list = await get_ban_list(message.chat.id)

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
            except Exception:
                pass

        text += f"• <a href='tg://user?id={user_id}'>{user_name}</a>{date_str}\n"

    await reply_in_topic(message, text)


# ============== Хэндлер команд ==============

@router.message(F.text.regexp(r"^(?:[!/]?)(?:команды|help|хелп)$", flags=re.IGNORECASE))
async def commands_handler(message: Message, bot: Bot):
    is_admin = await is_user_admin(bot, message.chat.id, message.from_user.id)

    user_commands = """📖 <b>Команды:</b>
• <code>правила</code> — правила чата
• <code>баны</code> — список забаненных
• <code>муты</code> — список замученных
• <code>онлайн</code> — игроки в игре
• <code>обновы?</code> — статус уведомлений
"""

    admin_commands = """
🛡️ <b>Модерация:</b>
• <code>бан</code> — заблокировать пользователя
• <code>разбан</code> — разблокировать пользователя
• <code>мут @user 30 минут</code> — замутить
• <code>размут @user</code> — размутить

⚙️ <b>Настройки:</b>
• <code>!приветствие</code> — изменить приветствие
• <code>!приветствие фото URL</code> — изменить фото
• <code>!правила</code> — изменить правила

🔔 <b>Обновления:</b>
• <code>+обновы</code> — включить уведомления
• <code>-обновы</code> — выключить уведомления
• <code>!проверить</code> — проверить сейчас
"""

    text = user_commands + admin_commands if is_admin else user_commands
    await reply_in_topic(message, text)


# ============== Хэндлер мута ==============

@router.message(F.text.regexp(r"^!?(?:мут|мьют)\b", flags=re.IGNORECASE))
async def mute_handler(message: Message, bot: Bot):
    if not await is_user_admin(bot, message.chat.id, message.from_user.id):
        await reply_in_topic(message, MESSAGES["no_admin_rights"])
        return

    if not await bot_has_mute_rights(bot, message.chat.id):
        await reply_in_topic(message, MESSAGES["bot_no_mute_rights"])
        return

    args = extract_command_args(message, [r"!?мут", r"!?мьют"])
    target = await parse_user_target(bot, message, args)

    if not target:
        await reply_in_topic(message, MESSAGES["mute_no_target"])
        return

    user_id, user_name = target

    if await is_target_admin(bot, message.chat.id, user_id):
        await reply_in_topic(message, MESSAGES["mute_cannot_mute_admin"])
        return

    duration_text = args if message.reply_to_message else extract_args_without_user(args)

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

        await add_mute(message.chat.id, user_id, user_name, duration_seconds)

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
    mute_list = await get_mute_list(message.chat.id)

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

@router.message(F.text.regexp(r"^!?(?:размут|анмут)\b", flags=re.IGNORECASE))
async def unmute_handler(message: Message, bot: Bot):
    if not await is_user_admin(bot, message.chat.id, message.from_user.id):
        await reply_in_topic(message, MESSAGES["no_admin_rights"])
        return

    if not await bot_has_mute_rights(bot, message.chat.id):
        await reply_in_topic(message, MESSAGES["bot_no_mute_rights"])
        return

    args = extract_command_args(message, [r"!?размут", r"!?анмут"])
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
        await remove_mute(message.chat.id, user_id)
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

@router.message(F.text.regexp(r"^!?(?:разбан|анбан)\b", flags=re.IGNORECASE))
async def unban_handler(message: Message, bot: Bot):
    if not await is_user_admin(bot, message.chat.id, message.from_user.id):
        await reply_in_topic(message, MESSAGES["no_admin_rights"])
        return

    if not await bot_has_ban_rights(bot, message.chat.id):
        await reply_in_topic(message, MESSAGES["bot_no_ban_rights"])
        return

    args = extract_command_args(message, [r"!?разбан", r"!?анбан"])
    target = await parse_user_target(bot, message, args)

    if not target:
        await reply_in_topic(message, MESSAGES["unban_no_target"])
        return

    user_id, user_name = target

    try:
        await bot.unban_chat_member(message.chat.id, user_id, only_if_banned=True)
        await remove_ban(message.chat.id, user_id)
        await reply_in_topic(
            message,
            MESSAGES["unban_success"].format(user_id=user_id, user_name=user_name)
        )
    except TelegramBadRequest as e:
        if "user not found" in str(e).lower():
            await reply_in_topic(message, MESSAGES["ban_user_not_found"])
        else:
            await reply_in_topic(message, f"❌ Ошибка: {e}")


# ============== Хэндлер приветствия новых участников ==============

@router.chat_member(ChatMemberUpdatedFilter(IS_NOT_MEMBER >> IS_MEMBER))
async def welcome_handler(event: ChatMemberUpdated, bot: Bot):
    user = event.new_chat_member.user

    if user.is_bot:
        return

    welcome_text, welcome_photo = await get_welcome(event.chat.id)

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
        logger.error("Ошибка отправки приветствия: %s", e)


# ============== Хэндлер изменения приветствия ==============

@router.message(F.text.regexp(r"^!приветствие\s+фото\s+", flags=re.IGNORECASE))
async def set_welcome_photo_handler(message: Message, bot: Bot):
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

    await set_welcome_photo(message.chat.id, photo_url)
    await reply_in_topic(message, MESSAGES["welcome_photo_updated"])


@router.message(F.text.regexp(r"^!приветствие\s*\n", flags=re.IGNORECASE))
async def set_welcome_text_handler(message: Message, bot: Bot):
    if not await is_user_admin(bot, message.chat.id, message.from_user.id):
        await reply_in_topic(message, MESSAGES["no_admin_rights"])
        return

    lines = message.text.split("\n", 1)
    if len(lines) < 2 or not lines[1].strip():
        await reply_in_topic(message, MESSAGES["welcome_no_text"])
        return

    await set_welcome_text(message.chat.id, lines[1].strip())
    await reply_in_topic(message, MESSAGES["welcome_text_updated"])


# ============== Хэндлер правил ==============

@router.message(F.text.regexp(r"^правила$", flags=re.IGNORECASE))
async def rules_handler(message: Message, bot: Bot):
    rules = await get_rules(message.chat.id)
    await reply_in_topic(message, rules)


@router.message(F.text.regexp(r"^!правила\s*\n", flags=re.IGNORECASE))
async def set_rules_handler(message: Message, bot: Bot):
    if not await is_user_admin(bot, message.chat.id, message.from_user.id):
        await reply_in_topic(message, MESSAGES["no_admin_rights"])
        return

    lines = message.text.split("\n", 1)
    if len(lines) < 2 or not lines[1].strip():
        await reply_in_topic(message, MESSAGES["rules_no_text"])
        return

    await set_rules(message.chat.id, lines[1].strip())
    await reply_in_topic(message, MESSAGES["rules_updated"])

private_router = Router()

@private_router.message(F.chat.type == ChatType.PRIVATE)
async def ignore_private_messages(message: Message):
    pass