from datetime import date
from django.db import models
from django.core.exceptions import ValidationError
from simple_history.models import HistoricalRecords
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver


class Category(models.Model):
    """Категория товаров"""

    name = models.CharField(max_length=100, unique=True, verbose_name="Название")
    description = models.TextField(blank=True, verbose_name="Описание")
    is_active = models.BooleanField(default=True, verbose_name="Активна")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")

    history = HistoricalRecords()

    class Meta:
        verbose_name = "Категория"
        verbose_name_plural = "Категории"
        ordering = ["name"]

    def __str__(self):
        return str(self.name)


class Product(models.Model):
    """Товар (электроника)"""

    CONDITION_CHOICES = [
        ("new", "Новый"),
        ("refurbished", "Восстановленный"),
        ("used", "Б/У"),
    ]

    name = models.CharField(max_length=200, verbose_name="Название")
    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        related_name="products",
        verbose_name="Категория",
    )
    brand = models.CharField(max_length=100, verbose_name="Бренд")
    model = models.CharField(max_length=100, verbose_name="Модель")
    description = models.TextField(blank=True, verbose_name="Описание")
    price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Цена")
    discount_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Цена со скидкой",
    )
    condition = models.CharField(
        max_length=20,
        choices=CONDITION_CHOICES,
        default="new",
        verbose_name="Состояние",
    )
    stock_quantity = models.IntegerField(default=0, verbose_name="Количество на складе")
    warranty_months = models.IntegerField(default=12, verbose_name="Гарантия (месяцев)")
    release_year = models.IntegerField(verbose_name="Год выпуска")
    is_available = models.BooleanField(default=True, verbose_name="Доступен для заказа")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата добавления")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")

    history = HistoricalRecords()

    class Meta:
        verbose_name = "Товар"
        verbose_name_plural = "Товары"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.brand} {self.model}"

    def clean(self):
        """Валидация бизнес-логики"""
        if self.discount_price and self.discount_price >= self.price:
            raise ValidationError(
                {"discount_price": "Цена со скидкой должна быть меньше обычной цены"}
            )

        current_year = date.today().year
        if self.release_year > current_year:
            raise ValidationError(
                {"release_year": f"Год выпуска не может быть больше {current_year}"}
            )

        if self.stock_quantity <= 0 and self.is_available:
            raise ValidationError(
                {
                    "is_available": "Товар не может быть доступен при нулевом количестве на складе"
                }
            )


class Order(models.Model):
    """Заказ"""

    STATUS_CHOICES = [
        ("pending", "Ожидает обработки"),
        ("processing", "В обработке"),
        ("shipped", "Отправлен"),
        ("delivered", "Доставлен"),
        ("cancelled", "Отменён"),
    ]

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="orders",
        null=True,
        blank=True,
        verbose_name="Пользователь",
    )

    product = models.ForeignKey(
        Product, on_delete=models.PROTECT, related_name="orders", verbose_name="Товар"
    )
    customer_name = models.CharField(max_length=200, verbose_name="Имя покупателя")
    customer_email = models.EmailField(verbose_name="Email покупателя")
    customer_phone = models.CharField(max_length=20, verbose_name="Телефон")
    quantity = models.IntegerField(default=1, verbose_name="Количество")
    total_price = models.DecimalField(
        max_digits=10, decimal_places=2, verbose_name="Общая сумма"
    )
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default="pending", verbose_name="Статус"
    )
    delivery_address = models.TextField(verbose_name="Адрес доставки")
    order_date = models.DateTimeField(auto_now_add=True, verbose_name="Дата заказа")
    delivery_date = models.DateField(
        null=True, blank=True, verbose_name="Дата доставки"
    )
    notes = models.TextField(blank=True, verbose_name="Примечания")

    history = HistoricalRecords()

    class Meta:
        verbose_name = "Заказ"
        verbose_name_plural = "Заказы"
        ordering = ["-order_date"]

    def __str__(self):
        return f"Заказ #{self.id}-{self.customer_name}"

    def clean(self):
        """Валидация бизнес-логики"""
        if self.quantity <= 0:
            raise ValidationError({"quantity": "Количество должно быть больше нуля"})

        if self.product and self.quantity > self.product.stock_quantity:
            raise ValidationError(
                {
                    "quantity": f"Недостаточно товара на складе. Доступно: {self.product.stock_quantity}"
                }
            )


class Supplier(models.Model):
    """Поставщик"""

    name = models.CharField(max_length=200, unique=True, verbose_name="Название")
    contact_person = models.CharField(max_length=200, verbose_name="Контактное лицо")
    contact_email = models.EmailField(verbose_name="Email")
    contact_phone = models.CharField(max_length=20, verbose_name="Телефон")
    address = models.TextField(verbose_name="Адрес")
    country = models.CharField(max_length=100, verbose_name="Страна")
    is_active = models.BooleanField(default=True, verbose_name="Активен")
    rating = models.DecimalField(
        max_digits=3, decimal_places=2, default=5.0, verbose_name="Рейтинг"
    )
    products = models.ManyToManyField(
        Product, related_name="suppliers", blank=True, verbose_name="Товары"
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата добавления")

    history = HistoricalRecords()

    class Meta:
        verbose_name = "Поставщик"
        verbose_name_plural = "Поставщики"
        ordering = ["-rating", "name"]

    def __str__(self):
        return str(self.name)

    def clean(self):
        """Валидация бизнес-логики"""
        if self.rating < 0 or self.rating > 5:
            raise ValidationError({"rating": "Рейтинг должен быть от 0 до 5"})


class Review(models.Model):
    """Отзыв на товар"""

    RATING_CHOICES = [
        (1, "Ужасно"),
        (2, "Плохо"),
        (3, "Нормально"),
        (4, "Хорошо"),
        (5, "Отлично"),
    ]

    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="reviews", verbose_name="Товар"
    )
    customer_name = models.CharField(max_length=200, verbose_name="Имя покупателя")
    customer_email = models.EmailField(verbose_name="Email покупателя")
    rating = models.IntegerField(choices=RATING_CHOICES, verbose_name="Оценка")
    comment = models.TextField(verbose_name="Комментарий")
    advantages = models.TextField(blank=True, verbose_name="Достоинства")
    disadvantages = models.TextField(blank=True, verbose_name="Недостатки")
    is_approved = models.BooleanField(default=False, verbose_name="Одобрен")
    is_verified_purchase = models.BooleanField(
        default=False, verbose_name="Подтверждённая покупка"
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")

    history = HistoricalRecords()

    class Meta:
        verbose_name = "Отзыв"
        verbose_name_plural = "Отзывы"
        ordering = ["-created_at"]
        unique_together = [["product", "customer_email"]]

    def __str__(self):
        return f"Отзыв от {self.customer_name} на {self.product.name}"

    def clean(self):
        """Валидация бизнес-логики"""
        if self.rating and (self.rating < 1 or self.rating > 5):
            raise ValidationError({"rating": "Оценка должна быть от 1 до 5"})

        if len(self.comment) < 10:
            raise ValidationError(
                {"comment": "Комментарий должен содержать минимум 10 символов"}
            )


class UserProfile(models.Model):
    """Профиль пользователя с ролью в системе."""

    ADMIN = "admin"
    MANAGER = "manager"
    BUYER = "buyer"

    ROLE_CHOICES = [
        (ADMIN, "Администратор"),
        (MANAGER, "Менеджер"),
        (BUYER, "Покупатель"),
    ]

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="profile",
        verbose_name="Пользователь",
    )
    role = models.CharField(
        max_length=20,
        choices=ROLE_CHOICES,
        default=BUYER,
        verbose_name="Роль",
    )
    phone = models.CharField(max_length=20, blank=True, verbose_name="Телефон")
    address = models.TextField(blank=True, verbose_name="Адрес")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата регистрации")

    class Meta:
        verbose_name = "Профиль пользователя"
        verbose_name_plural = "Профили пользователей"

    def __str__(self) -> str:
        return f"{self.user.username} ({self.get_role_display()})"

    @property
    def is_admin(self) -> bool:
        return self.role == self.ADMIN

    @property
    def is_manager(self) -> bool:
        return self.role == self.MANAGER

    @property
    def is_buyer(self) -> bool:
        return self.role == self.BUYER


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs) -> None:
    """Автоматически создаёт профиль при регистрации нового пользователя."""
    if created:
        UserProfile.objects.get_or_create(user=instance)
