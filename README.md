# TechStore — интернет-магазин компьютерной периферии

Курсовой проект на **Django REST Framework**: бэкенд интернет-магазина с REST API,
веб-витриной, ролевой моделью доступа, корзиной, избранным, системой отзывов,
фоновыми задачами (Celery) и аутентификацией через Google OAuth2.

> Вариант: «Интернет-магазин компьютерной периферии». Реализованы каталог,
> корзина, оформление заказа, управление пользователями, система отзывов и рейтингов.

---

## 🧰 Стек

| Категория | Технологии |
|-----------|-----------|
| Backend | Python 3.13, Django 6.0, Django REST Framework 3.16 |
| БД | SQLite (dev) / PostgreSQL (prod, через `DATABASE_URL`) |
| Фильтрация | django-filter |
| Фон. задачи | Celery + Redis |
| Почта | SMTP / Mailhog (dev) |
| Аутентификация | Token Auth, Session Auth, Google OAuth2 (social-auth) |
| Профилирование | django-silk |
| Мониторинг | Sentry |
| История изменений | django-simple-history |
| Импорт/экспорт | django-import-export |
| Прод | Gunicorn, WhiteNoise, Nginx, Docker |

---

## 🚀 Быстрый старт

### 1. Виртуальное окружение и зависимости

```bash
# macOS / Linux
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

```powershell
# Windows (PowerShell)
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 2. Файл `.env` (в корне проекта)

```env
DEBUG=1
ALLOWED_HOSTS=localhost 127.0.0.1
# DATABASE_URL должен быть закомментирован — иначе проект ждёт PostgreSQL
```

> ⚠️ Без `DEBUG=1` не раздаётся статика и админка отображается без CSS.
> Полный список переменных — в [.env.example](.env.example).

### 3. Миграции и запуск

```bash
python manage.py migrate
python manage.py createsuperuser   # для доступа в админку
python manage.py runserver
```

Открыть: <http://127.0.0.1:8000/> — витрина, <http://127.0.0.1:8000/api/> — API,
<http://127.0.0.1:8000/admin/> — админка.

---

## 👥 Роли и права

Профиль с ролью создаётся автоматически при регистрации (сигнал `post_save`).
Роль по умолчанию — **покупатель**.

| Роль | Возможности |
|------|-------------|
| **admin** | Полный доступ. Управление товарами, заказами, поставщиками, пользователями (через админку), модерация отзывов, рейтинги поставщиков, скидки без ограничений. |
| **manager** | CRUD товаров и категорий, все заказы и смена статусов, модерация отзывов, скидки **≤ 50 %**. |
| **buyer** | Просмотр каталога, корзина, оформление заказа (≤ 10 ед. за раз), личный кабинет, избранное, отзывы. Отмена только своих заказов в статусе `pending`. |

---

## ✨ Возможности

- **Каталог** — фильтрация (цена, категория, бренд, состояние, год, скидка), поиск, сортировка.
- **Корзина** — добавление/изменение количества/удаление, контроль остатка на складе.
- **Оформление заказа** из корзины — создаёт заказы, списывает склад, шлёт письмо-подтверждение.
- **Избранное** — добавление/удаление, флаг `is_favorite` и счётчик `favorites_count`.
- **Отзывы и рейтинги** — с модерацией (одобрение менеджером/админом).
- **Поставщики** — управление, рейтинги (только admin).
- **Аналитика** — еженедельный отчёт о продажах (Celery), «сложные» аналитические запросы.

---

## 🔌 API

Базовый префикс — `/api/`. Аутентификация: заголовок `Authorization: Token <key>`.

### Аутентификация

| Метод | Endpoint | Описание |
|-------|----------|----------|
| POST | `/api/auth/register/` | Регистрация → возвращает token |
| POST | `/api/auth/token/` | Логин по логину/паролю → token |
| GET/PATCH | `/api/auth/profile/` | Профиль текущего пользователя |
| GET | `/auth/login/google-oauth2/` | Вход через Google OAuth2 |

### Ресурсы (ViewSet'ы)

| Endpoint | Доступ | Примечания |
|----------|--------|-----------|
| `/api/categories/` | чтение — все, запись — manager/admin | actions: `popular`, `toggle_active` |
| `/api/products/` | чтение — все, запись — manager/admin | фильтры: `min_price`, `max_price`, `brand`, `category`, `condition`, `on_sale`, `year_from`, `year_to`, `min_warranty`; actions: `on_sale`, `low_stock`, `apply_discount`, `restock` |
| `/api/orders/` | buyer — только свои | actions: `my_orders`, `recent`, `pending`, `change_status`, `cancel` |
| `/api/suppliers/` | manager/admin | actions: `top_rated`, `add_products`, `update_rating` (admin) |
| `/api/reviews/` | чтение одобренных — все | actions: `high_rated`, `pending_approval`, `approve`, `verify_purchase` |
| `/api/cart/` | свой, авторизованные | actions: `add_item`, `update_item`, `remove_item`, `clear`, **`checkout`** |
| `/api/favorites/` | свои, авторизованные | action: **`toggle`** |

### Примеры

```bash
# Регистрация
curl -X POST http://127.0.0.1:8000/api/auth/register/ \
  -H "Content-Type: application/json" \
  -d '{"username":"buyer1","email":"b@x.ru","password":"secret123","role":"buyer"}'

# Добавить товар в корзину
curl -X POST http://127.0.0.1:8000/api/cart/add_item/ \
  -H "Authorization: Token <KEY>" -H "Content-Type: application/json" \
  -d '{"product": 1, "quantity": 2}'

# Оформить заказ из корзины
curl -X POST http://127.0.0.1:8000/api/cart/checkout/ \
  -H "Authorization: Token <KEY>" -H "Content-Type: application/json" \
  -d '{"customer_name":"Иван","customer_email":"i@x.ru","customer_phone":"+79001234567","delivery_address":"г. Москва, ул. Тверская, д. 10, 125009"}'

# Переключить избранное
curl -X POST http://127.0.0.1:8000/api/favorites/toggle/ \
  -H "Authorization: Token <KEY>" -H "Content-Type: application/json" \
  -d '{"product": 1}'
```

Готовая коллекция запросов — [postman_collection.json](postman_collection.json).

---

## ✅ Валидация бизнес-логики

| Правило | Где |
|---------|-----|
| Наличие товара на складе при добавлении в корзину / заказе | `CartItem.clean`, `OrderSerializer`, `CartViewSet.checkout` |
| Формат адреса доставки (город, улица, дом + индекс из 6 цифр) | `validators.validate_delivery_address` |
| Сумма заказа в пределах **500 – 100 000 ₽** | `validators.validate_order_amount` |
| Права доступа к заказу (свой / manager / admin) | `OrderViewSet.get_queryset` |
| Скидка ≤ 50 % для менеджера | `ProductSerializer.validate`, `apply_discount` |
| Один отзыв на товар от одного email | `ReviewSerializer.validate` |
| Лимит покупателя — 10 ед. за заказ | `OrderSerializer.validate_quantity` |

---

## 🧱 Архитектурные приёмы (для защиты)

- **`select_related` / `prefetch_related`** — оптимизация запросов для товаров+категорий,
  заказов+покупателей, отзывов+товаров, корзины+товаров.
- **Аннотации** — `avg_rating`, `reviews_count`, `total_ordered`, **`favorites_count`**
  (количество добавлений в избранное), `products_count`, `avg_price`.
- **Сериализаторы**:
  - `SerializerMethodField` — `discount_percentage`, `final_price`, `stock_alert`,
    `is_favorite`, `moderation_info`, `is_owner`.
  - **Передача данных через контекст** — список избранного (`favorites_products`)
    прокидывается во `view` одним запросом и используется в `get_is_favorite` (без N+1);
    роль пользователя из `request` управляет видимостью полей.

---

## 🧪 Тесты

```bash
python manage.py test shop.tests
# 44 теста, все проходят
```

Покрыто: автосоздание профиля, валидация моделей и заказов, ролевые права,
видимость заказов/полей, лимит скидки, дубликаты отзывов, фильтрация, аутентификация,
**корзина, оформление заказа (+письмо), избранное, валидация адреса и суммы**.

---

## ⚙️ Celery + Mailhog

### Фоновые задачи (Celery)

```bash
docker compose up redis mailhog -d
celery -A electronics_store worker --loglevel=info
celery -A electronics_store beat --loglevel=info   # периодические задачи
```

| Задача | Расписание |
|--------|-----------|
| Уведомление о низком остатке | ежедневно 09:00 |
| Отмена просроченных заказов (>7 дней) | ежедневно 01:00 |
| Еженедельный отчёт о продажах | пн 08:00 |
| Письмо о смене статуса заказа | по событию |

### Проверка отправки писем (без Celery)

**Через Mailhog** (нужен один контейнер):

```bash
docker compose up mailhog -d
python manage.py send_test_email buyer@example.com
# письмо появится в http://localhost:8025
```

**Вообще без Docker** (письмо печатается в терминал):

```bash
EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend \
  python manage.py send_test_email buyer@example.com
```

Кроме того, при оформлении заказа из корзины покупателю синхронно уходит
**письмо-подтверждение** (видно в Mailhog/консоли).

---

## 🔐 Google OAuth2

Ключи в `.env`: `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`.
Redirect URI в Google Console: `http://127.0.0.1:8000/auth/complete/google-oauth2/`.
После входа создаётся `UserProfile` (роль buyer) и DRF-токен (pipeline в [shop/pipeline.py](shop/pipeline.py)).

---

## 📊 Профилирование и мониторинг

- **Django Silk** — `/silk/` (профилирование SQL-запросов и времени ответа).
- **Sentry** — включается заданием `SENTRY_DSN` в `.env`.

---

## 🚢 Деплой

```bash
docker compose -f docker-compose.prod.yml up -d
```

Требуется VPS и заполненный `.env` (шаблон — [.env.example](.env.example)).
Прод-стек: Gunicorn + WhiteNoise (статика) + Nginx (reverse proxy) + PostgreSQL + Redis.

---

## 📁 Структура

```
electronics_store/      конфиг Django (settings, urls, celery, wsgi/asgi)
shop/
  models.py             Category, Product, Order, Supplier, Review, UserProfile, Cart, CartItem, Favorite
  views.py              ViewSet'ы (API) + веб-вьюхи (витрина, корзина, избранное, auth)
  serializers.py        сериализаторы с контекстом и аннотациями
  permissions.py        IsAdminRole, IsManagerOrAdmin, IsOwnerOrManagerAdmin
  filters.py            ProductFilter, OrderFilter, ReviewFilter, SupplierFilter
  validators.py         валидация адреса доставки и суммы заказа
  emails.py             синхронная отправка писем (подтверждение заказа)
  tasks.py              Celery-задачи
  pipeline.py           OAuth2 pipeline
  queries.py            «сложные» аналитические запросы
  admin.py              кастомизация админки + import/export
  tests.py              44 теста
  management/commands/  send_test_email
  templates/shop/       base, product_list, product_detail, cart, checkout, favorites, login, register
```

---

## 📋 Соответствие заданию

| Требование | Статус |
|-----------|--------|
| Роли + ≥3 функции на роль | ✅ |
| Валидация бизнес-логики (≥3) | ✅ (наличие, адрес, сумма, доступ, скидка, отзывы) |
| `select_related` (4 сценария) | ✅ |
| Сериализаторы: `SerializerMethodField` + контекст | ✅ |
| Аннотации (ср. рейтинг, продажи, избранное) | ✅ |
| FilterSet (цена, категория, производитель) | ✅ |
| Postman-коллекция | ✅ |
| Sentry | ✅ |
| Тесты (≥10) | ✅ 44 |
| Докстринги + типизация | ✅ |
| Django Silk | ✅ |
| Celery (периодические задачи) | ✅ |
| Mailhog + проверка почты | ✅ |
| Деплой | ✅ |
| OAuth2 | ✅ |
| Корзина + избранное | ✅ |
