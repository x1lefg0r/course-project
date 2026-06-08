"""
Management-команда для быстрой проверки настройки почты (Mailhog).

Пример:
    python manage.py send_test_email buyer@example.com

Достаточно поднять Mailhog (docker compose up mailhog -d) — письмо появится
в его веб-интерфейсе по адресу http://localhost:8025. Celery/Redis не нужны.
"""
from __future__ import annotations

from django.conf import settings
from django.core.management.base import BaseCommand
from django.core.mail import send_mail


class Command(BaseCommand):
    """Отправляет одно тестовое письмо через настроенный backend."""

    help = "Отправляет тестовое письмо для проверки настройки почты (Mailhog)."

    def add_arguments(self, parser) -> None:
        """Регистрирует необязательный аргумент с адресом получателя."""
        parser.add_argument(
            "recipient",
            nargs="?",
            default="test@example.com",
            help="Email получателя (по умолчанию test@example.com)",
        )

    def handle(self, *args, **options) -> None:
        """Отправляет письмо и сообщает результат в консоль."""
        recipient = options["recipient"]
        sent = send_mail(
            subject="✅ Тестовое письмо TechStore",
            message=(
                "Если вы видите это письмо — отправка почты настроена корректно.\n\n"
                f"Backend: {settings.EMAIL_BACKEND}\n"
                f"SMTP: {settings.EMAIL_HOST}:{settings.EMAIL_PORT}\n\n"
                "Mailhog UI: http://localhost:8025"
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[recipient],
            fail_silently=False,
        )
        if sent:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Письмо отправлено на {recipient}. "
                    "Откройте Mailhog: http://localhost:8025"
                )
            )
        else:
            self.stdout.write(self.style.ERROR("Письмо не отправлено (backend вернул 0)."))
