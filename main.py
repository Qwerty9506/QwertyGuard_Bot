# main.py
import asyncio
import logging
import os
from aiohttp import web
from aiogram import Bot, Dispatcher
from config import BOT_TOKEN, WEB_PORT
from database import init_db
from handlers import private, group

logging.basicConfig(level=logging.INFO)

# --- Фиктивный веб-сервер для прохождения проверок Render ---
async def handle(request):
    return web.Response(text="QwertyGuard Bot is running and healthy!")

async def web_server():
    app = web.Application()
    app.router.add_get('/', handle)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', WEB_PORT)
    await site.start()
    print(f"=== Web server started on port {WEB_PORT} (Render Health Check) ===")
# -------------------------------------------------------------

async def main():
    # Инициализируем базу данных
    init_db()
    
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()

    # Подключаем роутеры
    dp.include_router(private.router)
    dp.include_router(group.router)

    # Запускаем фоновый веб-сервер для Render
    asyncio.create_task(web_server())

    print("=== QwertyGuard Бот успешно запущен! ===")
    
    # Сбрасываем старые вебхуки (если были), чтобы избежать ошибок с Polling
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
