from aiogram import Router, types
from aiogram.filters import Command

from sqlalchemy.ext.asyncio import AsyncSession

from database.orm_query import (
    orm_add_user,
    orm_get_user,
    orm_update_user_admin_status,
)
from filters.chat_types import ChatTypeFilter, IsAdmin


group_admin_router = Router()
group_admin_router.message.filter(ChatTypeFilter(["group", "supergroup"]), IsAdmin())


def _extract_target_user(message: types.Message) -> types.User | None:
    reply = message.reply_to_message
    if not reply:
        return None

    user = reply.from_user
    if user is None or user.is_bot:
        return None

    return user


def _format_user_name(user: types.User) -> str:
    parts: list[str] = []

    if user.full_name:
        parts.append(user.full_name)

    if user.username:
        parts.append(f"@{user.username}")

    if not parts:
        return f"id:{user.id}"

    return " ".join(dict.fromkeys(parts))


@group_admin_router.message(Command("add_admin"))
async def add_admin_command(message: types.Message, session: AsyncSession) -> None:
    target_user = _extract_target_user(message)

    if target_user is None:
        await message.reply(
            "Чтобы назначить администратора, ответьте командой /add_admin "
            "на сообщение нужного пользователя."
        )
        return

    db_user = await orm_get_user(session, target_user.id)
    if db_user and db_user.is_admin:
        await message.reply(
            f"{_format_user_name(target_user)} уже является администратором."
        )
        return

    if db_user:
        await orm_update_user_admin_status(
            session,
            target_user.id,
            True,
            first_name=target_user.first_name,
            last_name=target_user.last_name,
        )
    else:
        await orm_add_user(
            session,
            target_user.id,
            first_name=target_user.first_name,
            last_name=target_user.last_name,
            is_admin=True,
        )

    await message.reply(
        f"{_format_user_name(target_user)} назначен администратором."
    )


@group_admin_router.message(Command("remove_admin"))
async def remove_admin_command(message: types.Message, session: AsyncSession) -> None:
    target_user = _extract_target_user(message)

    if target_user is None:
        await message.reply(
            "Чтобы снять права администратора, ответьте командой /remove_admin "
            "на сообщение нужного пользователя."
        )
        return

    db_user = await orm_get_user(session, target_user.id)
    if not db_user or not db_user.is_admin:
        await message.reply(
            f"{_format_user_name(target_user)} не является администратором."
        )
        return

    await orm_update_user_admin_status(
        session,
        target_user.id,
        False,
        first_name=target_user.first_name,
        last_name=target_user.last_name,
    )

    await message.reply(
        f"{_format_user_name(target_user)} больше не является администратором."
    )
