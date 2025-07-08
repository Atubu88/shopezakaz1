from aiogram import Bot, Dispatcher, types

from dotenv import load_dotenv, find_dotenv
import os

# Загрузка переменных окружения
load_dotenv(find_dotenv())

bot = Bot(token=os.getenv('TOKEN'))
dp = Dispatcher()

@dp.message_handler(commands=['start'])
async def send_welcome(message: types.Message):
    await message.reply(f"Ваш chat_id: {message.chat.id}")
    print(f"Ваш chat_id: {message.chat.id}")

if __name__ == '__main__':
    dp.startup.register(lambda: print("Бот запущен"))
    Dispatcher(dp, skip_updates=True)
