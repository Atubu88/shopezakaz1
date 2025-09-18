from pathlib import Path
from sqlalchemy.ext.asyncio import AsyncSession
from database.orm_query import (
    orm_add_to_cart,
    orm_delete_from_cart,
    orm_get_banner,
    orm_get_categories,
    orm_get_products,
    orm_get_user_carts,
    orm_reduce_product_in_cart,
)
from kbds.inline import (
    get_products_btns,
    get_user_cart,
    get_user_catalog_btns,
    get_user_main_btns,
)
from utils.paginator import Paginator
from aiogram.types import InputMediaPhoto, FSInputFile


BANNERS_DIR = Path(__file__).resolve().parents[1] / "banners"
DEFAULT_BANNER_FILE = BANNERS_DIR / "default.jpg"
BANNER_FILE_MAP = {
    "main": BANNERS_DIR / "main.jpg",
    "catalog": BANNERS_DIR / "catalog.jpg",
    "cart": BANNERS_DIR / "cart.jpg",
    "about": BANNERS_DIR / "about.jpg",
    "payment": BANNERS_DIR / "payment.jpg",
    "shipping": BANNERS_DIR / "shipping.jpg",
}

IMAGE_NOT_FOUND_TEXT = "Изображение не найдено или путь некорректен"


def resolve_banner_path(name: str) -> Path | None:
    normalized = name.lower()
    candidate = BANNER_FILE_MAP.get(normalized)
    if candidate and candidate.exists():
        return candidate

    dynamic_candidate = BANNERS_DIR / f"{normalized}.jpg"
    if dynamic_candidate.exists():
        return dynamic_candidate

    if DEFAULT_BANNER_FILE.exists():
        return DEFAULT_BANNER_FILE

    return None


def get_banner_media_source(banner, name: str):
    local_path = resolve_banner_path(name)
    if local_path:
        return FSInputFile(str(local_path))

    if banner and getattr(banner, "image", None):
        stored_path = Path(str(banner.image))
        if stored_path.exists():
            return FSInputFile(str(stored_path))
        return banner.image

    raise FileNotFoundError(f"No banner image available for '{name}'.")


async def main_menu(session, level, menu_name):
    banner = await orm_get_banner(session, menu_name)
    caption = banner.description if banner and banner.description else ""

    try:
        media_source = get_banner_media_source(banner, menu_name)
    except FileNotFoundError:
        if not DEFAULT_BANNER_FILE.exists():
            raise
        media_source = FSInputFile(str(DEFAULT_BANNER_FILE))
        if not caption:
            caption = IMAGE_NOT_FOUND_TEXT

    image = InputMediaPhoto(media=media_source, caption=caption)

    kbds = get_user_main_btns(level=level)

    return image, kbds


async def catalog(session, level, menu_name):
    banner = await orm_get_banner(session, menu_name)
    caption = banner.description if banner and banner.description else ""

    try:
        media_source = get_banner_media_source(banner, menu_name)
    except FileNotFoundError:
        if not DEFAULT_BANNER_FILE.exists():
            raise
        media_source = FSInputFile(str(DEFAULT_BANNER_FILE))
        if not caption:
            caption = IMAGE_NOT_FOUND_TEXT

    image = InputMediaPhoto(media=media_source, caption=caption)

    categories = await orm_get_categories(session)
    kbds = get_user_catalog_btns(level=level, categories=categories)

    return image, kbds

def pages(paginator: Paginator):
    btns = dict()
    if paginator.has_previous():
        btns["◀ Пред."] = "previous"

    if paginator.has_next():
        btns["След. ▶"] = "next"

    return btns


async def products(session, level, category, page):
    products = await orm_get_products(session, category_id=category)

    paginator = Paginator(products, page=page)
    product = paginator.get_page()[0]

    image = InputMediaPhoto(
        media=product.image,
        caption=f"<strong>{product.name}\
                </strong>\n{product.description}\nСтоимость: {round(product.price, 2)}\n\
                <strong>Товар {paginator.page} из {paginator.pages}</strong>",
    )

    pagination_btns = pages(paginator)

    kbds = get_products_btns(
        level=level,
        category=category,
        page=page,
        pagination_btns=pagination_btns,
        product_id=product.id,
    )

    return image, kbds


async def carts(session, level, menu_name, page, user_id, product_id):
    if menu_name == "delete":
        await orm_delete_from_cart(session, user_id, product_id)
        if page > 1:
            page -= 1
    elif menu_name == "decrement":
        is_cart = await orm_reduce_product_in_cart(session, user_id, product_id)
        if page > 1 and not is_cart:
            page -= 1
    elif menu_name == "increment":
        await orm_add_to_cart(session, user_id, product_id)

    carts = await orm_get_user_carts(session, user_id)

    if not carts:
        banner = await orm_get_banner(session, "cart")
        description_text = banner.description if banner and banner.description else None
        caption = (
            f"<strong>{description_text}</strong>"
            if description_text
            else f"<strong>{IMAGE_NOT_FOUND_TEXT}</strong>"
        )

        try:
            media_source = get_banner_media_source(banner, "cart")
        except FileNotFoundError:
            if not DEFAULT_BANNER_FILE.exists():
                raise
            media_source = FSInputFile(str(DEFAULT_BANNER_FILE))
            if not description_text:
                caption = f"<strong>{IMAGE_NOT_FOUND_TEXT}</strong>"

        image = InputMediaPhoto(media=media_source, caption=caption)

        kbds = get_user_cart(
            level=level,
            page=None,
            pagination_btns=None,
            product_id=None,
        )

    else:
        paginator = Paginator(carts, page=page)

        cart = paginator.get_page()[0]

        cart_price = round(cart.quantity * cart.product.price, 2)
        total_price = round(
            sum(cart.quantity * cart.product.price for cart in carts), 2
        )
        image = InputMediaPhoto(
            media=cart.product.image,
            caption=f"<strong>{cart.product.name}</strong>\n{cart.product.price}$ x {cart.quantity} = {cart_price}$\
                    \nТовар {paginator.page} из {paginator.pages} в корзине.\nОбщая стоимость товаров в корзине {total_price}",
        )

        pagination_btns = pages(paginator)

        kbds = get_user_cart(
            level=level,
            page=page,
            pagination_btns=pagination_btns,
            product_id=cart.product.id,
        )

    return image, kbds


async def get_menu_content(
    session: AsyncSession,
    level: int,
    menu_name: str,
    category: int | None = None,
    page: int | None = None,
    product_id: int | None = None,
    user_id: int | None = None,
):
    if level == 0:
        return await main_menu(session, level, menu_name)
    elif level == 1:
        return await catalog(session, level, menu_name)
    elif level == 2:
        return await products(session, level, category, page)
    elif level == 3:
        return await carts(session, level, menu_name, page, user_id, product_id)