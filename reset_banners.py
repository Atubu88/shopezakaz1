import asyncio
import os
from dotenv import load_dotenv
from sqlalchemy import text

from database.engine import session_maker
from common.texts_for_db import description_for_info_pages
from database.orm_query import orm_add_banner_description


# Подхватываем переменные окружения
load_dotenv()


async def reset_banners():
    async with session_maker() as session:
        # 1. Полностью чистим таблицу и сбрасываем ID
        await session.execute(text("TRUNCATE TABLE banner RESTART IDENTITY;"))
        await session.commit()

        # 2. Заливаем новые дефолтные описания
        await orm_add_banner_description(session, description_for_info_pages)
        print("✅ Таблица banner сброшена и заполнена новыми данными.")


if __name__ == "__main__":
    asyncio.run(reset_banners())
