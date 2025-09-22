from aiogram import F, Router, types
from sqlalchemy.ext.asyncio import AsyncSession

from database.orm_query import orm_delete_product, orm_get_categories, orm_get_products
from kbds.inline import get_callback_btns

from .common import edit_or_send_message, get_admin_main_keyboard


def register_catalog_handlers(router: Router) -> None:
    router.callback_query.register(show_categories, F.data == "admin_catalog")
    router.callback_query.register(show_products, F.data.startswith("category_"))
    router.callback_query.register(delete_product_callback, F.data.startswith("delete_"))


async def show_categories(callback: types.CallbackQuery, session: AsyncSession):
    categories = await orm_get_categories(session)
    btns = {category.name: f"category_{category.id}" for category in categories}
    btns["⬅️ Админ меню"] = "admin_menu"
    await edit_or_send_message(
        callback.message,
        "Выберите категорию",
        reply_markup=get_callback_btns(btns=btns),
    )
    await callback.answer()


async def show_products(callback: types.CallbackQuery, session: AsyncSession):
    category_id = callback.data.split("_")[-1]
    for product in await orm_get_products(session, int(category_id)):
        details_line = (
            f'<a href="{product.details_url}">Подробнее</a>'
            if getattr(product, "details_url", None)
            else (product.description or "")
        )
        caption_lines = [f"<strong>{product.name}</strong>"]
        if details_line:
            caption_lines.append(details_line)
        caption_lines.append(f"Стоимость: {round(product.price, 2)}")

        await callback.message.answer_photo(
            product.image,
            caption="\n".join(caption_lines),
            reply_markup=get_callback_btns(
                btns={
                    "Удалить": f"delete_{product.id}",
                    "Изменить": f"change_{product.id}",
                },
                sizes=(2,),
            ),
        )
    await callback.answer()
    await edit_or_send_message(
        callback.message,
        "ОК, вот список товаров ⏫",
        reply_markup=get_admin_main_keyboard(),
    )


async def delete_product_callback(callback: types.CallbackQuery, session: AsyncSession):
    product_id = callback.data.split("_")[-1]
    await orm_delete_product(session, int(product_id))

    await callback.answer("Товар удален")
    await edit_or_send_message(
        callback.message,
        "Товар удален!",
        reply_markup=get_admin_main_keyboard(),
    )
