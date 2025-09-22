from aiogram import F, Router, types
from aiogram.filters import Command, StateFilter, or_f
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from sqlalchemy.ext.asyncio import AsyncSession

from database.orm_query import (
    orm_add_product,
    orm_get_categories,
    orm_get_product,
    orm_update_product,
)
from kbds.inline import get_callback_btns

from .common import edit_or_send_message, get_admin_main_keyboard


class AddProduct(StatesGroup):
    name = State()
    description = State()
    category = State()
    price = State()
    image = State()

    product_for_change = None

    texts = {
        "AddProduct:name": "Введите название заново:",
        "AddProduct:description": "Введите описание заново:",
        "AddProduct:category": "Выберите категорию  заново ⬆️",
        "AddProduct:price": "Введите стоимость заново:",
        "AddProduct:image": "Этот стейт последний, поэтому...",
    }


async def prompt_product_name(message: types.Message, state: FSMContext) -> None:
    await edit_or_send_message(message, "Введите название товара")
    await state.set_state(AddProduct.name)


async def change_product_callback(
    callback: types.CallbackQuery, state: FSMContext, session: AsyncSession
):
    product_id = callback.data.split("_")[-1]
    product_for_change = await orm_get_product(session, int(product_id))

    AddProduct.product_for_change = product_for_change

    await callback.answer()
    await prompt_product_name(callback.message, state)


async def add_product_callback(callback: types.CallbackQuery, state: FSMContext):
    await prompt_product_name(callback.message, state)
    await callback.answer()


async def add_product(message: types.Message, state: FSMContext):
    await prompt_product_name(message, state)


async def cancel_handler(message: types.Message, state: FSMContext) -> None:
    current_state = await state.get_state()
    if current_state is None:
        return
    if AddProduct.product_for_change:
        AddProduct.product_for_change = None
    await state.clear()
    await message.answer("Действия отменены", reply_markup=get_admin_main_keyboard())


async def back_step_handler(message: types.Message, state: FSMContext) -> None:
    current_state = await state.get_state()

    if current_state == AddProduct.name:
        await message.answer(
            'Предидущего шага нет, или введите название товара или напишите "отмена"'
        )
        return

    previous = None
    for step in AddProduct.__all_states__:
        if step.state == current_state:
            await state.set_state(previous)
            await message.answer(
                f"Ок, вы вернулись к прошлому шагу \n {AddProduct.texts[previous.state]}"
            )
            return
        previous = step


async def add_name(message: types.Message, state: FSMContext):
    if message.text == "." and AddProduct.product_for_change:
        await state.update_data(name=AddProduct.product_for_change.name)
    else:
        if 4 >= len(message.text) >= 150:
            await message.answer(
                "Название товара не должно превышать 150 символов\nили быть менее 5ти символов. \n Введите заново"
            )
            return

        await state.update_data(name=message.text)
    await message.answer("Введите описание товара")
    await state.set_state(AddProduct.description)


async def add_name_invalid(message: types.Message, state: FSMContext):
    await message.answer("Вы ввели не допустимые данные, введите текст названия товара")


async def add_description(
    message: types.Message, state: FSMContext, session: AsyncSession
):
    if message.text == "." and AddProduct.product_for_change:
        await state.update_data(description=AddProduct.product_for_change.description)
    else:
        if 4 >= len(message.text):
            await message.answer(
                "Слишком короткое описание. \n Введите заново"
            )
            return
        await state.update_data(description=message.text)

    categories = await orm_get_categories(session)
    btns = {category.name: str(category.id) for category in categories}
    await message.answer("Выберите категорию", reply_markup=get_callback_btns(btns=btns))
    await state.set_state(AddProduct.category)


async def add_description_invalid(message: types.Message, state: FSMContext):
    await message.answer(
        "Вы ввели не допустимые данные, введите текст описания товара"
    )


async def category_choice(
    callback: types.CallbackQuery, state: FSMContext, session: AsyncSession
):
    if int(callback.data) in [category.id for category in await orm_get_categories(session)]:
        await callback.answer()
        await state.update_data(category=callback.data)
        await edit_or_send_message(callback.message, "Теперь введите цену товара.")
        await state.set_state(AddProduct.price)
    else:
        await callback.answer("Выберите категорию из кнопок.", show_alert=True)


async def category_choice_invalid(message: types.Message, state: FSMContext):
    await message.answer("'Выберите категорию из кнопок.'")


async def add_price(message: types.Message, state: FSMContext):
    if message.text == "." and AddProduct.product_for_change:
        await state.update_data(price=AddProduct.product_for_change.price)
    else:
        try:
            float(message.text)
        except ValueError:
            await message.answer("Введите корректное значение цены")
            return

        await state.update_data(price=message.text)
    await message.answer("Загрузите изображение товара")
    await state.set_state(AddProduct.image)


async def add_price_invalid(message: types.Message, state: FSMContext):
    await message.answer("Вы ввели не допустимые данные, введите стоимость товара")


async def add_image(message: types.Message, state: FSMContext, session: AsyncSession):
    if message.text and message.text == "." and AddProduct.product_for_change:
        await state.update_data(image=AddProduct.product_for_change.image)

    elif message.photo:
        await state.update_data(image=message.photo[-1].file_id)
    else:
        await message.answer("Отправьте фото пищи")
        return
    data = await state.get_data()
    try:
        if AddProduct.product_for_change:
            await orm_update_product(session, AddProduct.product_for_change.id, data)
        else:
            await orm_add_product(session, data)
        await message.answer("Товар добавлен/изменен", reply_markup=get_admin_main_keyboard())
        await state.clear()

    except Exception as e:
        await message.answer(
            f"Ошибка: \n{str(e)}\nОбратись к программеру, он опять денег хочет",
            reply_markup=get_admin_main_keyboard(),
        )
        await state.clear()

    AddProduct.product_for_change = None


async def add_image_invalid(message: types.Message, state: FSMContext):
    await message.answer("Отправьте фото пищи")


def register_add_product_handlers(router: Router) -> None:
    router.callback_query.register(
        change_product_callback, StateFilter(None), F.data.startswith("change_")
    )
    router.callback_query.register(
        add_product_callback, StateFilter(None), F.data == "admin_add_product"
    )
    router.message.register(
        add_product,
        StateFilter(None),
        F.text == "Добавить товар",
    )
    router.message.register(
        cancel_handler,
        StateFilter("*"),
        Command("отмена"),
    )
    router.message.register(
        cancel_handler,
        StateFilter("*"),
        F.text.casefold() == "отмена",
    )
    router.message.register(
        back_step_handler,
        StateFilter("*"),
        Command("назад"),
    )
    router.message.register(
        back_step_handler,
        StateFilter("*"),
        F.text.casefold() == "назад",
    )
    router.message.register(add_name, AddProduct.name, F.text)
    router.message.register(add_name_invalid, AddProduct.name)
    router.message.register(add_description, AddProduct.description, F.text)
    router.message.register(add_description_invalid, AddProduct.description)
    router.callback_query.register(category_choice, AddProduct.category)
    router.message.register(category_choice_invalid, AddProduct.category)
    router.message.register(add_price, AddProduct.price, F.text)
    router.message.register(add_price_invalid, AddProduct.price)
    router.message.register(
        add_image,
        AddProduct.image,
        or_f(F.photo, F.text == "."),
    )
    router.message.register(add_image_invalid, AddProduct.image)
