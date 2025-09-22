from aiogram import F, Router, types
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy.ext.asyncio import AsyncSession

from database.orm_query import (
    orm_add_category,
    orm_delete_category,
    orm_get_categories,
    orm_update_category,
)
from kbds.inline import get_callback_btns

from .common import edit_or_send_message, get_admin_main_keyboard, send_category_menu


class CategoryAdd(StatesGroup):
    name = State()


class CategoryRename(StatesGroup):
    category = State()
    name = State()


class CategoryDelete(StatesGroup):
    category = State()


def register_category_handlers(router: Router) -> None:
    router.callback_query.register(show_category_menu, F.data == "admin_category")
    router.callback_query.register(
        start_category_add, StateFilter(None), F.data == "admin_add_category"
    )
    router.message.register(process_category_add, CategoryAdd.name, F.text)
    router.message.register(process_category_add_invalid, CategoryAdd.name)
    router.callback_query.register(
        start_category_rename, StateFilter(None), F.data == "admin_rename_category"
    )
    router.callback_query.register(
        choose_category_for_rename,
        CategoryRename.category,
        F.data.startswith("admin_rename_category_"),
    )
    router.message.register(process_category_rename, CategoryRename.name, F.text)
    router.message.register(process_category_rename_invalid, CategoryRename.name)
    router.callback_query.register(
        start_category_delete, StateFilter(None), F.data == "admin_delete_category"
    )
    router.callback_query.register(
        process_category_delete,
        CategoryDelete.category,
        F.data.startswith("admin_delete_category_"),
    )


async def show_category_menu(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await send_category_menu(callback.message)
    await callback.answer()


async def start_category_add(callback: types.CallbackQuery, state: FSMContext):
    await edit_or_send_message(
        callback.message,
        "Введите название новой категории",
        reply_markup=None,
    )
    await state.set_state(CategoryAdd.name)
    await callback.answer()


async def process_category_add(
    message: types.Message, state: FSMContext, session: AsyncSession
):
    name = message.text.strip()

    if not name:
        await message.answer("Название категории не может быть пустым. Введите заново.")
        return

    if len(name) > 150:
        await message.answer(
            "Название категории не должно превышать 150 символов. Введите заново."
        )
        return

    categories = await orm_get_categories(session)
    if any(category.name.casefold() == name.casefold() for category in categories):
        await message.answer("Категория с таким названием уже существует. Введите другое название.")
        return

    category = await orm_add_category(session, name)
    await message.answer(
        f'Категория "{category.name}" добавлена.',
        reply_markup=get_admin_main_keyboard(),
    )
    await state.clear()


async def process_category_add_invalid(message: types.Message):
    await message.answer("Введите текстовое название категории или напишите \"отмена\".")


async def start_category_rename(
    callback: types.CallbackQuery, state: FSMContext, session: AsyncSession
):
    categories = await orm_get_categories(session)
    if not categories:
        await edit_or_send_message(
            callback.message,
            "Категории отсутствуют. Добавьте новую категорию.",
            reply_markup=get_admin_main_keyboard(),
        )
        await callback.answer()
        return

    btns = {category.name: f"admin_rename_category_{category.id}" for category in categories}
    btns["⬅️ В меню категорий"] = "admin_category"
    await edit_or_send_message(
        callback.message,
        "Выберите категорию для переименования",
        reply_markup=get_callback_btns(btns=btns),
    )
    await state.set_state(CategoryRename.category)
    await callback.answer()


async def choose_category_for_rename(
    callback: types.CallbackQuery, state: FSMContext, session: AsyncSession
):
    category_id = int(callback.data.split("_")[-1])

    categories = await orm_get_categories(session)
    category = next((item for item in categories if item.id == category_id), None)
    if category is None:
        await callback.answer("Категория не найдена.", show_alert=True)
        return

    await state.update_data(category_id=category_id, old_name=category.name)
    await edit_or_send_message(
        callback.message,
        f'Введите новое название для категории "{category.name}"',
    )
    await state.set_state(CategoryRename.name)
    await callback.answer()


async def process_category_rename(
    message: types.Message, state: FSMContext, session: AsyncSession
):
    new_name = message.text.strip()

    if not new_name:
        await message.answer("Название категории не может быть пустым. Введите заново.")
        return

    if len(new_name) > 150:
        await message.answer(
            "Название категории не должно превышать 150 символов. Введите другое название."
        )
        return

    data = await state.get_data()
    category_id = data.get("category_id")
    old_name = data.get("old_name", "")

    if category_id is None:
        await message.answer(
            "Не удалось определить категорию для переименования. Начните заново.",
            reply_markup=get_admin_main_keyboard(),
        )
        await state.clear()
        return

    categories = await orm_get_categories(session)
    if any(
        category.id != category_id and category.name.casefold() == new_name.casefold()
        for category in categories
    ):
        await message.answer("Категория с таким названием уже существует. Введите другое название.")
        return

    updated = await orm_update_category(session, int(category_id), new_name)
    if not updated:
        await message.answer(
            "Не удалось переименовать категорию. Попробуйте позже.",
            reply_markup=get_admin_main_keyboard(),
        )
        await state.clear()
        return

    await message.answer(
        f'Категория "{old_name}" переименована в "{new_name}".',
        reply_markup=get_admin_main_keyboard(),
    )
    await state.clear()


async def process_category_rename_invalid(message: types.Message):
    await message.answer("Введите текстовое название категории или напишите \"отмена\".")


async def start_category_delete(
    callback: types.CallbackQuery, state: FSMContext, session: AsyncSession
):
    categories = await orm_get_categories(session)
    if not categories:
        await edit_or_send_message(
            callback.message,
            "Категории отсутствуют. Добавлять пока нечего удалять.",
            reply_markup=get_admin_main_keyboard(),
        )
        await callback.answer()
        return

    btns = {category.name: f"admin_delete_category_{category.id}" for category in categories}
    btns["⬅️ В меню категорий"] = "admin_category"
    await edit_or_send_message(
        callback.message,
        "Выберите категорию для удаления",
        reply_markup=get_callback_btns(btns=btns),
    )
    await state.set_state(CategoryDelete.category)
    await callback.answer()


async def process_category_delete(
    callback: types.CallbackQuery, state: FSMContext, session: AsyncSession
):
    category_id = int(callback.data.split("_")[-1])

    categories = await orm_get_categories(session)
    category = next((item for item in categories if item.id == category_id), None)
    if category is None:
        await callback.answer("Категория не найдена.", show_alert=True)
        return

    deleted = await orm_delete_category(session, category_id)

    if deleted:
        await callback.answer("Категория удалена")
        await edit_or_send_message(
            callback.message,
            f'Категория "{category.name}" удалена.',
            reply_markup=get_admin_main_keyboard(),
        )
    else:
        await callback.answer("Не удалось удалить категорию", show_alert=True)
        await edit_or_send_message(
            callback.message,
            "Не удалось удалить категорию. Попробуйте позже.",
            reply_markup=get_admin_main_keyboard(),
        )

    await state.clear()
