"""
Синхронная отправка писем (без Celery) — для наглядной проверки через Mailhog.

В отличие от [[tasks.py]] (асинхронные Celery-задачи), эти письма уходят
прямо в обработчике запроса: достаточно поднять только Mailhog
(docker compose up mailhog -d) и runserver — Redis и воркер не нужны.
"""
from __future__ import annotations

from django.conf import settings
from django.core.mail import send_mail


def send_order_confirmation(customer_name: str, customer_email: str, orders, total) -> None:
    """
    Отправляет покупателю письмо-подтверждение оформленного заказа.

    Args:
        customer_name: Имя получателя
        customer_email: Email получателя
        orders: Список созданных заказов (Order)
        total: Итоговая сумма заказа

    Отправка best-effort (fail_silently=True): недоступность почты
    не должна срывать уже созданный заказ.
    """
    if not customer_email:
        return

    lines = "\n".join(
        f"  • {o.product.name} × {o.quantity} шт. = {o.total_price} ₽" for o in orders
    )
    order_nums = ", ".join(f"#{o.id}" for o in orders)

    send_mail(
        subject=f"TechStore: заказ оформлен ({order_nums})",
        message=(
            f"Здравствуйте, {customer_name}!\n\n"
            f"Ваш заказ принят в обработку. Состав заказа:\n\n"
            f"{lines}\n\n"
            f"Итого к оплате: {total} ₽\n\n"
            f"Спасибо за покупку в TechStore!"
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[customer_email],
        fail_silently=True,
    )
