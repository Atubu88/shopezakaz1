from __future__ import annotations

from contextlib import suppress
from decimal import Decimal, ROUND_HALF_UP

from aiogram import Bot, F, Router, types
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

from sqlalchemy.ext.asyncio import AsyncSession

from database.orm_query import orm_get_user_carts
from filters.chat_types import ChatTypeFilter
from handlers.menu_processing import get_menu_content
from kbds.inline import MenuCallBack


order_router = Router()
order_router.message.filter(ChatTypeFilter(["private"]))
order_router.callback_query.filter(F.message.chat.type == "private")


class OrderState(StatesGroup):
    """Состояния оформления заказа."""

    review = State()
    waiting_full_name = State()
    waiting_postal_code = State()
    waiting_phone = State()
    confirm = State()


def _to_decimal(value: object) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def format_money(value: object) -> str:
    normalized = _to_decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    text = format(normalized, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def build_cart_summary(carts: list) -> tuple[list[str], Decimal]:
    lines: list[str] = []
    total = Decimal("0")
    for idx, cart in enumerate(carts, start=1):
        price = _to_decimal(cart.product.price)
        subtotal = price * cart.quantity
        total += subtotal
        lines.append(
            (
                f"{idx}. {cart.product.name} — "
                f"{format_money(price)}$ × {cart.quantity} = {format_money(subtotal)}$"
            )
        )
    return lines, total


def build_cart_block(lines: list[str]) -> str:
    if not lines:
        return "Корзина пуста."
    return "\n".join(f"• {line}" for line in lines)


def build_review_text(cart_lines: list[str], total_text: str) -> str:
    cart_text = build_cart_block(cart_lines)
    return (
        "<strong>Оформление заказа</strong>\n\n"
        "Проверьте содержимое корзины перед оформлением.\n\n"
        f"<strong>Корзина:</strong>\n{cart_text}\n\n"
        f"<strong>Итого:</strong> {total_text}$\n\n"
        "Нажмите «Подтвердить», чтобы продолжить, или «Назад», чтобы вернуться."
    )


def get_confirmation_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Подтвердить", callback_data="order_confirm")
    builder.button(text="Назад", callback_data="order_back_to_cart")
    builder.adjust(2)
    return builder.as_markup()


def get_back_keyboard(callback_data: str = "order_back_to_cart") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Назад", callback_data=callback_data)
    builder.adjust(1)
    return builder.as_markup()


def get_final_review_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Отправить заказ", callback_data="order_submit")
    builder.button(text="Назад", callback_data="order_back_to_phone")
    builder.button(
        text="На главную 🏠",
        callback_data=MenuCallBack(level=0, menu_name="main").pack(),
    )
    builder.adjust(1, 1, 1)
    return builder.as_markup()


def get_completed_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text="На главную 🏠",
        callback_data=MenuCallBack(level=0, menu_name="main").pack(),
    )
    builder.button(
        text="Каталог 🛍️",
        callback_data=MenuCallBack(level=1, menu_name="catalog").pack(),
    )
    builder.adjust(1, 1)
    return builder.as_markup()


def get_contact_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📱 Отправить контакт", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
        selective=True,
    )


def is_valid_full_name(full_name: str) -> bool:
    parts = [part for part in full_name.replace("\xa0", " ").split() if part]
    return len(parts) >= 2


def is_valid_postal_code(postal_code: str) -> bool:
    digits = postal_code.strip().replace(" ", "")
    return digits.isdigit() and len(digits) in {5, 6}


def normalize_phone_number(raw: str) -> str | None:
    raw = raw.strip()
    if not raw:
        return None

    digits = "".join(filter(str.isdigit, raw))
    if not digits:
        return None

    if raw.startswith("+"):
        normalized = "+" + digits
    elif len(digits) == 11 and digits.startswith("8"):
        normalized = "+7" + digits[1:]
    elif len(digits) == 10:
        normalized = "+7" + digits
    else:
        normalized = "+" + digits

    digits_only = "".join(filter(str.isdigit, normalized))
    if not (10 <= len(digits_only) <= 15):
        return None

    return normalized


def pretty_phone_number(phone: str) -> str:
    digits = "".join(filter(str.isdigit, phone))
    if phone.startswith("+7") and len(digits) == 11:
        return (
            f"+7 {digits[1:4]} {digits[4:7]} {digits[7:9]} {digits[9:11]}"
        )
    return phone


async def cleanup_contact_state(
    bot: Bot, chat_id: int, data: dict
) -> None:
    # Удаляем сообщение с просьбой отправить контакт, если оно есть
    prompt_id = data.get("contact_prompt_message_id")
    if prompt_id:
        with suppress(TelegramBadRequest):
            await bot.delete_message(chat_id, prompt_id)

    # Убираем клавиатуру, если она активна
    if data.get("contact_keyboard_active"):
        try:
            removal = await bot.send_message(
                chat_id,
                ".",  # минимальный текст, чтобы Telegram принял
                reply_markup=ReplyKeyboardRemove()
            )
            with suppress(TelegramBadRequest):
                await bot.delete_message(chat_id, removal.message_id)
        except TelegramBadRequest:
            pass




async def edit_order_message(
    bot: types.Bot,
    chat_id: int,
    message_id: int,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> None:
    try:
        await bot.edit_message_caption(
            chat_id=chat_id,
            message_id=message_id,
            caption=text,
            reply_markup=reply_markup,
        )
    except TelegramBadRequest as error:
        error_text = str(error).lower()
        if "message is not modified" in error_text:
            return
        try:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=text,
                reply_markup=reply_markup,
            )
        except TelegramBadRequest as inner_error:
            if "message is not modified" not in str(inner_error).lower():
                raise inner_error


async def remove_user_message(message: types.Message) -> None:
    with suppress(TelegramBadRequest):
        await message.delete()


def order_summary_text(data: dict) -> str:
    cart_lines: list[str] = data.get("cart_lines", [])
    cart_block = build_cart_block(cart_lines)
    total = data.get("cart_total", "0")
    full_name = data.get("full_name") or "—"
    postal_code = data.get("postal_code") or "—"
    phone = data.get("phone") or "—"

    return (
        "<strong>Проверьте данные заказа</strong>\n\n"
        f"ФИО: {full_name}\n"
        f"Индекс: {postal_code}\n"
        f"Телефон: {phone}\n\n"
        f"<strong>Корзина:</strong>\n{cart_block}\n\n"
        f"<strong>Итого:</strong> {total}$"
    )


def completion_text(data: dict) -> str:
    summary = order_summary_text(data)
    return (
        "<strong>Заказ оформлен!</strong>\n\n"
        f"{summary}\n\n"
        "Наш менеджер свяжется с вами для подтверждения."
    )


async def get_message_context(state: FSMContext) -> tuple[int, int]:
    data = await state.get_data()
    chat_id = data.get("order_chat_id")
    message_id = data.get("order_message_id")
    if chat_id is None or message_id is None:
        raise RuntimeError("Order message context is missing in FSM state.")
    return chat_id, message_id


@order_router.callback_query(F.data == "start_order")
async def start_order(
    callback: types.CallbackQuery, state: FSMContext, session: AsyncSession
):
    if not callback.message or callback.message.chat.type != "private":
        await callback.answer()
        return

    data = await state.get_data()
    await cleanup_contact_state(callback.message.bot, callback.message.chat.id, data)
    await state.clear()

    carts = await orm_get_user_carts(session, callback.from_user.id)
    if not carts:
        await callback.answer("Ваша корзина пуста.", show_alert=True)
        return

    cart_lines, total = build_cart_summary(carts)
    total_text = format_money(total)
    caption = build_review_text(cart_lines, total_text)

    await edit_order_message(
        callback.message.bot,
        callback.message.chat.id,
        callback.message.message_id,
        caption,
        get_confirmation_keyboard(),
    )

    await state.set_state(OrderState.review)
    await state.update_data(
        order_chat_id=callback.message.chat.id,
        order_message_id=callback.message.message_id,
        cart_lines=cart_lines,
        cart_total=total_text,
    )

    await callback.answer()


@order_router.callback_query(OrderState.review, F.data == "order_confirm")
async def confirm_cart(callback: types.CallbackQuery, state: FSMContext):
    chat_id, message_id = await get_message_context(state)
    text = (
        "<strong>Шаг 1 из 3</strong>\n\n"
        "Введите ФИО получателя.\n"
        "Например: Иванов Иван Иванович."
    )

    await edit_order_message(
        callback.message.bot,
        chat_id,
        message_id,
        text,
        get_back_keyboard("order_back_to_review"),
    )

    await state.set_state(OrderState.waiting_full_name)
    await callback.answer()


@order_router.callback_query(OrderState.waiting_full_name, F.data == "order_back_to_review")
async def back_to_review(callback: types.CallbackQuery, state: FSMContext):
    if not callback.message or callback.message.chat.type != "private":
        await callback.answer()
        return

    chat_id, message_id = await get_message_context(state)
    data = await state.get_data()
    cart_lines = data.get("cart_lines", [])
    total_text = data.get("cart_total", "0")
    caption = build_review_text(cart_lines, total_text)

    await edit_order_message(
        callback.message.bot,
        chat_id,
        message_id,
        caption,
        get_confirmation_keyboard(),
    )

    await state.set_state(OrderState.review)
    await state.update_data(
        full_name=None,
        postal_code=None,
        phone=None,
        phone_normalized=None,
    )
    await callback.answer()


@order_router.callback_query(F.data == "order_back_to_cart")
async def return_to_cart(
    callback: types.CallbackQuery, state: FSMContext, session: AsyncSession
):
    if not callback.message or callback.message.chat.type != "private":
        await callback.answer()
        return

    data = await state.get_data()
    await cleanup_contact_state(callback.message.bot, callback.message.chat.id, data)
    await state.clear()

    media, reply_markup = await get_menu_content(
        session,
        level=3,
        menu_name="cart",
        page=1,
        product_id=None,
        user_id=callback.from_user.id,
    )

    async def edit_cart_as_text() -> None:
        caption = getattr(media, "caption", None)
        if caption:
            try:
                await callback.message.edit_text(caption, reply_markup=reply_markup)
            except TelegramBadRequest as error:
                if "message is not modified" not in str(error).lower():
                    raise
        else:
            try:
                await callback.message.edit_reply_markup(reply_markup=reply_markup)
            except TelegramBadRequest as error:
                if "message is not modified" not in str(error).lower():
                    raise

    if callback.message.text is not None:
        await edit_cart_as_text()
    else:
        try:
            await callback.message.edit_media(media=media, reply_markup=reply_markup)
        except TelegramBadRequest as error:
            lower_error = str(error).lower()
            if "message is not modified" in lower_error:
                pass
            elif (
                "message content type is not supported" in lower_error
                or "caption is too long" in lower_error
            ):
                await edit_cart_as_text()
            else:
                raise
    await callback.answer("Возврат в корзину")


@order_router.callback_query(OrderState.waiting_postal_code, F.data == "order_back_to_full_name")
async def back_to_full_name(callback: types.CallbackQuery, state: FSMContext):
    if not callback.message or callback.message.chat.type != "private":
        await callback.answer()
        return

    chat_id, message_id = await get_message_context(state)
    await edit_order_message(
        callback.message.bot,
        chat_id,
        message_id,
        (
            "<strong>Шаг 1 из 3</strong>\n\n"
            "Введите ФИО получателя.\n"
            "Например: Иванов Иван Иванович."
        ),
        get_back_keyboard("order_back_to_review"),
    )

    await state.set_state(OrderState.waiting_full_name)
    await state.update_data(
        postal_code=None,
        phone=None,
        phone_normalized=None,
    )
    await callback.answer()


@order_router.callback_query(OrderState.waiting_phone, F.data == "order_back_to_postal_code")
async def back_to_postal_code(callback: types.CallbackQuery, state: FSMContext):
    if not callback.message or callback.message.chat.type != "private":
        await callback.answer()
        return

    data = await state.get_data()
    await cleanup_contact_state(callback.message.bot, callback.message.chat.id, data)
    await state.update_data(
        contact_keyboard_active=False,
        contact_prompt_message_id=None,
        phone=None,
        phone_normalized=None,
    )

    chat_id, message_id = await get_message_context(state)
    await edit_order_message(
        callback.message.bot,
        chat_id,
        message_id,
        (
            "<strong>Шаг 2 из 3</strong>\n\n"
            "Введите почтовый индекс (5–6 цифр)."
        ),
        get_back_keyboard("order_back_to_full_name"),
    )

    await state.set_state(OrderState.waiting_postal_code)
    await callback.answer()


@order_router.callback_query(OrderState.confirm, F.data == "order_back_to_phone")
async def back_to_phone(callback: types.CallbackQuery, state: FSMContext):
    if not callback.message or callback.message.chat.type != "private":
        await callback.answer()
        return

    data = await state.get_data()
    await cleanup_contact_state(callback.message.bot, callback.message.chat.id, data)

    chat_id, message_id = await get_message_context(state)
    await edit_order_message(
        callback.message.bot,
        chat_id,
        message_id,
        (
            "<strong>Шаг 3 из 3</strong>\n\n"
            "Отправьте номер телефона.\n"
            "Вы можете поделиться контактом кнопкой ниже или ввести номер вручную."
        ),
        get_back_keyboard("order_back_to_postal_code"),
    )

    prompt = await callback.message.answer(
        "Поделитесь контактом кнопкой ниже или введите номер вручную.",
        reply_markup=get_contact_keyboard(),
    )

    await state.set_state(OrderState.waiting_phone)
    await state.update_data(
        contact_prompt_message_id=prompt.message_id,
        contact_keyboard_active=True,
        phone=None,
        phone_normalized=None,
    )
    await callback.answer()


@order_router.message(OrderState.waiting_full_name, F.text)
async def process_full_name(message: types.Message, state: FSMContext):
    full_name = message.text.strip()
    if not is_valid_full_name(full_name):
        chat_id, message_id = await get_message_context(state)
        await edit_order_message(
            message.bot,
            chat_id,
            message_id,
            (
                "<strong>Шаг 1 из 3</strong>\n\n"
                "Пожалуйста, укажите корректное ФИО получателя.\n"
                "Например: Иванов Иван Иванович."
            ),
            get_back_keyboard("order_back_to_review"),
        )
        await remove_user_message(message)
        return

    await state.update_data(full_name=full_name)
    chat_id, message_id = await get_message_context(state)

    await edit_order_message(
        message.bot,
        chat_id,
        message_id,
            (
                "<strong>Шаг 2 из 3</strong>\n\n"
                "Введите почтовый индекс (5–6 цифр)."
            ),
            get_back_keyboard("order_back_to_full_name"),
        )

    await state.set_state(OrderState.waiting_postal_code)
    await remove_user_message(message)


@order_router.message(OrderState.waiting_postal_code, F.text)
async def process_postal_code(message: types.Message, state: FSMContext):
    postal_code = message.text.strip()
    if not is_valid_postal_code(postal_code):
        chat_id, message_id = await get_message_context(state)
        await edit_order_message(
            message.bot,
            chat_id,
            message_id,
            (
                "<strong>Шаг 2 из 3</strong>\n\n"
                "Индекс должен состоять из 5–6 цифр. Попробуйте снова."
            ),
            get_back_keyboard("order_back_to_full_name"),
        )
        await remove_user_message(message)
        return

    await state.update_data(postal_code=postal_code)
    chat_id, message_id = await get_message_context(state)

    await edit_order_message(
        message.bot,
        chat_id,
        message_id,
            (
                "<strong>Шаг 3 из 3</strong>\n\n"
                "Отправьте номер телефона.\n"
                "Вы можете поделиться контактом кнопкой ниже или ввести номер вручную."
            ),
            get_back_keyboard("order_back_to_postal_code"),
        )

    prompt = await message.answer(
        "Поделитесь контактом кнопкой ниже или введите номер вручную.",
        reply_markup=get_contact_keyboard(),
    )

    await state.set_state(OrderState.waiting_phone)
    await state.update_data(
        contact_prompt_message_id=prompt.message_id,
        contact_keyboard_active=True,
    )

    await remove_user_message(message)


async def finalize_phone_step(message: types.Message, state: FSMContext, phone: str) -> None:
    normalized = normalize_phone_number(phone)
    if not normalized:
        chat_id, message_id = await get_message_context(state)
        await edit_order_message(
            message.bot,
            chat_id,
            message_id,
            (
                "<strong>Шаг 3 из 3</strong>\n\n"
                "Не удалось распознать номер телефона. Попробуйте снова."
            ),
            get_back_keyboard("order_back_to_postal_code"),
        )
        await remove_user_message(message)
        return

    pretty = pretty_phone_number(normalized)
    await state.update_data(phone=pretty, phone_normalized=normalized)

    data = await state.get_data()
    await cleanup_contact_state(message.bot, message.chat.id, data)
    await state.update_data(contact_keyboard_active=False, contact_prompt_message_id=None)

    chat_id, message_id = await get_message_context(state)
    summary = order_summary_text(await state.get_data())

    await edit_order_message(
        message.bot,
        chat_id,
        message_id,
        summary + "\n\nЕсли все верно, отправьте заказ.",
        get_final_review_keyboard(),
    )

    await state.set_state(OrderState.confirm)
    await remove_user_message(message)


@order_router.message(OrderState.waiting_phone, F.contact)
async def process_contact(message: types.Message, state: FSMContext):
    contact = message.contact
    if contact.user_id and contact.user_id != message.from_user.id:
        chat_id, message_id = await get_message_context(state)
        await edit_order_message(
            message.bot,
            chat_id,
            message_id,
            (
                "<strong>Шаг 3 из 3</strong>\n\n"
                "Можно отправлять только свой контакт. Попробуйте снова."
            ),
            get_back_keyboard("order_back_to_postal_code"),
        )
        await remove_user_message(message)
        return

    await finalize_phone_step(message, state, contact.phone_number)


@order_router.message(OrderState.waiting_phone, F.text)
async def process_manual_phone(message: types.Message, state: FSMContext):
    await finalize_phone_step(message, state, message.text)


@order_router.callback_query(OrderState.confirm, F.data == "order_submit")
async def submit_order(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    chat_id, message_id = await get_message_context(state)

    text = completion_text(data)

    await edit_order_message(
        callback.message.bot,
        chat_id,
        message_id,
        text,
        get_completed_keyboard(),
    )

    await callback.answer("Заказ отправлен! Мы свяжемся с вами в ближайшее время.")
    await state.clear()

