import os
from dotenv import load_dotenv

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
WEB_PORT = int(os.getenv("PORT", 8080)) # Порт, который выдаст Render
