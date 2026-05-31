# CLAUDE.md — контекст проекта

Курсовая по Django REST Framework. Интернет-магазин электроники. Все три части задания выполнены.

## Запуск

```powershell
.\venv\Scripts\python.exe manage.py runserver
```

**Обязательно в `.env`:**
```env
DEBUG=1
ALLOWED_HOSTS=localhost 127.0.0.1
# DATABASE_URL должен быть закомментирован — иначе падает с ошибкой postgres
```

Без `DEBUG=1` статика не раздаётся и admin выглядит без CSS.

## Тесты

```powershell
.\venv\Scripts\python.exe manage.py test shop.tests
# 31 тест, все проходят
```

## Структура

```
electronics_store/   — конфиг Django (settings, urls, celery)
shop/
  models.py          — Category, Product, Order, Supplier, Review, UserProfile
  views.py           — ViewSets + веб-вьюхи (login/register/logout/oauth)
  serializers.py     — сериализаторы с контекстом и аннотациями
  permissions.py     — IsAdminRole, IsManagerOrAdmin, IsOwnerOrManagerAdmin
  filters.py         — ProductFilter, OrderFilter, ReviewFilter, SupplierFilter
  tasks.py           — 4 Celery-задачи
  pipeline.py        — OAuth2 pipeline (UserProfile + DRF token)
  tests.py           — 31 тест
  templates/shop/    — base, product_list, product_detail, login, register
```

## Роли

| Роль | Права |
|------|-------|
| admin | Всё |
| manager | CRUD товаров, все заказы, модерация отзывов, скидки ≤50% |
| buyer | Просмотр, свои заказы (≤10 шт.), отмена только pending |

Профиль создаётся автоматически через сигнал `post_save`.

## API

- `POST /api/auth/register/` — регистрация → token
- `POST /api/auth/token/` — логин → token
- `GET /auth/login/google-oauth2/` — вход через Google
- `/api/products/` — фильтры: min_price, max_price, brand, on_sale, category
- `/api/orders/` — buyer видит только свои
- `/api/suppliers/` — только manager/admin
- `/silk/` — профилирование запросов

Postman коллекция: `postman_collection.json`

## Celery + Mailhog (нужен Docker)

```powershell
docker compose up redis mailhog -d
.\venv\Scripts\celery.exe -A electronics_store worker --loglevel=info
# Mailhog UI: http://localhost:8025
```

Задачи: низкий остаток (09:00), отмена старых заказов (01:00), отчёт (пн 08:00), смена статуса заказа (по событию).

## Деплой

Файлы готовы, команда:
```bash
docker compose -f docker-compose.prod.yml up -d
```
Нужен VPS + заполненный `.env` (шаблон в `.env.example`).

## Google OAuth2

Ключи в `.env`: `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`.
Redirect URI в Google Console: `http://127.0.0.1:8000/auth/complete/google-oauth2/`
