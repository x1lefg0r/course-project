from datetime import date
from rest_framework import serializers
from django.contrib.auth.models import User
from .models import Category, Product, Order, Review, Supplier, UserProfile


class UserProfileSerializer(serializers.ModelSerializer):
    """Сериализатор профиля пользователя с ролью."""

    username = serializers.CharField(source="user.username", read_only=True)
    email = serializers.EmailField(source="user.email", read_only=True)
    role_display = serializers.CharField(source="get_role_display", read_only=True)

    class Meta:
        model = UserProfile
        fields = ["id", "username", "email", "role", "role_display", "phone", "address", "created_at"]
        read_only_fields = ["created_at"]


class UserRegisterSerializer(serializers.ModelSerializer):
    """Сериализатор регистрации нового пользователя."""

    password = serializers.CharField(write_only=True, min_length=8)
    role = serializers.ChoiceField(
        choices=UserProfile.ROLE_CHOICES,
        default=UserProfile.BUYER,
        required=False,
        write_only=True,
    )

    class Meta:
        model = User
        fields = ["id", "username", "email", "password", "role"]

    def create(self, validated_data: dict) -> User:
        """Создаёт пользователя и устанавливает ему роль."""
        role = validated_data.pop("role", UserProfile.BUYER)
        user = User.objects.create_user(
            username=validated_data["username"],
            email=validated_data.get("email", ""),
            password=validated_data["password"],
        )
        UserProfile.objects.filter(user=user).update(role=role)
        return user


class CategorySerializer(serializers.ModelSerializer):
    """Сериализатор для категорий с аннотированными полями."""

    products_count = serializers.IntegerField(read_only=True, default=0)
    avg_price = serializers.DecimalField(
        max_digits=10, decimal_places=2, read_only=True, default=None, allow_null=True
    )
    total_stock = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = Category
        fields = ["id", "name", "description", "is_active", "created_at", "products_count", "avg_price", "total_stock"]
        read_only_fields = ["created_at"]

    def validate_name(self, value: str) -> str:
        """Валидация названия: минимум 3 символа."""
        if len(value) < 3:
            raise serializers.ValidationError("Название категории должно быть не менее 3 символов")
        return value


class ProductSerializer(serializers.ModelSerializer):
    """Сериализатор для товаров с аннотациями и контекстно-зависимыми полями."""

    category_name = serializers.CharField(source="category.name", read_only=True)
    discount_percentage = serializers.SerializerMethodField()
    final_price = serializers.SerializerMethodField()
    reviews_count = serializers.IntegerField(read_only=True, default=0)
    avg_rating = serializers.FloatField(read_only=True, default=None, allow_null=True)
    total_ordered = serializers.IntegerField(read_only=True, default=0)
    stock_alert = serializers.SerializerMethodField()
    can_order = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            "id", "name", "category", "category_name", "brand", "model", "description",
            "price", "discount_price", "discount_percentage", "final_price",
            "condition", "stock_quantity", "warranty_months", "release_year", "is_available",
            "created_at", "updated_at",
            "reviews_count", "avg_rating", "total_ordered",
            "stock_alert", "can_order",
        ]
        read_only_fields = ["created_at", "updated_at"]

    def get_discount_percentage(self, obj: Product) -> float:
        """Вычисляет процент скидки от обычной цены."""
        if obj.discount_price:
            return round(float((obj.price - obj.discount_price) / obj.price * 100), 2)
        return 0

    def get_final_price(self, obj: Product):
        """Возвращает итоговую цену с учётом скидки."""
        return obj.discount_price if obj.discount_price else obj.price

    def get_stock_alert(self, obj: Product) -> str | None:
        """
        Предупреждение о низком остатке на складе.

        Args:
            obj: Объект товара

        Видно только менеджерам и администраторам (из контекста запроса).
        """
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return None
        try:
            role = request.user.profile.role
        except AttributeError:
            return None
        if role not in ("admin", "manager"):
            return None
        if obj.stock_quantity == 0:
            return "Нет в наличии"
        if obj.stock_quantity < 5:
            return f"Низкий остаток: {obj.stock_quantity} шт."
        return None

    def get_can_order(self, obj: Product) -> bool:
        """
        Проверяет, может ли текущий пользователь заказать товар.

        Args:
            obj: Объект товара
        """
        request = self.context.get("request")
        if not obj.is_available or obj.stock_quantity <= 0:
            return False
        return bool(request and request.user.is_authenticated)

    def validate_price(self, value) -> ...:
        """Валидация цены: от 0 до 1 000 000."""
        if value <= 0:
            raise serializers.ValidationError("Цена должна быть больше нуля")
        if value > 1_000_000:
            raise serializers.ValidationError("Цена не может превышать 1,000,000")
        return value

    def validate_stock_quantity(self, value: int) -> int:
        """Валидация количества на складе: неотрицательное."""
        if value < 0:
            raise serializers.ValidationError("Количество на складе не может быть отрицательным")
        return value

    def validate(self, data: dict) -> dict:
        """
        Комплексная валидация: скидка < цена, менеджер ≤ 50%.

        Args:
            data: Словарь с данными товара
        """
        if data.get("discount_price") and data.get("price"):
            if data["discount_price"] >= data["price"]:
                raise serializers.ValidationError(
                    {"discount_price": "Цена со скидкой должна быть меньше обычной цены"}
                )
            request = self.context.get("request")
            if request and request.user.is_authenticated:
                try:
                    role = request.user.profile.role
                except AttributeError:
                    role = None
                if role == "manager":
                    pct = float(data["price"] - data["discount_price"]) / float(data["price"]) * 100
                    if pct > 50:
                        raise serializers.ValidationError(
                            {"discount_price": "Менеджер не может устанавливать скидку более 50%"}
                        )
        return data


class OrderSerializer(serializers.ModelSerializer):
    """Сериализатор для заказов с проверкой принадлежности через контекст."""

    product_name = serializers.CharField(source="product.name", read_only=True)
    product_brand = serializers.CharField(source="product.brand", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    is_owner = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = [
            "id", "user", "product", "product_name", "product_brand",
            "customer_name", "customer_email", "customer_phone",
            "quantity", "total_price", "status", "status_display",
            "delivery_address", "order_date", "delivery_date", "notes",
            "is_owner",
        ]
        read_only_fields = ["order_date", "total_price", "user"]

    def get_is_owner(self, obj: Order) -> bool:
        """
        Проверяет, принадлежит ли заказ текущему пользователю.

        Args:
            obj: Объект заказа
        """
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return False
        return obj.user == request.user

    def validate_customer_phone(self, value: str) -> str:
        """Валидация телефона: минимум 10 цифр."""
        cleaned = "".join(filter(str.isdigit, value))
        if len(cleaned) < 10:
            raise serializers.ValidationError("Номер телефона должен содержать минимум 10 цифр")
        return value

    def validate_quantity(self, value: int) -> int:
        """
        Валидация количества.

        Args:
            value: Количество единиц товара

        Покупатели ограничены 10 единицами за заказ (BL).
        """
        if value <= 0:
            raise serializers.ValidationError("Количество должно быть больше нуля")
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            try:
                role = request.user.profile.role
            except AttributeError:
                role = None
            if role == "buyer" and value > 10:
                raise serializers.ValidationError("Покупатель может заказать не более 10 единиц за раз")
        if value > 100:
            raise serializers.ValidationError("Нельзя заказать больше 100 единиц товара за раз")
        return value

    def create(self, validated_data: dict) -> Order:
        """
        Создаёт заказ, проверяет наличие, списывает остаток.

        Args:
            validated_data: Валидированные данные заказа
        """
        product = validated_data["product"]
        quantity = validated_data["quantity"]

        if quantity > product.stock_quantity:
            raise serializers.ValidationError(
                f"Недостаточно товара на складе. Доступно: {product.stock_quantity}"
            )

        final_price = product.discount_price if product.discount_price else product.price
        validated_data["total_price"] = final_price * quantity

        request = self.context.get("request")
        if request and request.user.is_authenticated:
            validated_data["user"] = request.user

        order = Order.objects.create(**validated_data)
        product.stock_quantity -= quantity
        if product.stock_quantity == 0:
            product.is_available = False
        product.save()
        return order


class SupplierSerializer(serializers.ModelSerializer):
    """Сериализатор для поставщиков с аннотированным количеством товаров."""

    products_count = serializers.IntegerField(read_only=True, default=0)
    products_list = serializers.SerializerMethodField()

    class Meta:
        model = Supplier
        fields = [
            "id", "name", "contact_person", "contact_email", "contact_phone",
            "address", "country", "is_active", "rating",
            "products", "products_count", "products_list", "created_at",
        ]
        read_only_fields = ["created_at"]

    def get_products_list(self, obj: Supplier) -> list[str]:
        """Возвращает названия первых 5 товаров поставщика."""
        return [p.name for p in obj.products.all()[:5]]

    def validate_rating(self, value) -> ...:
        """Валидация рейтинга: от 0 до 5."""
        if value < 0 or value > 5:
            raise serializers.ValidationError("Рейтинг должен быть от 0 до 5")
        return value

    def validate_contact_email(self, value: str) -> str:
        """Валидация email поставщика."""
        if not value or "@" not in value:
            raise serializers.ValidationError("Некорректный email")
        return value


class ReviewSerializer(serializers.ModelSerializer):
    """Сериализатор для отзывов с полем модерации, видимым только менеджерам/администраторам."""

    product_name = serializers.CharField(source="product.name", read_only=True)
    rating_display = serializers.CharField(source="get_rating_display", read_only=True)
    moderation_info = serializers.SerializerMethodField()

    class Meta:
        model = Review
        fields = [
            "id", "product", "product_name",
            "customer_name", "customer_email",
            "rating", "rating_display", "comment", "advantages", "disadvantages",
            "is_approved", "is_verified_purchase",
            "created_at", "updated_at", "moderation_info",
        ]
        read_only_fields = ["created_at", "updated_at", "is_approved", "is_verified_purchase"]

    def get_moderation_info(self, obj: Review) -> dict | None:
        """
        Данные модерации отзыва (только для менеджеров и администраторов).

        Args:
            obj: Объект отзыва
        """
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return None
        try:
            role = request.user.profile.role
        except AttributeError:
            return None
        if role not in ("admin", "manager"):
            return None
        return {
            "approved_status": "одобрен" if obj.is_approved else "на модерации",
            "is_verified_purchase": obj.is_verified_purchase,
            "days_since_created": (date.today() - obj.created_at.date()).days,
        }

    def validate_rating(self, value: int) -> int:
        """Валидация оценки: от 1 до 5."""
        if value < 1 or value > 5:
            raise serializers.ValidationError("Оценка должна быть от 1 до 5")
        return value

    def validate_comment(self, value: str) -> str:
        """Валидация комментария: от 10 до 2000 символов."""
        if len(value) < 10:
            raise serializers.ValidationError("Комментарий должен содержать минимум 10 символов")
        if len(value) > 2000:
            raise serializers.ValidationError("Комментарий не может быть длиннее 2000 символов")
        return value

    def validate(self, data: dict) -> dict:
        """Запрет повторного отзыва от одного покупателя на один товар."""
        if not self.instance:
            if Review.objects.filter(
                product=data.get("product"),
                customer_email=data.get("customer_email"),
            ).exists():
                raise serializers.ValidationError("Вы уже оставляли отзыв на этот товар")
        return data
