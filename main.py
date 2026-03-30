"""
Главный файл запуска Telegram бота
LonaRPG Community Bot
Версия: 1.1.0
"""
import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

from config import BOT_TOKEN
from handlers import router, private_router
from utils import init_data_files, MuteScheduler, UpdateChecker


# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("bot.log", encoding="utf-8")
    ]
)
logger = logging.getLogger(__name__)


async def main():
    """Главная функция запуска бота"""
    # Проверка токена
    if BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        logger.error("Токен бота не установлен! Установите переменную окружения BOT_TOKEN или укажите токен в config.py")
        sys.exit(1)

    # Создание бота с настройками по умолчанию
    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(
            parse_mode=ParseMode.HTML
        )
    )

    # Создание диспетчера
    dp = Dispatcher()

    # Создание планировщиков
    mute_scheduler = MuteScheduler(bot)
    update_checker = UpdateChecker(bot)
    bot.update_checker = update_checker  # Для доступа из хэндлеров

    # Функции startup/shutdown
    async def on_startup():
        """Действия при запуске бота"""
        logger.info("Инициализация файлов данных...")
        init_data_files()

        logger.info("Запуск планировщика размутов...")
        await mute_scheduler.start()

        logger.info("Запуск планировщика обновлений...")
        await update_checker.start()

        bot_info = await bot.get_me()
        logger.info(f"Бот @{bot_info.username} успешно запущен!")

    async def on_shutdown():
        """Действия при остановке бота"""
        logger.info("Остановка планировщика размутов...")
        await mute_scheduler.stop()

        logger.info("Остановка планировщика обновлений...")
        await update_checker.stop()

        logger.info("Бот остановлен.")

    # Регистрация роутеров
    dp.include_router(private_router)  # Роутер для игнорирования ЛС (первый в очереди)
    dp.include_router(router)          # Основной роутер команд

    # Регистрация обработчиков startup/shutdown
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    try:
        logger.info("Запуск бота...")
        # Удаляем вебхуки и запускаем polling
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Бот остановлен пользователем")
    except Exception as e:
        logger.exception(f"Критическая ошибка: {e}")
        sys.exit(1)