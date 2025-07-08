# order_processing.py
import re

from aiogram import Router, types
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, \
    ReplyKeyboardMarkup, FSInputFile
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.filters import StateFilter
from sqlalchemy.ext.asyncio import AsyncSession
from aiogram.types import ContentType

from handlers.menu_processing import carts, get_menu_content, main_menu
from handlers.user_private import start_cmd
from kbds.inline import get_user_cart



from database.orm_query import orm_get_user_carts

# Определяем состояния для процесса заказа
class OrderStates(StatesGroup):
    confirming_cart = State()
    level_3 = State()
    choosing_delivery = State()
    entering_address = State()
    confirming_address = State()
    choosing_payment = State()
    requesting_phone_number = State()  # Убедитесь, что это состояние существует
    confirming_order = State()

order_router = Router()

async def create_order_summary(session: AsyncSession, user_id: int):
    cart_items = await orm_get_user_carts(session, user_id)
    summary = "Ваш заказ:\n"
    total_cost = 0
    for item in cart_items:
        item_cost = item.product.price * item.quantity
        total_cost += item_cost
        summary += f"- {item.product.name}: {item.product.price}$ x {item.quantity} = {item_cost}$\n"
    summary += f"\nОбщая стоимость: {total_cost}$"
    return summary

# Хендлер для подтверждения корзины и выбора способа доставки
@order_router.callback_query(lambda c: c.data == 'start_order')
async def handle_start_order(callback_query: CallbackQuery, state: FSMContext, session: AsyncSession):
    user_id = callback_query.from_user.id
    await callback_query.message.delete()

    # Получение текстового описания заказа
    order_summary = await create_order_summary(session, user_id)

    # Установим состояние для подтверждения корзины
    await state.set_state(OrderStates.confirming_cart)

    # Создание клавиатуры для подтверждения корзины и выбора доставки
    delivery_options = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Подтвердить корзину", callback_data="confirm_cart")],
        [InlineKeyboardButton(text="Назад", callback_data="back_to_start")]
    ])

    await callback_query.message.answer(
        f"{order_summary}\n\nПодтвердите корзину или вернитесь для редактирования.",
        reply_markup=delivery_options
    )

# Обработчик для подтверждения корзины и перехода к выбору способа доставки
@order_router.callback_query(StateFilter(OrderStates.confirming_cart), lambda c: c.data == 'confirm_cart')
async def confirm_cart(callback_query: CallbackQuery, state: FSMContext):
    await callback_query.message.delete()
    await state.set_state(OrderStates.choosing_delivery)

    delivery_options = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Курьер", callback_data="choose_delivery_courier")],
        [InlineKeyboardButton(text="Самовывоз", callback_data="choose_delivery_pickup")],
        [InlineKeyboardButton(text="Назад", callback_data="back_to_cart")]
    ])

    await callback_query.message.answer("Выберите способ доставки:", reply_markup=delivery_options)

# Обработчик для выбора доставки курьером
@order_router.callback_query(StateFilter(OrderStates.choosing_delivery), lambda c: c.data == 'choose_delivery_courier')
async def handle_courier_delivery(callback_query: CallbackQuery, state: FSMContext):
    await callback_query.message.delete_reply_markup()  # Удаляем предыдущую клавиатуру
    await callback_query.message.delete()
    await state.set_state(OrderStates.entering_address)

    back_button = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Назад", callback_data="back_to_delivery_choice")]
    ])

    await callback_query.message.answer(
        "Пожалуйста, введите адрес доставки.",
        reply_markup=back_button
    )

# Обработчик для выбора самовывоза
# Хендлер для выбора доставки курьером
@order_router.callback_query(StateFilter(OrderStates.choosing_delivery), lambda c: c.data == 'choose_delivery_pickup')
async def handle_pickup_delivery(callback_query: CallbackQuery, state: FSMContext):
    await callback_query.message.delete()
    await state.set_state(OrderStates.choosing_payment)

    payment_options = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Оплата картой", callback_data="choose_payment_card")],
        [InlineKeyboardButton(text="Оплата наличными", callback_data="choose_payment_cash")],
        [InlineKeyboardButton(text="Назад", callback_data="back_to_delivery_choice")]  # Универсальный хендлер
    ])

    await callback_query.message.answer(
        "Вы выбрали самовывоз. Пожалуйста, выберите способ оплаты:",
        reply_markup=payment_options
    )

# Обработчик для ввода адреса доставки
@order_router.message(StateFilter(OrderStates.entering_address))
async def enter_address(message: types.Message, state: FSMContext):
    address = message.text
    await state.update_data(address=address)

    await state.set_state(OrderStates.confirming_address)

    confirm_markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Подтвердить адрес", callback_data="confirm_address")],
        [InlineKeyboardButton(text="Назад", callback_data="back_to_delivery_choice")]
    ])

    await message.answer(f"Вы указали адрес: {address}\nПодтвердите адрес или измените его.", reply_markup=confirm_markup)

# Обработчик для подтверждения адреса
@order_router.callback_query(StateFilter(OrderStates.confirming_address), lambda c: c.data == 'confirm_address')
async def confirm_address(callback_query: CallbackQuery, state: FSMContext):
    await callback_query.message.delete()
    await state.set_state(OrderStates.choosing_payment)

    payment_options = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Оплата картой", callback_data="choose_payment_card")],
        [InlineKeyboardButton(text="Оплата наличными", callback_data="choose_payment_cash")],
        [InlineKeyboardButton(text="Назад", callback_data="back_to_delivery_choice")]
    ])

    await callback_query.message.answer("Адрес подтвержден. Выберите способ оплаты:", reply_markup=payment_options)

# Обработчик для выбора способа оплаты
# Хендлер для запроса номера телефона вручную
# Хендлер для выбора способа оплаты
@order_router.callback_query(lambda c: c.data.startswith('choose_payment'))
async def choose_payment(callback_query: CallbackQuery, state: FSMContext):
    # Определение способа оплаты на основе данных из нажатой кнопки
    payment_method = "Картой" if callback_query.data == 'choose_payment_card' else "Наличными"

    # Сохранение способа оплаты в состоянии
    await state.update_data(payment_method=payment_method)

    # Уведомляем пользователя о выбранном способе оплаты
    await callback_query.message.answer(f"Вы выбрали способ оплаты: {payment_method}.")

    # Удаление предыдущей клавиатуры, чтобы избежать повторного отображения кнопки
    await callback_query.message.delete_reply_markup()

    # Переход к следующему шагу — запросу ввода номера телефона вручную
    await state.set_state(OrderStates.requesting_phone_number)

    # Сообщение пользователю с инструкцией ввести номер телефона вручную
    await callback_query.message.answer("Пожалуйста, введите ваш номер телефона вручную.")

# Хендлер для обработки ввода номера телефона вручную
# Хендлер для обработки ввода номера телефона вручную
@order_router.message(StateFilter(OrderStates.requesting_phone_number))
async def receive_phone_number(message: types.Message, state: FSMContext):
    phone_number = message.text.strip()  # Удаляем пробелы вокруг номера телефона

    # Проверка валидности номера телефона с использованием регулярных выражений
    if re.match(r"^\+?\d{10,15}$", phone_number):  # Проверяет формат номера телефона
        # Сохраняем номер телефона в данные состояния
        await state.update_data(phone_number=phone_number)

        # Подтверждение для пользователя
        await message.answer("Спасибо! Ваш номер телефона получен и сохранен.")

        # Переход к следующему шагу — подтверждению заказа
        await state.set_state(OrderStates.confirming_order)

        # Создание клавиатуры для подтверждения заказа
        confirm_order_markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Подтвердить заказ", callback_data="confirm_order")],
            [InlineKeyboardButton(text="Назад", callback_data="back_to_payment_choice")]
        ])

        await message.answer(
            "Вы выбрали способ оплаты. Подтвердите заказ или измените его.",
            reply_markup=confirm_order_markup
        )
    else:
        # Сообщение об ошибке, если введенный текст не является номером телефона
        await message.answer("Введен неверный номер телефона. Пожалуйста, введите номер телефона в формате +71234567890 или 81234567890.")
# Обработчик для подтверждения заказа
# Хендлер для подтверждения заказа и отправки уведомления администратору
@order_router.callback_query(StateFilter(OrderStates.confirming_order), lambda c: c.data == 'confirm_order')
async def confirm_order(callback_query: CallbackQuery, state: FSMContext, session: AsyncSession):
    await callback_query.message.delete()

    # Получение данных заказа из состояния
    data = await state.get_data()
    user_id = callback_query.from_user.id
    user_name = callback_query.from_user.full_name or callback_query.from_user.username
    user_profile = f"[{user_name}](tg://user?id={user_id})"  # Ссылка на профиль пользователя
    address = data.get('address', 'Самовывоз')  # Получаем адрес из состояния или используем "Самовывоз" по умолчанию
    phone_number = data.get('phone_number', 'Не указан')
    payment_method = data.get('payment_method', 'Не указан')  # Получаем способ оплаты из состояния

    # Получаем детали заказа
    order_summary = await create_order_summary(session, user_id)

    # Формируем сообщение для администратора
    admin_message = (
        f"Новый заказ от пользователя {user_profile}:\n"
        f"Адрес: {address}\n"
        f"Телефон: {phone_number}\n"
        f"Способ оплаты: {payment_method}\n"
        f"{order_summary}\n"
    )

    # Отправка уведомления администратору
    admin_chat_id = -1002231413484  # Замените на ID чата администратора
    await callback_query.bot.send_message(
        admin_chat_id,
        admin_message,
        parse_mode="Markdown"  # Используйте HTML, если предпочитаете другой формат
    )

    # Подтверждение для пользователя
    await callback_query.message.answer("Ваш заказ подтвержден и отправлен на обработку. Спасибо за покупку!")
    await state.clear()
# Хендлеры для кнопок "Назад"
#
#
# Пример хендлера, который возвращает в корзину

@order_router.callback_query(lambda c: c.data == 'back_to_start')
async def back_to_start(callback_query: CallbackQuery, state: FSMContext, session: AsyncSession):
    await callback_query.message.delete()

    # Сбрасываем состояние
    await state.clear()

    # Повторный вызов стартовой команды
    await start_cmd(callback_query.message, session)

@order_router.callback_query(lambda c: c.data == 'back_to_cart')
async def back_to_cart(callback_query: CallbackQuery, state: FSMContext, session: AsyncSession):
    # Вызовем хендлер для подтверждения корзины
    await handle_start_order(callback_query, state, session)



# Хендлер для кнопки "Назад" на этапе ввода адреса
@order_router.callback_query(lambda c: c.data == 'back_to_delivery_choice')
async def back_to_delivery_choice(callback_query: CallbackQuery, state: FSMContext):
    await callback_query.message.delete()
    await state.set_state(OrderStates.choosing_delivery)

    # Клавиатура для выбора способа доставки
    delivery_options = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Курьер", callback_data="choose_delivery_courier")],
        [InlineKeyboardButton(text="Самовывоз", callback_data="choose_delivery_pickup")],
        [InlineKeyboardButton(text="Назад", callback_data="back_to_cart")]
    ])

    await callback_query.message.answer("Выберите способ доставки:", reply_markup=delivery_options)
@order_router.callback_query(lambda c: c.data == 'back_to_payment_choice')
async def back_to_payment_choice(callback_query: CallbackQuery, state: FSMContext):
    await callback_query.message.delete()
    await state.set_state(OrderStates.choosing_payment)

    payment_options = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Оплата картой", callback_data="choose_payment_card")],
        [InlineKeyboardButton(text="Оплата наличными", callback_data="choose_payment_cash")],
        [InlineKeyboardButton(text="Назад", callback_data="back_to_delivery_choice")]
    ])

    await callback_query.message.answer("Выберите способ оплаты:", reply_markup=payment_options)
