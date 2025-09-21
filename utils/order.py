from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Awaitable, Callable, Mapping, Sequence

from utils.money import format_money, to_decimal


@dataclass(slots=True)
class CustomerData:
    full_name: str
    postal_code: str
    phone_display: str
    phone_value: str

    @classmethod
    def from_state(cls, data: Mapping[str, object]) -> "CustomerData":
        full_name = str(data.get("full_name") or "").strip()
        postal_code = str(data.get("postal_code") or "").strip()
        phone_display = str(data.get("phone") or "").strip()
        phone_normalized = str(data.get("phone_normalized") or "").strip()
        phone_value = phone_normalized or phone_display
        return cls(full_name, postal_code, phone_display, phone_value)

    @property
    def is_complete(self) -> bool:
        return all((self.full_name, self.postal_code, self.phone_value))

    @property
    def phone_for_display(self) -> str:
        return self.phone_display or self.phone_value


@dataclass(slots=True)
class CartItemPayload:
    product_id: int
    price: Decimal
    quantity: int
    name: str

    def to_dict(self) -> dict[str, object]:
        return {
            "product_id": self.product_id,
            "price": str(self.price),
            "quantity": self.quantity,
            "name": self.name,
        }


@dataclass(slots=True)
class CartData:
    lines: tuple[str, ...]
    items: tuple[CartItemPayload, ...]
    total: Decimal

    @property
    def total_text(self) -> str:
        return format_money(self.total)

    @property
    def items_payload(self) -> list[dict[str, object]]:
        return [item.to_dict() for item in self.items]

    def lines_for_display(self) -> list[str]:
        return list(self.lines)

    @classmethod
    def from_state(cls, data: Mapping[str, object]) -> "CartData | None":
        raw_lines = data.get("cart_lines")
        if not isinstance(raw_lines, (list, tuple)):
            return None
        lines_tuple = tuple(str(line) for line in raw_lines if line is not None)
        if not lines_tuple:
            return None

        raw_items = data.get("cart_items")
        if not isinstance(raw_items, (list, tuple)):
            return None
        items: list[CartItemPayload] = []
        for entry in raw_items:
            item = _parse_cart_item(entry)
            if item is None:
                return None
            items.append(item)
        if not items:
            return None

        total_raw = data.get("cart_total")
        if total_raw is None:
            return None
        try:
            total = Decimal(str(total_raw))
        except (InvalidOperation, ValueError):
            return None

        return cls(lines_tuple, tuple(items), total)

    @classmethod
    def from_carts(cls, carts: Sequence) -> "CartData":
        lines: list[str] = []
        items: list[CartItemPayload] = []
        total = Decimal("0")

        for idx, cart in enumerate(carts, start=1):
            price = to_decimal(cart.product.price)
            quantity = int(cart.quantity)
            subtotal = price * quantity
            total += subtotal
            name = str(cart.product.name)
            lines.append(
                (
                    f"{idx}. {name} — {format_money(price)}$ "
                    f"× {quantity} = {format_money(subtotal)}$"
                )
            )
            items.append(
                CartItemPayload(
                    product_id=int(cart.product_id),
                    price=price,
                    quantity=quantity,
                    name=name,
                )
            )

        return cls(tuple(lines), tuple(items), total)


def _parse_cart_item(entry: object) -> CartItemPayload | None:
    if not isinstance(entry, Mapping):
        return None
    try:
        product_id = int(entry["product_id"])
        quantity = int(entry["quantity"])
        price = Decimal(str(entry["price"]))
        name = str(entry["name"])
    except (KeyError, TypeError, ValueError, InvalidOperation):
        return None
    return CartItemPayload(product_id, price, quantity, name)


async def ensure_cart_data(
    state_data: Mapping[str, object],
    fetch_carts: Callable[[], Awaitable[Sequence]],
) -> CartData | None:
    state_cart = CartData.from_state(state_data)
    if state_cart is not None:
        return state_cart

    carts = await fetch_carts()
    if not carts:
        return None
    return CartData.from_carts(carts)


def build_admin_notification(order_id: int, customer: CustomerData, cart: CartData) -> str:
    items_block = "\n".join(f"🛍️ {line}" for line in cart.lines) if cart.lines else "—"
    return (
        f"📦 <strong>Новый заказ №{order_id}</strong>\n"
        f"👤 <strong>ФИО:</strong> {customer.full_name}\n"
        f"📮 <strong>Индекс:</strong> {customer.postal_code}\n"
        f"📞 <strong>Телефон:</strong> {customer.phone_for_display}\n\n"
        f"🧾 <strong>Товары:</strong>\n{items_block}\n\n"
        f"💰 <strong>Итого:</strong> {cart.total_text}$"
    )


def prepare_summary_payload(
    state_data: Mapping[str, object], customer: CustomerData, cart: CartData
) -> dict[str, object]:
    payload = dict(state_data)
    payload.update(
        {
            "full_name": customer.full_name,
            "postal_code": customer.postal_code,
            "phone": customer.phone_for_display,
            "cart_lines": cart.lines_for_display(),
            "cart_total": cart.total_text,
        }
    )
    return payload


def parse_admin_chat_id(raw_value: str | None) -> int | None:
    if raw_value is None:
        return None
    try:
        return int(raw_value)
    except (TypeError, ValueError):
        return None
