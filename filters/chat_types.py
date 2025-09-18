from aiogram.filters import Filter
from aiogram import types

from sqlalchemy.ext.asyncio import AsyncSession

from database.orm_query import orm_get_user


class ChatTypeFilter(Filter):
    def __init__(self, chat_types: list[str]) -> None:
        self.chat_types = chat_types

    async def __call__(self, message: types.Message) -> bool:
        return message.chat.type in self.chat_types


class IsAdmin(Filter):
    async def __call__(self, message: types.Message, session: AsyncSession) -> bool:
        user = await orm_get_user(session, message.from_user.id)
        return bool(user and user.is_admin)
