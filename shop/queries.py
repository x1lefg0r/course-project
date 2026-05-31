from django.db.models import Q, Count, Avg, Sum
from datetime import date
from .models import Category, Product, Order, Supplier, Review


def complex_query_1():
    """
    Запрос 1: новые/восстановленные товары ценой < 50 000 ₽ или со скидкой, не наушники.

    Returns:
        QuerySet[Product]: отфильтрованные товары
    """
    products = Product.objects.filter(
        (Q(condition="new") | Q(condition="refurbished"))
        & (Q(price__lt=50000) | Q(discount_price__isnull=False))
        & ~Q(category__name="Наушники")
        & Q(is_available=True)
    )
    return products


def complex_query_2():
    """
    Запрос 2: крупные заказы техники (отправленные/доставленные, >100 000 ₽ или >2 шт.).

    Returns:
        QuerySet[Order]: отфильтрованные заказы
    """
    orders = Order.objects.filter(
        (Q(status="shipped") | Q(status="delivered"))
        & (Q(total_price__gt=100000) | Q(quantity__gt=2))
        & ~Q(status="cancelled")
        & (
            Q(product__category__name="Смартфоны")
            | Q(product__category__name="Ноутбуки")
        )
    )
    return orders


def complex_query_3():
    """
    Запрос 3: активные премиум-категории (ср. цена > 30 000 ₽) с новыми/акционными товарами.

    Returns:
        QuerySet[Category]: категории с аннотациями avg_price и product_count
    """
    categories = (
        Category.objects.annotate(
            avg_price=Avg("products__price"), product_count=Count("products")
        )
        .filter(
            Q(is_active=True)
            & (Q(products__discount_price__isnull=False) | Q(products__condition="new"))
            & ~Q(product_count=0)
            & Q(avg_price__gt=30000)
        )
        .distinct()
    )
    return categories


def complex_query_4():
    """
    Запрос 4: топ-бренды Apple/Samsung/Xiaomi после 2020 г. с малым остатком (<10 шт.).

    Returns:
        QuerySet[Product]: товары с низким остатком от ведущих брендов
    """
    products = Product.objects.filter(
        (Q(release_year__gt=2020) | Q(warranty_months__gt=12))
        & (Q(brand="Apple") | Q(brand="Samsung") | Q(brand="Xiaomi"))
        & ~Q(condition="used")
        & Q(stock_quantity__lt=10)
        & Q(stock_quantity__gt=0)
    )
    return products


def complex_query_5():
    """
    Запрос 5: активные поставщики Apple/Samsung с рейтингом >4.0 или из России, >3 товаров.

    Returns:
        QuerySet[Supplier]: поставщики с аннотацией product_count
    """
    from django.db.models import Count

    suppliers = (
        Supplier.objects.annotate(product_count=Count("products"))
        .filter(
            (Q(rating__gt=4.0) | Q(country="Россия"))
            & (Q(products__brand="Apple") | Q(products__brand="Samsung"))
            & ~Q(is_active=False)
            & Q(product_count__gt=3)
        )
        .distinct()
    )
    return suppliers


def complex_query_6():
    """
    Запрос 6: качественные одобренные отзывы на технику за последние 30 дней.

    Returns:
        QuerySet[Review]: отзывы с оценкой 5★ или подтверждённой покупкой
    """
    from datetime import timedelta

    thirty_days_ago = date.today() - timedelta(days=30)

    reviews = Review.objects.filter(
        (Q(rating=5) | Q(is_verified_purchase=True))
        & (
            Q(product__category__name="Смартфоны")
            | Q(product__category__name="Ноутбуки")
        )
        & ~Q(is_approved=False)
        & Q(created_at__gte=thirty_days_ago)
    )
    return reviews
