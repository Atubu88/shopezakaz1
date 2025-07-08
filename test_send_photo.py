from aiogram import Bot, types
from aiogram.types import FSInputFile
import asyncio
import os



# Настройка бота
bot = Bot(token=os.getenv('TOKEN'))  # Убедитесь, что ваш .env файл загружен и содержит правильный токен

async def send_test_photo():
    # Проверка, что файл существует
    if os.path.exists("banners/m.jpg"):
        file = FSInputFile("banners/m.jpg")
        # Замените 'ВАШ_CHAT_ID' на ваш реальный chat_id в Telegram
        await bot.send_photo(chat_id='ВАШ_CHAT_ID', photo=file, caption="Тестовое изображение")
    else:
        print("Файл не найден по указанному пути.")

# Запуск асинхронной функции
asyncio.run(send_test_photo())
