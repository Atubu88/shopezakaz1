from aiogram import F, Router, types
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy.ext.asyncio import AsyncSession

from database.orm_query import orm_change_banner_image, orm_get_info_pages

from .common import edit_or_send_message, get_admin_main_keyboard


class AddBanner(StatesGroup):
    image = State()


def register_banner_handlers(router: Router) -> None:
    router.callback_query.register(
        prompt_banner_upload, StateFilter(None), F.data == "admin_banner"
    )
    router.message.register(add_banner, AddBanner.image, F.photo)
    router.message.register(add_banner_invalid, AddBanner.image)


async def prompt_banner_upload(
    callback: types.CallbackQuery, state: FSMContext, session: AsyncSession
):
    pages_names = [page.name for page in await orm_get_info_pages(session)]
    await edit_or_send_message(
        callback.message,
        (
            "Отправьте фото баннера.\n"
            "В описании укажите для какой страницы:\n"
            f"{', '.join(pages_names)}"
        ),
    )
    await state.set_state(AddBanner.image)
    await callback.answer()


async def add_banner(
    message: types.Message, state: FSMContext, session: AsyncSession
):
    image_id = message.photo[-1].file_id
    for_page = message.caption.strip()
    pages_names = [page.name for page in await orm_get_info_pages(session)]
    if for_page not in pages_names:
        await message.answer(
            "Введите нормальное название страницы, например:\n"
            f"{', '.join(pages_names)}"
        )
        return
    await orm_change_banner_image(
        session,
        for_page,
        image_id,
    )
    await message.answer(
        "Баннер добавлен/изменен.", reply_markup=get_admin_main_keyboard()
    )
    await state.clear()


async def add_banner_invalid(message: types.Message, state: FSMContext):
    await message.answer("Отправьте фото баннера или отмена")
