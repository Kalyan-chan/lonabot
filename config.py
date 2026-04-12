"""
Конфигурация бота LonaRPG Community
"""
import os
from pathlib import Path

# Токен бота
BOT_TOKEN = os.getenv("BOT_TOKEN", "8735150280:AAHMnQETt-n6Kn_ZnIGemRiLMQCTmsCKy0k")

# Пути к JSON файлам данных
DATA_DIR = Path("data")
BANS_FILE = DATA_DIR / "bans.json"
MUTES_FILE = DATA_DIR / "mutes.json"
WELCOME_FILE = DATA_DIR / "welcome.json"
RULES_FILE = DATA_DIR / "rules.json"
UPDATES_FILE = DATA_DIR / "updates.json"
MAPS_FILE = DATA_DIR / "maps.json"

# Настройки парсера обновлений
UPDATES_CHECK_INTERVAL = 1200  # 20 минут в секундах
UPDATES_CHAT_ID = -1003790930801
UPDATES_THREAD_ID = 53

# URL для парсинга
UPDATES_URL = "https://lonarpg.online/Download/"
VERSION_JSON_URL = "https://lonarpg.online/version.json"
ONLINE_API_URL = "http://lonarpg.online:50123/api/worldmap/online_players"
LAUNCHER_URL = "https://lonarpg.online/Download/Installer.exe"

# ID администраторов по умолчанию
DEFAULT_ADMINS = [7209807539, 8560098255]

# Приветствие по умолчанию
DEFAULT_WELCOME_TEXT = """👋 Приветик, <a href='tg://user?id={user_id}'>{user_name}</a>! 

Вы оказались в чате посвящённом небольшому проекту по созданию <b>онлайн версии LonaRPG</b>.

Здесь вы можете <a href='https://t.me/lonaonline/9/10'>найти союзников</a> для совместной игры, <a href='https://t.me/lonaonline/11/12'>создать гильдию</a>, <a href='https://t.me/lonaonline/7/8'>написать о баге</a> или пообщаться с единомышленниками.

Ознакомьтесь с правилами, и приятного времяпровождения!"""

DEFAULT_WELCOME_PHOTO = "https://i.postimg.cc/zGMz6s82/1774806899041-019d3abb-d708-70dc-8cbc-390f3499de44.png"

# Правила по умолчанию
DEFAULT_RULES = """📌 <b>Правила чата:</b>
1. Запрещён флуд и спам
2. Запрещён контент 18+
3. Запрещена политика и дискриминация
• Обсуждение политических тем и идеологий
• Политическая символика
4. Запрещены конфликты и токсичность
• Оскорбления, абьюз, провокации и срачи

<b>📌Общее:</b>
• Администрация имеет последнее слово в спорных ситуациях.
• Все участники, включая администрацию, равны перед правилами
• Нарушения вне чата не рассматриваются
• Несогласие с правилами = выход из чата"""

# Сообщения бота
MESSAGES = {
    "no_admin_rights": "❌ У вас нет прав для использования этой команды.",
    "bot_no_ban_rights": "❌ У бота нет прав для исключения пользователей.",
    "bot_no_mute_rights": "❌ У бота нет прав для ограничения пользователей.",

    "ban_success": "🚫 <a href='tg://user?id={user_id}'>{user_name}</a> заключили в темницу Ноэртауна.",
    "ban_user_not_found": "❌ Пользователь не найден.",
    "ban_cannot_ban_admin": "❌ Нельзя наказать администратора.",
    "ban_no_target": "❌ Укажите пользователя для бана.",
    "ban_list_empty": "📋 Список заключённых пуст.",
    "ban_list_header": "📋 <b>Список заключённых:</b>\n\n",

    "mute_success": "🔇 <a href='tg://user?id={user_id}'>{user_name}</a> замолчал на {duration}.",
    "mute_user_not_found": "❌ Пользователь не найден.",
    "mute_cannot_mute_admin": "❌ Нельзя наказать администратора.",
    "mute_no_target": "❌ Укажите пользователя для мута.",
    "mute_no_duration": "❌ Укажите время мута. Пример: мут @user 30 минут",
    "mute_invalid_duration": "❌ Неверный формат времени. Пример: 30 минут, 2 часа",
    "mute_min_duration": "❌ Минимальное время мута - 1 минута.",
    "mute_list_empty": "📋 Список молчунов пуст.",
    "mute_list_header": "📋 <b>Список пользователей в муте:</b>\n\n",
    "unmute_success": "🔊 <a href='tg://user?id={user_id}'>{user_name}</a> снова говорит.",
    "unmute_no_target": "❌ Укажите пользователя для размута.",

    "welcome_text_updated": "✅ Текст приветствия обновлён.",
    "welcome_photo_updated": "✅ Фото приветствия обновлено.",
    "welcome_photo_invalid": "❌ Неверная ссылка на изображение. Ссылка должна заканчиваться на .png, .jpg или .jpeg",
    "welcome_no_text": "❌ Укажите текст приветствия.",
    "welcome_no_photo": "❌ Укажите ссылку на изображение.",

    "unban_success": "✅ <a href='tg://user?id={user_id}'>{user_name}</a> освобождён из темницы Ноэртауна.",
    "unban_no_target": "❌ Укажите пользователя для разбана.",
    "unban_not_banned": "❌ Пользователь не находится в бане.",

    "rules_updated": "✅ Правила чата обновлены.",
    "rules_no_text": "❌ Укажите текст правил.",

    "only_group": "❌ Бот работает только в группах.",
}