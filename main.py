# main.py
import asyncio
import logging
from aiogram import Bot, Dispatcher
from config import BOT_TOKEN
from database import init_db
from handlers import private, group

logging.basicConfig(level=logging.INFO)

async def main():
    # Инициализируем базу данных (создаст таблицы, если их нет)
    init_db()
    
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()

    # Подключаем роутеры
    dp.include_router(private.router)
    dp.include_router(group.router)

    print("=== QwertyGuard Бот успешно запущен! ===")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
