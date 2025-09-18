from aiogram import F, Router, types
from aiogram.filters import Command, StateFilter, or_f
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import ReplyKeyboardRemove

from sqlalchemy.ext.asyncio import AsyncSession

from database.orm_query import (
    orm_add_category,
    orm_add_product,
    orm_change_banner_image,
    orm_delete_category,
    orm_delete_product,
    orm_get_categories,
    orm_get_info_pages,
    orm_get_product,
    orm_get_products,
    orm_update_category,
    orm_update_product,
)

from filters.chat_types import ChatTypeFilter, IsAdmin

from kbds.inline import get_callback_btns


admin_router = Router()
admin_router.message.filter(ChatTypeFilter(["private"]), IsAdmin())


ADMIN_MAIN_BTNS = {
    "Добавить товар": "admin_add_product",
    "Ассортимент": "admin_catalog",
    "Добавить категорию": "admin_add_category",
    "Переименовать категорию": "admin_rename_category",
    "Удалить категорию": "admin_delete_category",
    "Добавить/Изменить баннер": "admin_banner",
}


def get_admin_main_keyboard() -> types.InlineKeyboardMarkup:
    return get_callback_btns(btns=ADMIN_MAIN_BTNS, sizes=(2, 2))


async def send_admin_menu(message: types.Message) -> None:
    await message.answer("Что хотите сделать?", reply_markup=get_admin_main_keyboard())

# Хендлер для выхода из админ-панели
@admin_router.message(Command("exit_admin"), IsAdmin())
async def exit_admin_mode(message: types.Message, state: FSMContext):
    await state.clear()  # Сброс состояния
    await message.answer("Вы вышли из админ-панели.", reply_markup=ReplyKeyboardRemove())

@admin_router.message(Command("admin"))
async def admin_features(message: types.Message):
    await send_admin_menu(message)


@admin_router.callback_query(F.data == "admin_menu")
async def show_admin_menu(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await send_admin_menu(callback.message)
    await callback.answer()


@admin_router.callback_query(F.data == 'admin_catalog')
async def show_categories(callback: types.CallbackQuery, session: AsyncSession):
    categories = await orm_get_categories(session)
    btns = {category.name: f'category_{category.id}' for category in categories}
    btns["⬅️ Админ меню"] = "admin_menu"
    await callback.message.answer("Выберите категорию", reply_markup=get_callback_btns(btns=btns))
    await callback.answer()


@admin_router.callback_query(F.data.startswith('category_'))
async def starring_at_product(callback: types.CallbackQuery, session: AsyncSession):
    category_id = callback.data.split('_')[-1]
    for product in await orm_get_products(session, int(category_id)):
        await callback.message.answer_photo(
            product.image,
            caption=f"<strong>{product.name}\
                    </strong>\n{product.description}\nСтоимость: {round(product.price, 2)}",
            reply_markup=get_callback_btns(
                btns={
                    "Удалить": f"delete_{product.id}",
                    "Изменить": f"change_{product.id}",
                },
                sizes=(2,)
            ),
        )
    await callback.answer()
    await callback.message.answer(
        "ОК, вот список товаров ⏫", reply_markup=get_admin_main_keyboard()
    )


@admin_router.callback_query(F.data.startswith("delete_"))
async def delete_product_callback(callback: types.CallbackQuery, session: AsyncSession):
    product_id = callback.data.split("_")[-1]
    await orm_delete_product(session, int(product_id))

    await callback.answer("Товар удален")
    await callback.message.answer("Товар удален!", reply_markup=get_admin_main_keyboard())


################# Микро FSM для загрузки/изменения баннеров ############################

class AddBanner(StatesGroup):
    image = State()

# Отправляем перечень информационных страниц бота и становимся в состояние отправки photo
@admin_router.callback_query(StateFilter(None), F.data == 'admin_banner')
async def prompt_banner_upload(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    pages_names = [page.name for page in await orm_get_info_pages(session)]
    await callback.message.answer(
        f"Отправьте фото баннера.\nВ описании укажите для какой страницы:\n{', '.join(pages_names)}"
    )
    await state.set_state(AddBanner.image)
    await callback.answer()

# Добавляем/изменяем изображение в таблице (там уже есть записанные страницы по именам:
# main, catalog, cart(для пустой корзины), about, payment, shipping
@admin_router.message(AddBanner.image, F.photo)
async def add_banner(message: types.Message, state: FSMContext, session: AsyncSession):
    image_id = message.photo[-1].file_id
    for_page = message.caption.strip()
    pages_names = [page.name for page in await orm_get_info_pages(session)]
    if for_page not in pages_names:
        await message.answer(f"Введите нормальное название страницы, например:\
                         \n{', '.join(pages_names)}")
        return
    await orm_change_banner_image(session, for_page, image_id,)
    await message.answer("Баннер добавлен/изменен.", reply_markup=get_admin_main_keyboard())
    await state.clear()

@admin_router.message(StateFilter("*"), Command("отмена"))
@admin_router.message(StateFilter("*"), F.text.casefold() == "отмена")
async def cancel_handler(message: types.Message, state: FSMContext) -> None:
    current_state = await state.get_state()
    if current_state is None:
        return
    if AddProduct.product_for_change:
        AddProduct.product_for_change = None
    await state.clear()
    await message.answer("Действия отменены", reply_markup=get_admin_main_keyboard())

# ловим некоррекный ввод
@admin_router.message(AddBanner.image)
async def add_banner2(message: types.Message, state: FSMContext):
    await message.answer("Отправьте фото баннера или отмена")

#########################################################################################


########################## Управление категориями ######################################


class CategoryAdd(StatesGroup):
    name = State()


class CategoryRename(StatesGroup):
    category = State()
    name = State()


class CategoryDelete(StatesGroup):
    category = State()


@admin_router.callback_query(StateFilter(None), F.data == "admin_add_category")
async def start_category_add(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer(
        "Введите название новой категории",
        reply_markup=types.ReplyKeyboardRemove(),
    )
    await state.set_state(CategoryAdd.name)
    await callback.answer()


@admin_router.message(CategoryAdd.name, F.text)
async def process_category_add(
    message: types.Message, state: FSMContext, session: AsyncSession
):
    name = message.text.strip()

    if not name:
        await message.answer("Название категории не может быть пустым. Введите заново.")
        return

    if len(name) > 150:
        await message.answer("Название категории не должно превышать 150 символов. Введите заново.")
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


@admin_router.message(CategoryAdd.name)
async def process_category_add_invalid(message: types.Message):
    await message.answer("Введите текстовое название категории или напишите \"отмена\".")


@admin_router.callback_query(StateFilter(None), F.data == "admin_rename_category")
async def start_category_rename(
    callback: types.CallbackQuery, state: FSMContext, session: AsyncSession
):
    categories = await orm_get_categories(session)
    if not categories:
        await callback.message.answer(
            "Категории отсутствуют. Добавьте новую категорию.",
            reply_markup=get_admin_main_keyboard(),
        )
        await callback.answer()
        return

    btns = {category.name: f"admin_rename_category_{category.id}" for category in categories}
    btns["⬅️ Админ меню"] = "admin_menu"
    await callback.message.answer(
        "Выберите категорию для переименования",
        reply_markup=get_callback_btns(btns=btns),
    )
    await state.set_state(CategoryRename.category)
    await callback.answer()


@admin_router.callback_query(CategoryRename.category, F.data.startswith("admin_rename_category_"))
async def choose_category_for_rename(
    callback: types.CallbackQuery, state: FSMContext, session: AsyncSession
):
    category_id = int(callback.data.split("_")[-1])

    categories = await orm_get_categories(session)
    category = next((item for item in categories if item.id == category_id), None)
    if category is None:
        await callback.answer("Категория не найдена.", show_alert=True)
        return

    await callback.message.edit_reply_markup()
    await state.update_data(category_id=category_id, old_name=category.name)
    await callback.message.answer(
        f'Введите новое название для категории "{category.name}"',
        reply_markup=types.ReplyKeyboardRemove(),
    )
    await state.set_state(CategoryRename.name)
    await callback.answer()


@admin_router.message(CategoryRename.name, F.text)
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


@admin_router.message(CategoryRename.name)
async def process_category_rename_invalid(message: types.Message):
    await message.answer("Введите текстовое название категории или напишите \"отмена\".")


@admin_router.callback_query(StateFilter(None), F.data == "admin_delete_category")
async def start_category_delete(
    callback: types.CallbackQuery, state: FSMContext, session: AsyncSession
):
    categories = await orm_get_categories(session)
    if not categories:
        await callback.message.answer(
            "Категории отсутствуют. Добавлять пока нечего удалять.",
            reply_markup=get_admin_main_keyboard(),
        )
        await callback.answer()
        return

    btns = {category.name: f"admin_delete_category_{category.id}" for category in categories}
    btns["⬅️ Админ меню"] = "admin_menu"
    await callback.message.answer(
        "Выберите категорию для удаления",
        reply_markup=get_callback_btns(btns=btns),
    )
    await state.set_state(CategoryDelete.category)
    await callback.answer()


@admin_router.callback_query(CategoryDelete.category, F.data.startswith("admin_delete_category_"))
async def process_category_delete(
    callback: types.CallbackQuery, state: FSMContext, session: AsyncSession
):
    category_id = int(callback.data.split("_")[-1])

    categories = await orm_get_categories(session)
    category = next((item for item in categories if item.id == category_id), None)
    if category is None:
        await callback.answer("Категория не найдена.", show_alert=True)
        return

    await callback.message.edit_reply_markup()
    deleted = await orm_delete_category(session, category_id)

    if deleted:
        await callback.answer("Категория удалена")
        await callback.message.answer(
            f'Категория "{category.name}" удалена.',
            reply_markup=get_admin_main_keyboard(),
        )
    else:
        await callback.answer("Не удалось удалить категорию", show_alert=True)
        await callback.message.answer(
            "Не удалось удалить категорию. Попробуйте позже.",
            reply_markup=get_admin_main_keyboard(),
        )

    await state.clear()


#########################################################################################



######################### FSM для дабавления/изменения товаров админом ###################

class AddProduct(StatesGroup):
    # Шаги состояний
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


# Становимся в состояние ожидания ввода name
@admin_router.callback_query(StateFilter(None), F.data.startswith("change_"))
async def change_product_callback(
    callback: types.CallbackQuery, state: FSMContext, session: AsyncSession
):
    product_id = callback.data.split("_")[-1]

    product_for_change = await orm_get_product(session, int(product_id))

    AddProduct.product_for_change = product_for_change

    await callback.answer()
    await prompt_product_name(callback.message, state)


# Становимся в состояние ожидания ввода name
async def prompt_product_name(message: types.Message, state: FSMContext) -> None:
    await message.answer(
        "Введите название товара", reply_markup=types.ReplyKeyboardRemove()
    )
    await state.set_state(AddProduct.name)


@admin_router.callback_query(StateFilter(None), F.data == "admin_add_product")
async def add_product_callback(callback: types.CallbackQuery, state: FSMContext):
    await prompt_product_name(callback.message, state)
    await callback.answer()


@admin_router.message(StateFilter(None), F.text == "Добавить товар")
async def add_product(message: types.Message, state: FSMContext):
    await prompt_product_name(message, state)


# Хендлер отмены и сброса состояния должен быть всегда именно здесь,
# после того, как только встали в состояние номер 1 (элементарная очередность фильтров)



# Вернутся на шаг назад (на прошлое состояние)
@admin_router.message(StateFilter("*"), Command("назад"))
@admin_router.message(StateFilter("*"), F.text.casefold() == "назад")
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


# Ловим данные для состояние name и потом меняем состояние на description
@admin_router.message(AddProduct.name, F.text)
async def add_name(message: types.Message, state: FSMContext):
    if message.text == "." and AddProduct.product_for_change:
        await state.update_data(name=AddProduct.product_for_change.name)
    else:
        # Здесь можно сделать какую либо дополнительную проверку
        # и выйти из хендлера не меняя состояние с отправкой соответствующего сообщения
        # например:
        if 4 >= len(message.text) >= 150:
            await message.answer(
                "Название товара не должно превышать 150 символов\nили быть менее 5ти символов. \n Введите заново"
            )
            return

        await state.update_data(name=message.text)
    await message.answer("Введите описание товара")
    await state.set_state(AddProduct.description)

# Хендлер для отлова некорректных вводов для состояния name
@admin_router.message(AddProduct.name)
async def add_name2(message: types.Message, state: FSMContext):
    await message.answer("Вы ввели не допустимые данные, введите текст названия товара")


# Ловим данные для состояние description и потом меняем состояние на price
@admin_router.message(AddProduct.description, F.text)
async def add_description(message: types.Message, state: FSMContext, session: AsyncSession):
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
    btns = {category.name : str(category.id) for category in categories}
    await message.answer("Выберите категорию", reply_markup=get_callback_btns(btns=btns))
    await state.set_state(AddProduct.category)

# Хендлер для отлова некорректных вводов для состояния description
@admin_router.message(AddProduct.description)
async def add_description2(message: types.Message, state: FSMContext):
    await message.answer("Вы ввели не допустимые данные, введите текст описания товара")


# Ловим callback выбора категории
@admin_router.callback_query(AddProduct.category)
async def category_choice(callback: types.CallbackQuery, state: FSMContext , session: AsyncSession):
    if int(callback.data) in [category.id for category in await orm_get_categories(session)]:
        await callback.answer()
        await state.update_data(category=callback.data)
        await callback.message.answer('Теперь введите цену товара.')
        await state.set_state(AddProduct.price)
    else:
        await callback.message.answer('Выберите катеорию из кнопок.')
        await callback.answer()

#Ловим любые некорректные действия, кроме нажатия на кнопку выбора категории
@admin_router.message(AddProduct.category)
async def category_choice2(message: types.Message, state: FSMContext):
    await message.answer("'Выберите катеорию из кнопок.'")


# Ловим данные для состояние price и потом меняем состояние на image
@admin_router.message(AddProduct.price, F.text)
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

# Хендлер для отлова некорректных ввода для состояния price
@admin_router.message(AddProduct.price)
async def add_price2(message: types.Message, state: FSMContext):
    await message.answer("Вы ввели не допустимые данные, введите стоимость товара")


# Ловим данные для состояние image и потом выходим из состояний
@admin_router.message(AddProduct.image, or_f(F.photo, F.text == "."))
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

# Ловим все прочее некорректное поведение для этого состояния
@admin_router.message(AddProduct.image)
async def add_image2(message: types.Message, state: FSMContext):
    await message.answer("Отправьте фото пищи")

