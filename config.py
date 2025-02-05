import os
from dotenv import load_dotenv

#Загрузка переменных из .env файла
load_dotenv()

# Чтение токена из переменной окружения
TOKEN = os.getenv("BOT_TOKEN")

API = os.getenv("WEATHER_API_KEY")

if not TOKEN:
    raise ValueError("Переменная окружения BOT_TOKEN не установлена!")

if not API:
    raise ValueError("API для определения температуры не установлена!")