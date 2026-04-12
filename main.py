"""
LonaRPG Community Bot
"""
import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

from config import BOT_TOKEN
from handlers import router, private_router
from parse import parse_router, UpdateChecker
from utils import init_data_files, MuteScheduler
from middlewares import RateLimitMiddleware

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("bot.log", encoding="utf-8")
    ]
)
logging.getLogger("aiogram.event").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


async def main():
    if not BOT_TOKEN or BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        logger.error("Токен бота не установлен!")
        sys.exit(1)

    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )

    dp = Dispatcher()

    # Rate limiting: не чаще 1 сообщения в 2 секунды на пользователя
    dp.message.middleware(RateLimitMiddleware(rate_limit=2.0))

    mute_scheduler = MuteScheduler(bot)
    update_checker = UpdateChecker(bot)
    bot.update_checker = update_checker

    async def on_startup():
        logger.info("Инициализация файлов данных...")
        init_data_files()

        logger.info("Запуск планировщика размутов...")
        await mute_scheduler.start()

        logger.info("Запуск планировщика обновлений...")
        await update_checker.start()

        bot_info = await bot.get_me()
        logger.info("Бот @%s успешно запущен!", bot_info.username)

    async def on_shutdown():
        logger.info("Остановка планировщика размутов...")
        await mute_scheduler.stop()

        logger.info("Остановка планировщика обновлений...")
        await update_checker.stop()

        logger.info("Бот остановлен.")

    dp.include_router(private_router)
    dp.include_router(parse_router)
    dp.include_router(router)

    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    try:
        logger.info("Запуск бота")
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Бот остановлен")
    except Exception as e:
        logger.exception("Критическая ошибка: %s", e)
        sys.exit(1)