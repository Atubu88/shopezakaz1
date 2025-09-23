import math
from decimal import Decimal

from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from database.models import Banner, Cart, Category, Order, OrderItem, Product, User

# Простой пагинатор
class Paginator:
    def __init__(self, array: list | tuple, page: int=1, per_page: int=1):
        self.array = array
        self.per_page = per_page
        self.page = page
        self.len = len(self.array)
        # math.ceil - округление в большую сторону до целого числа
        self.pages = math.ceil(self.len / self.per_page)

    def __get_slice(self):
        start = (self.page - 1) * self.per_page
        stop = start + self.per_page
        return self.array[start:stop]

    def get_page(self):
        page_items = self.__get_slice()
        return page_items

    def has_next(self):
        if self.page < self.pages:
            return self.page + 1
        return False

    def has_previous(self):
        if self.page > 1:
            return self.page - 1
        return False

    def get_next(self):
        if self.page < self.pages:
            self.page += 1
            return self.get_page()
        raise IndexError(f'Next page does not exist. Use has_next() to check before.')

    def get_previous(self):
        if self.page > 1:
            self.page -= 1
            return self.__get_slice()
        raise IndexError(f'Previous page does not exist. Use has_previous() to check before.')


############### Работа с баннерами (информационными страницами) ###############

async def orm_add_banner_description(session: AsyncSession, data: dict):
    # Проходим по каждому элементу данных
    for name, description in data.items():
        # Проверяем, существует ли баннер с данным именем
        query = select(Banner).where(Banner.name == name)
        result = await session.execute(query)
        banner = result.scalar()

        if banner:
            # Обновляем существующий баннер
            await session.execute(
                update(Banner).where(Banner.name == name).values(description=description)
            )
        else:
            # Добавляем новый баннер, если его нет
            session.add(Banner(name=name, description=description))

    await session.commit()


async def orm_change_banner_image(session: AsyncSession, name: str, image: str):
    query = update(Banner).where(Banner.name == name).values(image=image)
    await session.execute(query)
    await session.commit()


async def orm_get_banner(session: AsyncSession, page: str):
    query = select(Banner).where(Banner.name == page)
    result = await session.execute(query)
    return result.scalar()


async def orm_get_info_pages(session: AsyncSession):
    query = select(Banner)
    result = await session.execute(query)
    return result.scalars().all()


############################ Категории ######################################

async def orm_get_categories(session: AsyncSession):
    query = select(Category)
    result = await session.execute(query)
    return result.scalars().all()

async def orm_create_categories(session: AsyncSession, categories: list):
    query = select(Category)
    result = await session.execute(query)
    if result.first():
        return
    session.add_all([Category(name=name) for name in categories])
    await session.commit()


async def orm_add_category(session: AsyncSession, name: str) -> Category:
    category = Category(name=name)
    session.add(category)
    await session.commit()
    await session.refresh(category)
    return category


async def orm_update_category(session: AsyncSession, category_id: int, name: str) -> bool:
    query = (
        update(Category)
        .where(Category.id == category_id)
        .values(name=name)
    )
    result = await session.execute(query)
    await session.commit()
    return result.rowcount > 0


async def orm_delete_category(session: AsyncSession, category_id: int) -> bool:
    result = await session.execute(delete(Category).where(Category.id == category_id))
    await session.commit()
    return result.rowcount > 0

############ Админка: добавить/изменить/удалить товар ########################

async def orm_add_product(session: AsyncSession, data: dict):
    obj = Product(
        name=data["name"],
        description=data["description"],
        details_url=data.get("details_url"),
        price=float(data["price"]),
        image=data["image"],
        category_id=int(data["category"]),
    )
    session.add(obj)
    await session.commit()


async def orm_get_products(session: AsyncSession, category_id):
    query = select(Product).where(Product.category_id == int(category_id))
    result = await session.execute(query)
    return result.scalars().all()


async def orm_get_product(session: AsyncSession, product_id: int):
    query = select(Product).where(Product.id == product_id)
    result = await session.execute(query)
    return result.scalar()


async def orm_update_product(session: AsyncSession, product_id: int, data):
    query = (
        update(Product)
        .where(Product.id == product_id)
        .values(
            name=data["name"],
            description=data["description"],
            details_url=data.get("details_url"),
            price=float(data["price"]),
            image=data["image"],
            category_id=int(data["category"]),
        )
    )
    await session.execute(query)
    await session.commit()


async def orm_delete_product(session: AsyncSession, product_id: int):
    query = delete(Product).where(Product.id == product_id)
    await session.execute(query)
    await session.commit()

##################### Добавляем юзера в БД #####################################

async def orm_get_user(session: AsyncSession, user_id: int) -> User | None:
    query = select(User).where(User.user_id == user_id)
    result = await session.execute(query)
    return result.scalar_one_or_none()


async def orm_add_user(
    session: AsyncSession,
    user_id: int,
    first_name: str | None = None,
    last_name: str | None = None,
    phone: str | None = None,
    is_admin: bool = False,
):
    user = await orm_get_user(session, user_id)
    if user is None:
        session.add(
            User(
                user_id=user_id,
                first_name=first_name,
                last_name=last_name,
                phone=phone,
                is_admin=is_admin,
            )
        )
        await session.commit()


async def orm_update_user_admin_status(
    session: AsyncSession,
    user_id: int,
    is_admin: bool,
    *,
    first_name: str | None = None,
    last_name: str | None = None,
) -> bool:
    values: dict[str, object] = {"is_admin": is_admin}
    if first_name is not None:
        values["first_name"] = first_name
    if last_name is not None:
        values["last_name"] = last_name

    result = await session.execute(
        update(User).where(User.user_id == user_id).values(**values)
    )
    await session.commit()
    return result.rowcount > 0


######################## Работа с корзинами #######################################

async def orm_add_to_cart(session: AsyncSession, user_id: int, product_id: int):
    query = select(Cart).where(Cart.user_id == user_id, Cart.product_id == product_id).options(joinedload(Cart.product))
    cart = await session.execute(query)
    cart = cart.scalar()
    if cart:
        cart.quantity += 1
        await session.commit()
        return cart
    else:
        session.add(Cart(user_id=user_id, product_id=product_id, quantity=1))
        await session.commit()



async def orm_get_user_carts(session: AsyncSession, user_id):
    query = select(Cart).filter(Cart.user_id == user_id).options(joinedload(Cart.product))
    result = await session.execute(query)
    return result.scalars().all()


async def orm_delete_from_cart(session: AsyncSession, user_id: int, product_id: int):
    query = delete(Cart).where(Cart.user_id == user_id, Cart.product_id == product_id)
    await session.execute(query)
    await session.commit()


async def orm_reduce_product_in_cart(session: AsyncSession, user_id: int, product_id: int):
    query = select(Cart).where(Cart.user_id == user_id, Cart.product_id == product_id).options(joinedload(Cart.product))
    cart = await session.execute(query)
    cart = cart.scalar()

    if not cart:
        return
    if cart.quantity > 1:
        cart.quantity -= 1
        await session.commit()
        return True
    else:
        await orm_delete_from_cart(session, user_id, product_id)
        await session.commit()
        return False


async def create_order_with_items(
    session: AsyncSession,
    user_id: int,
    full_name: str,
    postal_code: str,
    phone: str,
    cart_lines: list[dict],
    total_amount: Decimal | float | str,
) -> Order:
    if not cart_lines:
        raise ValueError("Cart is empty, cannot create order.")

    total = Decimal(str(total_amount))

    async with session.begin():
        order = Order(
            user_id=user_id,
            full_name=full_name,
            postal_code=postal_code,
            phone=phone,
            total_amount=total,
        )
        session.add(order)
        await session.flush()

        order_items: list[OrderItem] = []
        for line in cart_lines:
            product_id = int(line["product_id"])
            quantity = int(line["quantity"])
            price = Decimal(str(line["price"]))
            order_items.append(
                OrderItem(
                    order=order,
                    product_id=product_id,
                    price=price,
                    quantity=quantity,
                )
            )

        if order_items:
            session.add_all(order_items)

        await session.execute(delete(Cart).where(Cart.user_id == user_id))

    await session.refresh(order)
    return order

