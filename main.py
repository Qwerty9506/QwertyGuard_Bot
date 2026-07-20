import asyncio
from aiogram import Bot, Dispatcher
from aiohttp import web
import config
import database as db
from handlers import private, group

async def handle_ping(request):
    return web.Response(text="Bot is running!")

async def start_web_server():
    app = web.Application()
    app.router.add_get('/', handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', config.WEB_PORT)
    await site.start()
    print(f"Web server started on port {config.WEB_PORT}")

async def main():
    await db.init_db()

    bot = Bot(token=config.BOT_TOKEN)
    dp = Dispatcher()

    dp.include_router(private.router)
    dp.include_router(group.router)

    await asyncio.gather(
        start_web_server(),
        dp.start_polling(bot)
    )

if __name__ == "__main__":
    asyncio.run(main())