from __future__ import annotations

import re
from contextlib import suppress

from aiogram import Bot, Router, types
from aiogram.enums import ChatType, MessageEntityType
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command

from sqlalchemy.ext.asyncio import AsyncSession

from database.orm_query import (
    orm_add_user,
    orm_get_user,
    orm_update_user_admin_status,
)
from filters.chat_types import ChatTypeFilter, IsAdmin


_ARGUMENT_STRIP_CHARS = " ,.;:!()[]{}<>\"'`"
_TG_USER_ID_RE = re.compile(r"tg://user\\?id=(\\d+)", re.IGNORECASE)
_TME_USERNAME_RE = re.compile(
    r"^(?:https?://)?(?:t|telegram)\.me/(?:@?)([a-zA-Z0-9_]{3,})/?$",
    re.IGNORECASE,
)
_USERNAME_RE = re.compile(r"^[a-zA-Z0-9_]{3,}$")


group_admin_router = Router()
group_admin_router.message.filter(ChatTypeFilter(["group", "supergroup"]), IsAdmin())


async def _extract_target_user(message: types.Message, bot: Bot) -> types.User | None:
    reply = message.reply_to_message
    if reply and reply.from_user and not reply.from_user.is_bot:
        return reply.from_user

    user = await _extract_user_from_entities(message, bot)
    if user:
        return user

    argument = _get_command_argument(message)
    if not argument:
        return None

    return await _extract_user_from_argument(argument, message, bot)


def _get_command_argument(message: types.Message) -> str | None:
    text = message.text or message.caption
    if not text:
        return None

    parts = text.strip().split(maxsplit=1)
    if len(parts) < 2:
        return None

    raw_argument = parts[1].split()[0]
    argument = raw_argument.strip(_ARGUMENT_STRIP_CHARS)
    return argument or None


async def _extract_user_from_entities(
    message: types.Message, bot: Bot
) -> types.User | None:
    if message.entities and message.text:
        user = await _extract_user_from_entity_list(
            message, message.text, message.entities, bot
        )
        if user:
            return user

    if message.caption_entities and message.caption:
        user = await _extract_user_from_entity_list(
            message, message.caption, message.caption_entities, bot
        )
        if user:
            return user

    return None


async def _extract_user_from_entity_list(
    message: types.Message,
    text: str,
    entities: list[types.MessageEntity],
    bot: Bot,
) -> types.User | None:
    for entity in entities:
        if entity.type == MessageEntityType.BOT_COMMAND:
            continue

        if entity.type == MessageEntityType.TEXT_MENTION and entity.user:
            if not entity.user.is_bot:
                return entity.user

        if entity.type == MessageEntityType.TEXT_LINK and entity.url:
            match = _TG_USER_ID_RE.search(entity.url)
            if match:
                user = await _fetch_user_by_id(bot, message.chat.id, int(match.group(1)))
                if user:
                    return user

        if entity.type == MessageEntityType.MENTION:
            username = text[entity.offset : entity.offset + entity.length]
            user = await _fetch_user_by_username(bot, message.chat.id, username)
            if user:
                return user

    return None


async def _extract_user_from_argument(
    argument: str, message: types.Message, bot: Bot
) -> types.User | None:
    id_match = _TG_USER_ID_RE.search(argument)
    if id_match:
        return await _fetch_user_by_id(bot, message.chat.id, int(id_match.group(1)))

    if argument.isdigit():
        return await _fetch_user_by_id(bot, message.chat.id, int(argument))

    link_match = _TME_USERNAME_RE.match(argument)
    if link_match:
        return await _fetch_user_by_username(bot, message.chat.id, link_match.group(1))

    if argument.startswith("@"):
        return await _fetch_user_by_username(bot, message.chat.id, argument[1:])

    if _USERNAME_RE.match(argument):
        return await _fetch_user_by_username(bot, message.chat.id, argument)

    return None


async def _fetch_user_by_id(
    bot: Bot, chat_id: int, user_id: int
) -> types.User | None:
    with suppress(TelegramBadRequest):
        member = await bot.get_chat_member(chat_id, user_id)
        if member.user and not member.user.is_bot:
            return member.user
    return None


async def _fetch_user_by_username(
    bot: Bot, chat_id: int, username: str
) -> types.User | None:
    normalized = username.strip().lstrip("@")
    if not normalized:
        return None

    chat_identifier = f"@{normalized}"

    with suppress(TelegramBadRequest):
        chat = await bot.get_chat(chat_identifier)
        if chat.type == ChatType.PRIVATE:
            user = await _fetch_user_by_id(bot, chat_id, chat.id)
            if user:
                return user
    return None


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
async def add_admin_command(
    message: types.Message, session: AsyncSession, bot: Bot
) -> None:
    target_user = await _extract_target_user(message, bot)

    if target_user is None:
        await message.reply(
            "Чтобы назначить администратора, ответьте командой /add_admin "
            "на сообщение нужного пользователя или укажите его @username/ID."
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
async def remove_admin_command(
    message: types.Message, session: AsyncSession, bot: Bot
) -> None:
    target_user = await _extract_target_user(message, bot)

    if target_user is None:
        await message.reply(
            "Чтобы снять права администратора, ответьте командой /remove_admin "
            "на сообщение нужного пользователя или укажите его @username/ID."
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
