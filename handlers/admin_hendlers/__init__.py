from aiogram import F, Router, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import ReplyKeyboardRemove

from filters.chat_types import ChatTypeFilter, IsAdmin

from .add_product import register_add_product_handlers
from .banner import register_banner_handlers
from .catalog import register_catalog_handlers
from .category import register_category_handlers
from .common import send_admin_menu

admin_router = Router()
admin_router.message.filter(ChatTypeFilter(["private"]), IsAdmin())


@admin_router.message(Command("exit_admin"), IsAdmin())
async def exit_admin_mode(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "Вы вышли из админ-панели.",
        reply_markup=ReplyKeyboardRemove(),
    )


@admin_router.message(Command("admin"))
async def admin_features(message: types.Message):
    await send_admin_menu(message)


@admin_router.callback_query(F.data == "admin_menu")
async def show_admin_menu(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await send_admin_menu(callback.message)
    await callback.answer()


register_add_product_handlers(admin_router)
register_catalog_handlers(admin_router)
register_category_handlers(admin_router)
register_banner_handlers(admin_router)
