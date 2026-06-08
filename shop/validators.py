"""
Переиспользуемые валидаторы бизнес-логики для оформления заказа.

Используются в сериализаторах ([[serializers.py]]) и при оформлении заказа
из корзины (CartViewSet.checkout, web-вьюха cart_checkout).
"""
from __future__ import annotations

import re
from decimal import Decimal

from rest_framework import serializers

# Минимальная и максимальная допустимая сумма заказа (БЛ из варианта).
MIN_ORDER_AMOUNT = Decimal("500")
MAX_ORDER_AMOUNT = Decimal("100000")

# Российский почтовый индекс — ровно 6 цифр.
_POSTAL_CODE_RE = re.compile(r"\b\d{6}\b")


def validate_delivery_address(value: str) -> str:
    """
    Валидация формата адреса доставки.

    Args:
        value: Строка адреса доставки

    Адрес должен содержать минимум три компонента через запятую
    (город, улица, дом) и почтовый индекс из 6 цифр.

    Returns:
        Исходную строку адреса, если она прошла проверку

    Raises:
        serializers.ValidationError: если формат адреса некорректен
    """
    parts = [p.strip() for p in value.split(",") if p.strip()]
    if len(parts) < 3:
        raise serializers.ValidationError(
            "Адрес должен содержать город, улицу и номер дома через запятую. "
            "Пример: «г. Москва, ул. Тверская, д. 10, 125009»"
        )
    if not _POSTAL_CODE_RE.search(value):
        raise serializers.ValidationError(
            "Адрес должен содержать почтовый индекс из 6 цифр"
        )
    return value


def validate_order_amount(total) -> None:
    """
    Валидация суммы заказа по установленным ограничениям.

    Args:
        total: Итоговая сумма заказа

    Raises:
        serializers.ValidationError: если сумма вне диапазона
            [MIN_ORDER_AMOUNT; MAX_ORDER_AMOUNT]
    """
    total = Decimal(str(total))
    if total < MIN_ORDER_AMOUNT:
        raise serializers.ValidationError(
            f"Минимальная сумма заказа — {MIN_ORDER_AMOUNT:.0f} ₽ (сейчас {total:.2f} ₽)"
        )
    if total > MAX_ORDER_AMOUNT:
        raise serializers.ValidationError(
            f"Максимальная сумма заказа — {MAX_ORDER_AMOUNT:.0f} ₽ (сейчас {total:.2f} ₽)"
        )
