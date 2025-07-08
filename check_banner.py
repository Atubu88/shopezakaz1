from dotenv import load_dotenv, find_dotenv
import os

load_dotenv(find_dotenv())  # Загрузка переменных окружения

from database.orm_query import orm_get_banner
from sqlalchemy.ext.asyncio import AsyncSession
from database.engine import session_maker
import asyncio

async def check_banner():
    async with session_maker() as session:
        session.expire_all()# Используем session_maker
        banner = await orm_get_banner(session, "main")
        if banner:
            print(f"Данные баннера: {banner.name}, {banner.image}, {banner.description}")
            if banner.image and os.path.exists(banner.image):
                print(f"Путь к изображению баннера корректен: {banner.image}")
            else:
                print(f"Путь к изображению не указан или некорректен: {banner.image}")
        else:
            print("Баннер не найден в базе данных.")

asyncio.run(check_banner())
