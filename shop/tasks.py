from __future__ import annotations

from celery import shared_task
from django.core.mail import send_mail
from django.utils import timezone
from datetime import timedelta


@shared_task
def send_low_stock_alert() -> str:
    """
    Ежедневная задача: уведомить менеджеров о товарах с низким остатком (<5 шт.).

    Returns:
        Строка с результатом выполнения задачи
    """
    from .models import Product
    from django.contrib.auth.models import User

    low_stock = Product.objects.filter(
        stock_quantity__lt=5,
        stock_quantity__gt=0,
        is_available=True,
    ).select_related("category")

    if not low_stock.exists():
        return "Нет товаров с низким остатком"

    recipients = list(
        User.objects.filter(profile__role__in=["admin", "manager"])
        .exclude(email="")
        .values_list("email", flat=True)
    )
    if not recipients:
        return "Нет получателей для уведомления"

    product_lines = "\n".join(
        f"  • {p.name} ({p.brand} {p.model}): {p.stock_quantity} шт."
        for p in low_stock
    )

    send_mail(
        subject="⚠ Низкий остаток товаров на складе",
        message=(
            f"Требует внимания: товары с остатком менее 5 штук.\n\n"
            f"{product_lines}\n\n"
            f"Пожалуйста, пополните склад."
        ),
        from_email="noreply@electronics-store.ru",
        recipient_list=recipients,
        fail_silently=True,
    )
    return f"Уведомление отправлено: {low_stock.count()} товаров, {len(recipients)} получателей"


@shared_task
def cancel_stale_orders() -> str:
    """
    Ежедневная задача: автоматически отменить заказы в статусе 'pending' старше 7 дней.

    Возвращает товары на склад и отправляет email покупателям.

    Returns:
        Строка с количеством отменённых заказов
    """
    from .models import Order

    cutoff = timezone.now() - timedelta(days=7)
    stale = Order.objects.filter(
        status="pending",
        order_date__lt=cutoff,
    ).select_related("product")

    cancelled = 0
    for order in stale:
        order.status = "cancelled"
        order.save()

        product = order.product
        product.stock_quantity += order.quantity
        if product.stock_quantity > 0:
            product.is_available = True
        product.save()

        if order.customer_email:
            send_mail(
                subject=f"Заказ #{order.id} автоматически отменён",
                message=(
                    f"Здравствуйте, {order.customer_name}!\n\n"
                    f"Ваш заказ #{order.id} ({order.product.name} × {order.quantity} шт.) "
                    f"был автоматически отменён, так как не обработан в течение 7 дней.\n\n"
                    f"Если вас это не устраивает, оформите новый заказ на сайте."
                ),
                from_email="noreply@electronics-store.ru",
                recipient_list=[order.customer_email],
                fail_silently=True,
            )
        cancelled += 1

    return f"Отменено {cancelled} просроченных заказов"


@shared_task
def send_weekly_sales_report() -> str:
    """
    Еженедельная задача: отправить отчёт о продажах администраторам.

    Returns:
        Строка с итогами отчёта
    """
    from .models import Order
    from django.db.models import Sum, Count
    from django.contrib.auth.models import User

    week_ago = timezone.now() - timedelta(days=7)
    orders = Order.objects.filter(
        order_date__gte=week_ago,
        status__in=["processing", "shipped", "delivered"],
    )
    stats = orders.aggregate(total_orders=Count("id"), total_revenue=Sum("total_price"))

    top_products = (
        Order.objects.filter(order_date__gte=week_ago)
        .exclude(status="cancelled")
        .values("product__name")
        .annotate(qty=Sum("quantity"))
        .order_by("-qty")[:5]
    )
    top_lines = "\n".join(f"  {i+1}. {p['product__name']}: {p['qty']} шт." for i, p in enumerate(top_products))

    admins = list(
        User.objects.filter(profile__role="admin")
        .exclude(email="")
        .values_list("email", flat=True)
    )
    if not admins:
        return "Нет администраторов для отправки отчёта"

    send_mail(
        subject=f"Еженедельный отчёт о продажах ({week_ago.strftime('%d.%m')}–{timezone.now().strftime('%d.%m.%Y')})",
        message=(
            f"Еженедельный отчёт о продажах\n"
            f"{'='*40}\n\n"
            f"Период: {week_ago.strftime('%d.%m.%Y')} — {timezone.now().strftime('%d.%m.%Y')}\n\n"
            f"Количество заказов: {stats['total_orders'] or 0}\n"
            f"Общая выручка:      {stats['total_revenue'] or 0} ₽\n\n"
            f"Топ-5 товаров по количеству:\n{top_lines or '  Нет данных'}\n"
        ),
        from_email="noreply@electronics-store.ru",
        recipient_list=admins,
        fail_silently=True,
    )
    return f"Отчёт отправлен. Заказов: {stats['total_orders']}, Выручка: {stats['total_revenue']} ₽"


@shared_task
def send_order_status_email(order_id: int, new_status: str) -> str:
    """
    Задача: уведомить покупателя об изменении статуса заказа.

    Args:
        order_id: ID заказа
        new_status: Новый статус заказа

    Returns:
        Строка с результатом отправки
    """
    from .models import Order

    try:
        order = Order.objects.select_related("product").get(id=order_id)
    except Order.DoesNotExist:
        return f"Заказ #{order_id} не найден"

    status_text = {
        "processing": "принят в обработку",
        "shipped": "отправлен",
        "delivered": "доставлен",
        "cancelled": "отменён",
    }.get(new_status, new_status)

    send_mail(
        subject=f"Заказ #{order.id}: статус обновлён",
        message=(
            f"Здравствуйте, {order.customer_name}!\n\n"
            f"Ваш заказ #{order.id} {status_text}.\n\n"
            f"Товар: {order.product.name} × {order.quantity} шт.\n"
            f"Сумма: {order.total_price} ₽\n"
        ),
        from_email="noreply@electronics-store.ru",
        recipient_list=[order.customer_email],
        fail_silently=True,
    )
    return f"Email отправлен: заказ #{order_id}, статус '{new_status}'"
