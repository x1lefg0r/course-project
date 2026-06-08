from django.test import TestCase
from django.contrib.auth.models import User
from django.core import mail
from django.core.exceptions import ValidationError
from rest_framework.test import APITestCase
from rest_framework.authtoken.models import Token
from rest_framework import status

from .models import (
    Category, Product, Order, Review, Supplier, UserProfile, CartItem, Favorite,
)

VALID_ADDRESS = "г. Москва, ул. Тверская, д. 10, 125009"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_user(username: str, role: str = UserProfile.BUYER, password: str = "testpass123") -> User:
    """
    Создаёт пользователя и устанавливает ему роль.

    Args:
        username: Имя пользователя
        role: Роль (buyer / manager / admin)
        password: Пароль
    """
    user = User.objects.create_user(username=username, password=password, email=f"{username}@test.com")
    UserProfile.objects.filter(user=user).update(role=role)
    return user


def auth_client(client, user: User) -> None:
    """
    Аутентифицирует клиент через Token.

    Args:
        client: DRF APIClient
        user: Объект пользователя
    """
    token, _ = Token.objects.get_or_create(user=user)
    client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")


def make_product(category: Category, name: str = "Товар", price: int = 1000, stock: int = 50) -> Product:
    """
    Создаёт товар с заданными параметрами.

    Args:
        category: Категория товара
        name: Название товара
        price: Цена
        stock: Остаток на складе
    """
    return Product.objects.create(
        name=name, category=category, brand="TestBrand", model="T1",
        price=price, condition="new", stock_quantity=stock,
        warranty_months=12, release_year=2023, is_available=True,
    )


def make_order(product: Product, user: User, quantity: int = 1, order_status: str = "pending") -> Order:
    """
    Создаёт заказ для пользователя.

    Args:
        product: Товар
        user: Пользователь-покупатель
        quantity: Количество
        order_status: Статус заказа
    """
    return Order.objects.create(
        product=product, user=user,
        customer_name="Тест Тестов", customer_email="test@test.com",
        customer_phone="+79001234567", quantity=quantity,
        total_price=product.price * quantity,
        delivery_address="Москва, ул. Тестовая, д. 1",
        status=order_status,
    )


# ---------------------------------------------------------------------------
# 1. UserProfile — сигнал автосоздания профиля
# ---------------------------------------------------------------------------

class TestUserProfileAutoCreation(TestCase):
    """Проверяет, что профиль создаётся автоматически при регистрации."""

    def test_profile_created_on_user_creation(self) -> None:
        """Профиль должен существовать сразу после создания пользователя."""
        user = User.objects.create_user("signal_user", password="pass123")
        self.assertTrue(hasattr(user, "profile"))
        self.assertIsInstance(user.profile, UserProfile)

    def test_default_role_is_buyer(self) -> None:
        """Роль по умолчанию — покупатель."""
        user = User.objects.create_user("default_role_user", password="pass123")
        self.assertEqual(user.profile.role, UserProfile.BUYER)


# ---------------------------------------------------------------------------
# 2. Product — валидация модели
# ---------------------------------------------------------------------------

class TestProductValidation(TestCase):
    """Проверяет бизнес-валидацию модели Product."""

    def setUp(self) -> None:
        self.category = Category.objects.create(name="Электроника", is_active=True)

    def test_discount_price_cannot_exceed_price(self) -> None:
        """Цена со скидкой не может быть больше или равна обычной цене."""
        product = Product(
            name="Тест", category=self.category, brand="X", model="Y",
            price=50000, discount_price=60000, condition="new",
            stock_quantity=5, warranty_months=12, release_year=2023, is_available=True,
        )
        with self.assertRaises(ValidationError):
            product.clean()

    def test_zero_stock_cannot_be_available(self) -> None:
        """Товар не может быть доступен при нулевом остатке."""
        product = Product(
            name="Тест", category=self.category, brand="X", model="Y",
            price=50000, condition="new", stock_quantity=0,
            warranty_months=12, release_year=2023, is_available=True,
        )
        with self.assertRaises(ValidationError):
            product.clean()

    def test_valid_discount_passes(self) -> None:
        """Корректная скидка (меньше цены) должна пройти валидацию."""
        product = Product(
            name="Тест", category=self.category, brand="X", model="Y",
            price=50000, discount_price=45000, condition="new",
            stock_quantity=5, warranty_months=12, release_year=2023, is_available=True,
        )
        product.clean()  # не должно бросать исключение


# ---------------------------------------------------------------------------
# 3. Order — лимит покупателя (BL: не более 10 единиц за заказ)
# ---------------------------------------------------------------------------

class TestOrderBuyerQuantityLimit(APITestCase):
    """Проверяет бизнес-правило: покупатель не может заказать более 10 единиц."""

    def setUp(self) -> None:
        self.category = Category.objects.create(name="Тест", is_active=True)
        self.product = make_product(self.category, stock=50)
        self.buyer = make_user("buyer_limit", UserProfile.BUYER)
        auth_client(self.client, self.buyer)

    def _order_data(self, quantity: int) -> dict:
        return {
            "product": self.product.id,
            "customer_name": "Иван Иванов",
            "customer_email": "ivan@test.com",
            "customer_phone": "+79001234567",
            "quantity": quantity,
            "delivery_address": "г. Москва, ул. Тверская, д. 10, 125009",
        }

    def test_buyer_cannot_order_more_than_10(self) -> None:
        """Заказ на 11 единиц должен быть отклонён с 400."""
        resp = self.client.post("/api/orders/", self._order_data(11), format="json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_buyer_can_order_exactly_10(self) -> None:
        """Заказ ровно на 10 единиц должен пройти."""
        resp = self.client.post("/api/orders/", self._order_data(10), format="json")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)


# ---------------------------------------------------------------------------
# 4. Order — управление остатком (создание/отмена)
# ---------------------------------------------------------------------------

class TestOrderStockManagement(APITestCase):
    """Проверяет корректное списание и восстановление остатка."""

    def setUp(self) -> None:
        self.category = Category.objects.create(name="Тест", is_active=True)
        self.product = make_product(self.category, stock=10)
        self.buyer = make_user("buyer_stock", UserProfile.BUYER)
        auth_client(self.client, self.buyer)

    def test_stock_decreases_after_order(self) -> None:
        """После создания заказа остаток должен уменьшиться."""
        data = {
            "product": self.product.id,
            "customer_name": "Иван", "customer_email": "ivan@test.com",
            "customer_phone": "+79001234567", "quantity": 3,
            "delivery_address": "г. Москва, ул. Тверская, д. 10, 125009",
        }
        self.client.post("/api/orders/", data, format="json")
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 7)

    def test_stock_restored_after_cancel(self) -> None:
        """После отмены заказа остаток должен вернуться."""
        order = make_order(self.product, self.buyer, quantity=3)
        self.product.stock_quantity -= 3
        self.product.save()

        resp = self.client.post(f"/api/orders/{order.id}/cancel/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 10)


# ---------------------------------------------------------------------------
# 5. Permissions — разграничение ролей
# ---------------------------------------------------------------------------

class TestRolePermissions(APITestCase):
    """Проверяет разграничение прав между ролями."""

    def setUp(self) -> None:
        self.category = Category.objects.create(name="Тест", is_active=True)
        self.buyer = make_user("perm_buyer", UserProfile.BUYER)
        self.manager = make_user("perm_manager", UserProfile.MANAGER)
        self.admin_user = make_user("perm_admin", UserProfile.ADMIN)
        self.product_data = {
            "name": "Новый товар", "category": self.category.id,
            "brand": "X", "model": "Y", "price": "1000.00",
            "condition": "new", "stock_quantity": 5,
            "warranty_months": 12, "release_year": 2023, "is_available": True,
        }

    def test_buyer_cannot_create_product(self) -> None:
        """Покупатель не может создавать товары (403)."""
        auth_client(self.client, self.buyer)
        resp = self.client.post("/api/products/", self.product_data, format="json")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_manager_can_create_product(self) -> None:
        """Менеджер может создавать товары (201)."""
        auth_client(self.client, self.manager)
        resp = self.client.post("/api/products/", self.product_data, format="json")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

    def test_buyer_cannot_access_suppliers(self) -> None:
        """Покупатель не имеет доступа к поставщикам (403)."""
        auth_client(self.client, self.buyer)
        resp = self.client.get("/api/suppliers/")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_manager_cannot_update_supplier_rating(self) -> None:
        """Менеджер не может изменять рейтинг поставщика — только администратор (403)."""
        supplier = Supplier.objects.create(
            name="Тест Снаб", contact_person="Тест", contact_email="s@test.com",
            contact_phone="+79001234567", address="Москва", country="Россия", rating=4.0,
        )
        auth_client(self.client, self.manager)
        resp = self.client.post(f"/api/suppliers/{supplier.id}/update_rating/", {"rating": 4.5}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_unauthenticated_can_read_products(self) -> None:
        """Анонимный пользователь может читать товары (200)."""
        resp = self.client.get("/api/products/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)


# ---------------------------------------------------------------------------
# 6. Order — покупатель видит только свои заказы
# ---------------------------------------------------------------------------

class TestOrderVisibility(APITestCase):
    """Проверяет, что покупатель видит только свои заказы."""

    def setUp(self) -> None:
        self.category = Category.objects.create(name="Тест", is_active=True)
        self.product = make_product(self.category)
        self.buyer1 = make_user("vis_buyer1", UserProfile.BUYER)
        self.buyer2 = make_user("vis_buyer2", UserProfile.BUYER)
        make_order(self.product, self.buyer1)
        make_order(self.product, self.buyer2)

    def test_buyer_sees_only_own_orders(self) -> None:
        """В списке заказов покупатель видит только заказы, привязанные к его аккаунту."""
        auth_client(self.client, self.buyer1)
        resp = self.client.get("/api/orders/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        for order in resp.data["results"]:
            self.assertEqual(order["user"], self.buyer1.id)

    def test_manager_sees_all_orders(self) -> None:
        """Менеджер видит все заказы."""
        manager = make_user("vis_manager", UserProfile.MANAGER)
        auth_client(self.client, manager)
        resp = self.client.get("/api/orders/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(resp.data["count"], 2)


# ---------------------------------------------------------------------------
# 7. Manager — ограничение скидки 50%
# ---------------------------------------------------------------------------

class TestManagerDiscountLimit(APITestCase):
    """Проверяет, что менеджер не может установить скидку более 50%."""

    def setUp(self) -> None:
        self.category = Category.objects.create(name="Тест", is_active=True)
        self.product = make_product(self.category, price=10000)
        self.manager = make_user("disc_manager", UserProfile.MANAGER)
        auth_client(self.client, self.manager)

    def test_manager_cannot_exceed_50_percent(self) -> None:
        """Скидка более 50% от менеджера должна вернуть 400."""
        resp = self.client.post(
            f"/api/products/{self.product.id}/apply_discount/",
            {"discount_percent": 60}, format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_manager_can_apply_exactly_50_percent(self) -> None:
        """Скидка ровно 50% от менеджера должна пройти."""
        resp = self.client.post(
            f"/api/products/{self.product.id}/apply_discount/",
            {"discount_percent": 50}, format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_admin_can_exceed_50_percent(self) -> None:
        """Администратор может установить скидку более 50%."""
        admin_user = make_user("disc_admin", UserProfile.ADMIN)
        auth_client(self.client, admin_user)
        resp = self.client.post(
            f"/api/products/{self.product.id}/apply_discount/",
            {"discount_percent": 70}, format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)


# ---------------------------------------------------------------------------
# 8. Review — дублирование запрещено
# ---------------------------------------------------------------------------

class TestReviewDuplicateValidation(APITestCase):
    """Проверяет, что нельзя оставить два отзыва с одним email на один товар."""

    def setUp(self) -> None:
        self.category = Category.objects.create(name="Тест", is_active=True)
        self.product = make_product(self.category)
        self.buyer = make_user("rev_buyer", UserProfile.BUYER)
        auth_client(self.client, self.buyer)
        Review.objects.create(
            product=self.product, customer_name="Иван",
            customer_email="ivan@test.com", rating=5,
            comment="Отличный товар, очень доволен!", is_approved=True,
        )

    def test_duplicate_review_rejected(self) -> None:
        """Повторный отзыв от одного email должен вернуть 400."""
        data = {
            "product": self.product.id,
            "customer_name": "Иван",
            "customer_email": "ivan@test.com",
            "rating": 4,
            "comment": "Второй отзыв на тот же товар попытка",
        }
        resp = self.client.post("/api/reviews/", data, format="json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)


# ---------------------------------------------------------------------------
# 9. Product FilterSet — фильтрация по цене
# ---------------------------------------------------------------------------

class TestProductPriceFilter(APITestCase):
    """Проверяет фильтрацию товаров по ценовому диапазону."""

    def setUp(self) -> None:
        self.category = Category.objects.create(name="Тест", is_active=True)
        make_product(self.category, name="Дешёвый", price=5000)
        make_product(self.category, name="Средний", price=30000)
        make_product(self.category, name="Дорогой", price=100000)

    def test_filter_by_max_price(self) -> None:
        """Фильтр max_price возвращает только товары дешевле или равно порогу."""
        resp = self.client.get("/api/products/?max_price=10000")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        for p in resp.data["results"]:
            self.assertLessEqual(float(p["price"]), 10000)

    def test_filter_by_price_range(self) -> None:
        """Фильтр min_price + max_price работает как диапазон."""
        resp = self.client.get("/api/products/?min_price=10000&max_price=50000")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        for p in resp.data["results"]:
            self.assertGreaterEqual(float(p["price"]), 10000)
            self.assertLessEqual(float(p["price"]), 50000)

    def test_filter_by_brand(self) -> None:
        """Фильтр brand (без учёта регистра) работает корректно."""
        resp = self.client.get("/api/products/?brand=testbrand")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["count"], 3)


# ---------------------------------------------------------------------------
# 10. Auth — регистрация и получение токена
# ---------------------------------------------------------------------------

class TestAuthEndpoints(APITestCase):
    """Проверяет регистрацию и получение токена."""

    def test_register_returns_token(self) -> None:
        """Успешная регистрация должна вернуть токен и ID пользователя."""
        data = {"username": "newuser1", "email": "new1@test.com", "password": "securepass123", "role": "buyer"}
        resp = self.client.post("/api/auth/register/", data, format="json")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertIn("token", resp.data)
        self.assertIn("user_id", resp.data)

    def test_register_duplicate_username_fails(self) -> None:
        """Регистрация с существующим именем пользователя должна вернуть 400."""
        User.objects.create_user("existing_user", password="pass123")
        data = {"username": "existing_user", "email": "ex@test.com", "password": "securepass123"}
        resp = self.client.post("/api/auth/register/", data, format="json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_obtain_token_with_valid_credentials(self) -> None:
        """Правильные учётные данные должны вернуть токен."""
        User.objects.create_user("token_user", password="testpass123")
        resp = self.client.post("/api/auth/token/", {"username": "token_user", "password": "testpass123"}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn("token", resp.data)


# ---------------------------------------------------------------------------
# 11. Order — бизнес-правила отмены для покупателя
# ---------------------------------------------------------------------------

class TestOrderCancelRules(APITestCase):
    """Проверяет ограничения на отмену заказов покупателем."""

    def setUp(self) -> None:
        self.category = Category.objects.create(name="Тест", is_active=True)
        self.product = make_product(self.category, stock=50)
        self.buyer = make_user("cancel_buyer", UserProfile.BUYER)
        auth_client(self.client, self.buyer)

    def test_buyer_cannot_cancel_shipped_order(self) -> None:
        """Покупатель не может отменить уже отправленный заказ (400)."""
        order = make_order(self.product, self.buyer, order_status="shipped")
        resp = self.client.post(f"/api/orders/{order.id}/cancel/")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_buyer_cannot_cancel_other_users_order(self) -> None:
        """Покупатель не может отменить чужой заказ — получает 404 (queryset скрывает чужие объекты)."""
        other = make_user("other_buyer_cancel", UserProfile.BUYER)
        order = make_order(self.product, other, order_status="pending")
        resp = self.client.post(f"/api/orders/{order.id}/cancel/")
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_buyer_can_cancel_own_pending_order(self) -> None:
        """Покупатель может отменить свой заказ в статусе pending (200)."""
        order = make_order(self.product, self.buyer, order_status="pending")
        resp = self.client.post(f"/api/orders/{order.id}/cancel/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)


# ---------------------------------------------------------------------------
# 12. Review — видимость поля moderation_info по роли
# ---------------------------------------------------------------------------

class TestReviewModerationInfoVisibility(APITestCase):
    """Проверяет, что moderation_info видно только менеджерам/администраторам."""

    def setUp(self) -> None:
        self.category = Category.objects.create(name="Тест", is_active=True)
        self.product = make_product(self.category)
        Review.objects.create(
            product=self.product, customer_name="Иван",
            customer_email="ivan_mod@test.com", rating=5,
            comment="Отличный товар, всё понравилось!", is_approved=True,
        )

    def test_buyer_does_not_see_moderation_info(self) -> None:
        """Покупатель не должен видеть поле moderation_info."""
        buyer = make_user("mod_buyer", UserProfile.BUYER)
        auth_client(self.client, buyer)
        resp = self.client.get("/api/reviews/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        for review in resp.data["results"]:
            self.assertIsNone(review["moderation_info"])

    def test_manager_sees_moderation_info(self) -> None:
        """Менеджер должен видеть поле moderation_info."""
        manager = make_user("mod_manager", UserProfile.MANAGER)
        auth_client(self.client, manager)
        resp = self.client.get("/api/reviews/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        for review in resp.data["results"]:
            self.assertIsNotNone(review["moderation_info"])


# ---------------------------------------------------------------------------
# 13. Cart — добавление товара и проверка наличия на складе
# ---------------------------------------------------------------------------

class TestCartAddItem(APITestCase):
    """Проверяет добавление товаров в корзину и валидацию остатка."""

    def setUp(self) -> None:
        self.category = Category.objects.create(name="Тест", is_active=True)
        self.product = make_product(self.category, price=1000, stock=5)
        self.buyer = make_user("cart_buyer", UserProfile.BUYER)
        auth_client(self.client, self.buyer)

    def test_add_item_creates_cart_position(self) -> None:
        """Добавление товара создаёт позицию и считает сумму."""
        resp = self.client.post(
            "/api/cart/add_item/", {"product": self.product.id, "quantity": 2}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["total_quantity"], 2)
        self.assertEqual(float(resp.data["total_price"]), 2000)

    def test_add_item_rejects_over_stock(self) -> None:
        """Нельзя добавить больше, чем есть на складе (400)."""
        resp = self.client.post(
            "/api/cart/add_item/", {"product": self.product.id, "quantity": 99}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(CartItem.objects.count(), 0)

    def test_add_item_accumulates_quantity(self) -> None:
        """Повторное добавление суммирует количество."""
        self.client.post("/api/cart/add_item/", {"product": self.product.id, "quantity": 1}, format="json")
        self.client.post("/api/cart/add_item/", {"product": self.product.id, "quantity": 2}, format="json")
        item = CartItem.objects.get(product=self.product)
        self.assertEqual(item.quantity, 3)


# ---------------------------------------------------------------------------
# 14. Cart — оформление заказа (checkout) из корзины
# ---------------------------------------------------------------------------

class TestCartCheckout(APITestCase):
    """Проверяет оформление заказа из корзины."""

    def setUp(self) -> None:
        self.category = Category.objects.create(name="Тест", is_active=True)
        self.product = make_product(self.category, price=1000, stock=10)
        self.buyer = make_user("checkout_buyer", UserProfile.BUYER)
        auth_client(self.client, self.buyer)
        self.client.post(
            "/api/cart/add_item/", {"product": self.product.id, "quantity": 3}, format="json"
        )

    def _checkout(self, address: str = VALID_ADDRESS):
        return self.client.post(
            "/api/cart/checkout/",
            {
                "customer_name": "Иван Иванов",
                "customer_email": "ivan@test.com",
                "customer_phone": "+79001234567",
                "delivery_address": address,
            },
            format="json",
        )

    def test_checkout_creates_order_and_clears_cart(self) -> None:
        """Checkout создаёт заказ, списывает склад, очищает корзину и шлёт письмо."""
        resp = self._checkout()
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(len(resp.data["order_ids"]), 1)
        self.assertEqual(Order.objects.filter(user=self.buyer).count(), 1)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 7)
        self.assertEqual(CartItem.objects.count(), 0)
        # Письмо-подтверждение ушло покупателю
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("ivan@test.com", mail.outbox[0].to)

    def test_checkout_rejects_invalid_address(self) -> None:
        """Checkout с некорректным адресом отклоняется (400)."""
        resp = self._checkout(address="Москва")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Order.objects.count(), 0)

    def test_checkout_empty_cart_rejected(self) -> None:
        """Checkout с пустой корзиной отклоняется (400)."""
        self.client.post("/api/cart/clear/", format="json")
        resp = self._checkout()
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)


# ---------------------------------------------------------------------------
# 15. Favorites — переключение и поле is_favorite через контекст
# ---------------------------------------------------------------------------

class TestFavorites(APITestCase):
    """Проверяет избранное: toggle, is_favorite, аннотацию favorites_count."""

    def setUp(self) -> None:
        self.category = Category.objects.create(name="Тест", is_active=True)
        self.product = make_product(self.category)
        self.buyer = make_user("fav_buyer", UserProfile.BUYER)
        auth_client(self.client, self.buyer)

    def test_toggle_adds_then_removes(self) -> None:
        """Первый toggle добавляет в избранное, второй — убирает."""
        resp1 = self.client.post("/api/favorites/toggle/", {"product": self.product.id}, format="json")
        self.assertEqual(resp1.status_code, status.HTTP_201_CREATED)
        self.assertTrue(resp1.data["is_favorite"])
        self.assertEqual(Favorite.objects.filter(user=self.buyer).count(), 1)

        resp2 = self.client.post("/api/favorites/toggle/", {"product": self.product.id}, format="json")
        self.assertFalse(resp2.data["is_favorite"])
        self.assertEqual(Favorite.objects.filter(user=self.buyer).count(), 0)

    def test_is_favorite_flag_in_product_list(self) -> None:
        """Поле is_favorite в списке товаров отражает избранное пользователя."""
        Favorite.objects.create(user=self.buyer, product=self.product)
        resp = self.client.get("/api/products/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        target = next(p for p in resp.data["results"] if p["id"] == self.product.id)
        self.assertTrue(target["is_favorite"])
        self.assertEqual(target["favorites_count"], 1)

    def test_favorites_only_own(self) -> None:
        """Пользователь видит в избранном только свои записи."""
        other = make_user("fav_other", UserProfile.BUYER)
        Favorite.objects.create(user=other, product=self.product)
        resp = self.client.get("/api/favorites/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["count"], 0)


# ---------------------------------------------------------------------------
# 16. Валидация адреса доставки и суммы заказа
# ---------------------------------------------------------------------------

class TestOrderValidationRules(APITestCase):
    """Проверяет валидацию формата адреса и суммы заказа при создании."""

    def setUp(self) -> None:
        self.category = Category.objects.create(name="Тест", is_active=True)
        self.buyer = make_user("val_buyer", UserProfile.BUYER)
        auth_client(self.client, self.buyer)

    def _order(self, product: Product, quantity: int, address: str = VALID_ADDRESS) -> dict:
        return {
            "product": product.id,
            "customer_name": "Иван", "customer_email": "ivan@test.com",
            "customer_phone": "+79001234567", "quantity": quantity,
            "delivery_address": address,
        }

    def test_invalid_address_rejected(self) -> None:
        """Адрес без индекса и компонентов отклоняется (400)."""
        product = make_product(self.category, price=1000, stock=10)
        resp = self.client.post("/api/orders/", self._order(product, 1, address="Москва"), format="json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("delivery_address", resp.data)

    def test_amount_below_minimum_rejected(self) -> None:
        """Сумма заказа меньше 500 ₽ отклоняется (400)."""
        cheap = make_product(self.category, name="Дешёвый", price=100, stock=10)
        resp = self.client.post("/api/orders/", self._order(cheap, 1), format="json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_amount_above_maximum_rejected(self) -> None:
        """Сумма заказа больше 100 000 ₽ отклоняется (400)."""
        pricey = make_product(self.category, name="Дорогой", price=60000, stock=10)
        resp = self.client.post("/api/orders/", self._order(pricey, 2), format="json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_valid_order_passes(self) -> None:
        """Корректный заказ (адрес + сумма в норме) проходит (201)."""
        product = make_product(self.category, price=1000, stock=10)
        resp = self.client.post("/api/orders/", self._order(product, 2), format="json")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
