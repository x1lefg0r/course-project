"""
Кастомные шаги pipeline для social-auth-app-django.

Выполняются после успешной OAuth2-аутентификации через Google.
"""
from __future__ import annotations


def create_user_profile(backend, user, response, *args, **kwargs) -> None:
    """
    Создаёт UserProfile с ролью 'покупатель' для новых OAuth2-пользователей.

    Args:
        backend: Бэкенд аутентификации (Google)
        user: Объект пользователя Django
        response: Ответ от провайдера OAuth2
    """
    from .models import UserProfile

    UserProfile.objects.get_or_create(user=user, defaults={"role": UserProfile.BUYER})


def get_or_create_token(backend, user, response, *args, **kwargs) -> dict:
    """
    Создаёт или возвращает DRF-токен для OAuth2-пользователя.

    Args:
        backend: Бэкенд аутентификации
        user: Объект пользователя Django
        response: Ответ от провайдера OAuth2

    Returns:
        Словарь с ключом token — значение DRF-токена
    """
    from rest_framework.authtoken.models import Token

    token, _ = Token.objects.get_or_create(user=user)
    return {"token": token.key}
