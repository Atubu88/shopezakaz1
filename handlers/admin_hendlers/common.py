from aiogram import types
from aiogram.exceptions import TelegramBadRequest

from kbds.inline import get_callback_btns

ADMIN_MAIN_BTNS = {
    "Добавить товар": "admin_add_product",
    "Ассортимент": "admin_catalog",
    "Категории": "admin_category",
    "Добавить/Изменить баннер": "admin_banner",
}

CATEGORY_MENU_BTNS = {
    "Добавить категорию": "admin_add_category",
    "Переименовать категорию": "admin_rename_category",
    "Удалить категорию": "admin_delete_category",
    "⬅️ Админ меню": "admin_menu",
}


def get_admin_main_keyboard() -> types.InlineKeyboardMarkup:
    return get_callback_btns(btns=ADMIN_MAIN_BTNS, sizes=(2, 2))


def get_category_menu_keyboard() -> types.InlineKeyboardMarkup:
    return get_callback_btns(btns=CATEGORY_MENU_BTNS, sizes=(1, 1, 1, 1))


def get_menu_text() -> str:
    return "Что хотите сделать?"


def get_category_menu_text() -> str:
    return "Выберите действие с категориями"


async def edit_or_send_message(
    message: types.Message,
    text: str,
    reply_markup: types.InlineKeyboardMarkup | None = None,
) -> types.Message:
    if reply_markup is None or isinstance(reply_markup, types.InlineKeyboardMarkup):
        try:
            return await message.edit_text(text, reply_markup=reply_markup)
        except TelegramBadRequest as e:
            if "message is not modified" in str(e).lower():
                return message
    return await message.answer(text, reply_markup=reply_markup)


async def send_admin_menu(message: types.Message) -> None:
    await edit_or_send_message(
        message,
        get_menu_text(),
        reply_markup=get_admin_main_keyboard(),
    )


async def send_category_menu(message: types.Message) -> None:
    await edit_or_send_message(
        message,
        get_category_menu_text(),
        reply_markup=get_category_menu_keyboard(),
    )
