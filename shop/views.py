from datetime import date, timedelta

from django.db.models import Count, Avg, Sum, Q
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from rest_framework import viewsets, filters, status, serializers
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend

from .filters import ProductFilter, OrderFilter, ReviewFilter, SupplierFilter
from .models import (
    Category, Product, Order, Supplier, Review, UserProfile, Cart, CartItem, Favorite,
)
from .permissions import IsAdminRole, IsManagerOrAdmin, IsOwnerOrManagerAdmin
from .serializers import (
    CategorySerializer,
    ProductSerializer,
    OrderSerializer,
    SupplierSerializer,
    ReviewSerializer,
    UserProfileSerializer,
    UserRegisterSerializer,
    CartSerializer,
    FavoriteSerializer,
)
from .validators import validate_delivery_address, validate_order_amount
from .emails import send_order_confirmation
from .queries import (
    complex_query_1,
    complex_query_2,
    complex_query_3,
    complex_query_4,
    complex_query_5,
    complex_query_6,
)
from .forms import ProductCreateForm


# ---------------------------------------------------------------------------
# Auth API views
# ---------------------------------------------------------------------------

@api_view(["POST"])
@permission_classes([AllowAny])
def register_view(request):
    """
    Регистрация нового пользователя.

    Args:
        request: HTTP-запрос с полями username, email, password, role
    """
    serializer = UserRegisterSerializer(data=request.data)
    if serializer.is_valid():
        user = serializer.save()
        from rest_framework.authtoken.models import Token
        token, _ = Token.objects.get_or_create(user=user)
        return Response(
            {"token": token.key, "user_id": user.id, "username": user.username},
            status=status.HTTP_201_CREATED,
        )
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


def oauth_success_view(request):
    """
    Редирект на главную после успешного OAuth2-входа через Google.

    Args:
        request: HTTP-запрос аутентифицированного пользователя
    """
    from django.contrib import messages
    from rest_framework.authtoken.models import Token

    if request.user.is_authenticated:
        Token.objects.get_or_create(user=request.user)  # создаём токен, но не показываем
        messages.success(request, f"Добро пожаловать, {request.user.username}!")
    return redirect("product_list")


@api_view(["GET", "PATCH"])
@permission_classes([IsAuthenticated])
def profile_view(request):
    """
    Просмотр и редактирование профиля текущего пользователя.

    Args:
        request: HTTP-запрос; PATCH — обновление полей phone, address
    """
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    if request.method == "PATCH":
        serializer = UserProfileSerializer(profile, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    return Response(UserProfileSerializer(profile).data)


# ---------------------------------------------------------------------------
# API ViewSets
# ---------------------------------------------------------------------------

class CategoryViewSet(viewsets.ModelViewSet):
    """API для управления категориями товаров."""

    queryset = Category.objects.annotate(
        products_count=Count("products", distinct=True),
        avg_price=Avg("products__price"),
        total_stock=Sum("products__stock_quantity"),
    )
    serializer_class = CategorySerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ["is_active"]
    search_fields = ["name", "description"]
    ordering_fields = ["name", "created_at", "products_count"]

    def get_permissions(self):
        """
        Разграничение доступа по ролям.

        Чтение — всем; запись — только менеджерам/администраторам.
        """
        if self.action in ("list", "retrieve", "popular", "complex_filter_3"):
            return [AllowAny()]
        return [IsManagerOrAdmin()]

    @action(methods=["GET"], detail=False)
    def popular(self, request):
        """Топ-5 категорий по количеству товаров."""
        categories = (
            Category.objects.annotate(products_count=Count("products", distinct=True))
            .filter(products_count__gt=0)
            .order_by("-products_count")[:5]
        )
        serializer = self.get_serializer(categories, many=True)
        return Response(serializer.data)

    @action(methods=["POST"], detail=True)
    def toggle_active(self, request, pk=None):
        """
        Переключить статус активности категории.

        Args:
            request: HTTP-запрос
            pk: Первичный ключ категории
        """
        category = self.get_object()
        category.is_active = not category.is_active
        category.save()
        return Response({
            "status": "success",
            "message": f'Категория {"активирована" if category.is_active else "деактивирована"}',
            "is_active": category.is_active,
        })

    @action(methods=["GET"], detail=False)
    def complex_filter_3(self, request):
        """Сложный запрос 3: активные премиум-категории (ср. цена > 30 000 ₽)."""
        categories = complex_query_3()
        serializer = self.get_serializer(categories, many=True)
        return Response({
            "count": categories.count(),
            "description": "Премиум-категории (ср. цена >30000₽) с новыми/акционными товарами",
            "results": serializer.data,
        })


class ProductViewSet(viewsets.ModelViewSet):
    """API для управления товарами с фильтрацией, сортировкой и аннотациями."""

    queryset = Product.objects.select_related("category").annotate(
        reviews_count=Count("reviews", filter=Q(reviews__is_approved=True), distinct=True),
        avg_rating=Avg("reviews__rating", filter=Q(reviews__is_approved=True)),
        total_ordered=Sum("orders__quantity"),
        favorites_count=Count("favorited_by", distinct=True),
    )
    serializer_class = ProductSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = ProductFilter
    search_fields = ["name", "brand", "model", "description"]
    ordering_fields = ["price", "created_at", "stock_quantity", "release_year", "avg_rating"]

    def get_serializer_context(self) -> dict:
        """
        Дополняет контекст списком id избранных товаров пользователя.

        Список получается одним запросом и используется сериализатором
        для поля ``is_favorite`` (без N+1 на каждый товар).
        """
        context = super().get_serializer_context()
        user = self.request.user
        if user.is_authenticated:
            context["favorites_products"] = list(
                Favorite.objects.filter(user=user).values_list("product_id", flat=True)
            )
        return context

    def get_permissions(self):
        """
        Чтение доступно всем; изменение — только менеджерам/администраторам.
        """
        if self.action in (
            "list", "retrieve", "on_sale", "low_stock",
            "complex_filter_1", "complex_filter_4",
            "list_by_category", "list_by_brand",
        ):
            return [AllowAny()]
        return [IsManagerOrAdmin()]

    @action(methods=["GET"], detail=False)
    def on_sale(self, request):
        """Товары со скидкой, отсортированные по цене со скидкой."""
        products = self.get_queryset().filter(discount_price__isnull=False, is_available=True).order_by("discount_price")
        page = self.paginate_queryset(products)
        if page is not None:
            return self.get_paginated_response(self.get_serializer(page, many=True).data)
        return Response(self.get_serializer(products, many=True).data)

    @action(methods=["GET"], detail=False)
    def low_stock(self, request):
        """Товары с низким остатком на складе (менее 5 штук)."""
        products = self.get_queryset().filter(stock_quantity__lt=5, stock_quantity__gt=0)
        return Response(self.get_serializer(products, many=True).data)

    @action(methods=["POST"], detail=True)
    def apply_discount(self, request, pk=None):
        """
        Применить скидку к товару.

        Args:
            request: HTTP-запрос с полем discount_percent (0–100)
            pk: Первичный ключ товара

        BL: менеджер не может выставить скидку более 50%.
        """
        product = self.get_object()
        discount_percent = request.data.get("discount_percent")
        if not discount_percent:
            return Response({"error": "Укажите процент скидки (discount_percent)"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            discount_percent = float(discount_percent)
            if discount_percent <= 0 or discount_percent >= 100:
                raise ValueError
        except (ValueError, TypeError):
            return Response({"error": "Процент скидки должен быть числом от 0 до 100"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            role = request.user.profile.role
        except AttributeError:
            role = None
        if role == "manager" and discount_percent > 50:
            return Response({"error": "Менеджер не может устанавливать скидку более 50%"}, status=status.HTTP_400_BAD_REQUEST)

        from decimal import Decimal
        product.discount_price = product.price * (Decimal("1") - Decimal(str(discount_percent)) / Decimal("100"))
        product.save()
        return Response({
            "status": "success",
            "message": f"Скидка {discount_percent}% применена",
            "product": self.get_serializer(product).data,
        })

    @action(methods=["POST"], detail=True)
    def restock(self, request, pk=None):
        """
        Пополнить остаток товара на складе.

        Args:
            request: HTTP-запрос с полем quantity
            pk: Первичный ключ товара
        """
        product = self.get_object()
        quantity = request.data.get("quantity")
        if not quantity:
            return Response({"error": "Укажите количество (quantity)"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            quantity = int(quantity)
            if quantity <= 0:
                raise ValueError
        except (ValueError, TypeError):
            return Response({"error": "Количество должно быть положительным числом"}, status=status.HTTP_400_BAD_REQUEST)

        product.stock_quantity += quantity
        if product.stock_quantity > 0:
            product.is_available = True
        product.save()
        return Response({
            "status": "success",
            "message": f"Добавлено {quantity} единиц товара",
            "stock_quantity": product.stock_quantity,
        })

    def list_by_category(self, request, category_id=None):
        """
        Товары по ID категории (URL-параметр).

        Args:
            request: HTTP-запрос
            category_id: ID категории
        """
        products = self.get_queryset().filter(category_id=category_id)
        return Response({"category_id": category_id, "count": products.count(), "results": self.get_serializer(products, many=True).data})

    def list_by_brand(self, request, brand_name=None):
        """
        Товары по бренду (URL-параметр).

        Args:
            request: HTTP-запрос
            brand_name: Название бренда
        """
        products = self.get_queryset().filter(brand__iexact=brand_name)
        return Response({"brand": brand_name, "count": products.count(), "results": self.get_serializer(products, many=True).data})

    @action(methods=["GET"], detail=False)
    def complex_filter_1(self, request):
        """Сложный запрос 1: новые/восстановленные, дешёвые или со скидкой, не наушники."""
        products = complex_query_1()
        return Response({
            "count": products.count(),
            "description": "Новые/восстановленные товары < 50000₽ или со скидкой (не наушники)",
            "results": self.get_serializer(products, many=True).data,
        })

    @action(methods=["GET"], detail=False)
    def complex_filter_4(self, request):
        """Сложный запрос 4: топ-бренды после 2020 года с малым остатком."""
        products = complex_query_4()
        return Response({
            "count": products.count(),
            "description": "Топ-бренды (>2020 или гарантия >12 мес), малый остаток на складе",
            "results": self.get_serializer(products, many=True).data,
        })


class OrderViewSet(viewsets.ModelViewSet):
    """API для управления заказами с разграничением доступа по ролям."""

    queryset = Order.objects.select_related("product", "product__category", "user").all()
    serializer_class = OrderSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = OrderFilter
    search_fields = ["customer_name", "customer_email", "customer_phone"]
    ordering_fields = ["order_date", "total_price"]

    def get_permissions(self):
        """
        Распределение прав:
        - list/retrieve: аутентифицированные (покупатели видят только свои заказы);
        - create: аутентифицированные;
        - update/destroy: менеджер/администратор;
        - cancel: аутентифицированные (с проверкой владельца).
        """
        if self.action in ("list", "retrieve", "my_orders", "create", "cancel"):
            return [IsAuthenticated()]
        if self.action in ("update", "partial_update", "destroy", "change_status", "recent", "pending", "complex_filter_2"):
            return [IsManagerOrAdmin()]
        return [IsAuthenticated()]

    def get_queryset(self):
        """
        Покупатели видят только свои заказы; менеджеры/администраторы — все.
        """
        queryset = super().get_queryset()
        user = self.request.user
        if not user.is_authenticated:
            return queryset.none()
        try:
            role = user.profile.role
        except AttributeError:
            role = UserProfile.BUYER
        if role in ("admin", "manager"):
            return queryset
        return queryset.filter(user=user)

    @action(methods=["GET"], detail=False)
    def recent(self, request):
        """Заказы за последние 7 дней."""
        seven_days_ago = date.today() - timedelta(days=7)
        orders = self.get_queryset().filter(order_date__gte=seven_days_ago).order_by("-order_date")
        page = self.paginate_queryset(orders)
        if page is not None:
            return self.get_paginated_response(self.get_serializer(page, many=True).data)
        return Response(self.get_serializer(orders, many=True).data)

    @action(methods=["GET"], detail=False)
    def pending(self, request):
        """Заказы в статусе «ожидает обработки»."""
        orders = self.get_queryset().filter(status="pending")
        return Response(self.get_serializer(orders, many=True).data)

    @action(methods=["POST"], detail=True)
    def change_status(self, request, pk=None):
        """
        Изменить статус заказа (менеджер/администратор).

        Args:
            request: HTTP-запрос с полем status
            pk: Первичный ключ заказа
        """
        order = self.get_object()
        new_status = request.data.get("status")
        valid_statuses = ["pending", "processing", "shipped", "delivered", "cancelled"]
        if new_status not in valid_statuses:
            return Response(
                {"error": f'Статус должен быть одним из: {", ".join(valid_statuses)}'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        old_status = order.status
        order.status = new_status
        if new_status == "delivered" and not order.delivery_date:
            order.delivery_date = date.today()
        if new_status == "cancelled" and old_status != "cancelled":
            product = order.product
            product.stock_quantity += order.quantity
            product.is_available = True
            product.save()
        order.save()
        from .tasks import send_order_status_email
        send_order_status_email.delay(order.id, new_status)
        return Response({
            "status": "success",
            "message": f'Статус изменён с "{old_status}" на "{new_status}"',
            "order": self.get_serializer(order).data,
        })

    @action(methods=["POST"], detail=True)
    def cancel(self, request, pk=None):
        """
        Отменить заказ.

        Args:
            request: HTTP-запрос
            pk: Первичный ключ заказа

        BL: покупатель может отменить только свой заказ в статусе «pending».
        Менеджер/администратор — любой заказ, кроме доставленного.
        """
        order = self.get_object()
        try:
            role = request.user.profile.role
        except AttributeError:
            role = UserProfile.BUYER

        if role == "buyer" and order.user != request.user:
            return Response({"error": "Нельзя отменить чужой заказ"}, status=status.HTTP_403_FORBIDDEN)
        if role == "buyer" and order.status != "pending":
            return Response({"error": "Покупатель может отменить только заказ в статусе «ожидает обработки»"}, status=status.HTTP_400_BAD_REQUEST)
        if order.status in ("delivered", "cancelled"):
            return Response({"error": f'Нельзя отменить заказ в статусе "{order.status}"'}, status=status.HTTP_400_BAD_REQUEST)

        order.status = "cancelled"
        order.save()
        product = order.product
        product.stock_quantity += order.quantity
        product.is_available = True
        product.save()
        return Response({"status": "success", "message": "Заказ отменён, товар возвращён на склад"})

    def list_by_customer(self, request, customer_name=None):
        """
        Заказы по имени покупателя (URL-параметр).

        Args:
            request: HTTP-запрос
            customer_name: Имя покупателя
        """
        orders = self.get_queryset().filter(customer_name__icontains=customer_name)
        return Response({"customer_name": customer_name, "count": orders.count(), "results": self.get_serializer(orders, many=True).data})

    @action(methods=["GET"], detail=False)
    def my_orders(self, request):
        """Заказы текущего аутентифицированного пользователя."""
        orders = Order.objects.filter(user=request.user).select_related("product", "product__category")
        return Response({"user": request.user.username, "count": orders.count(), "results": self.get_serializer(orders, many=True).data})

    @action(methods=["GET"], detail=False)
    def complex_filter_2(self, request):
        """Сложный запрос 2: крупные заказы техники (отправлены/доставлены)."""
        orders = complex_query_2()
        return Response({
            "count": orders.count(),
            "description": "Крупные заказы техники (отправлены/доставлены)",
            "results": self.get_serializer(orders, many=True).data,
        })


class SupplierViewSet(viewsets.ModelViewSet):
    """API для управления поставщиками (доступно только менеджерам/администраторам)."""

    queryset = Supplier.objects.prefetch_related("products").annotate(
        products_count=Count("products", distinct=True),
    )
    serializer_class = SupplierSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = SupplierFilter
    search_fields = ["name", "contact_person", "country"]
    ordering_fields = ["rating", "name", "created_at"]

    def get_permissions(self):
        """
        Создание/удаление — администраторам; остальное — менеджерам/администраторам.
        """
        if self.action in ("create", "destroy", "update_rating"):
            return [IsAdminRole()]
        return [IsManagerOrAdmin()]

    @action(methods=["GET"], detail=False)
    def top_rated(self, request):
        """Поставщики с рейтингом ≥ 4.5."""
        suppliers = self.get_queryset().filter(rating__gte=4.5, is_active=True).order_by("-rating")
        return Response({"count": suppliers.count(), "results": self.get_serializer(suppliers, many=True).data})

    @action(methods=["POST"], detail=True)
    def add_products(self, request, pk=None):
        """
        Добавить товары к поставщику.

        Args:
            request: HTTP-запрос с полем product_ids (список ID)
            pk: Первичный ключ поставщика
        """
        supplier = self.get_object()
        product_ids = request.data.get("product_ids", [])
        if not product_ids:
            return Response({"error": "Укажите product_ids"}, status=status.HTTP_400_BAD_REQUEST)
        products = Product.objects.filter(id__in=product_ids)
        supplier.products.add(*products)
        return Response({"status": "success", "message": f"Добавлено {products.count()} товаров", "products_count": supplier.products.count()})

    @action(methods=["POST"], detail=True)
    def update_rating(self, request, pk=None):
        """
        Обновить рейтинг поставщика (только администратор).

        Args:
            request: HTTP-запрос с полем rating (0–5)
            pk: Первичный ключ поставщика
        """
        supplier = self.get_object()
        new_rating = request.data.get("rating")
        if new_rating is None:
            return Response({"error": "Укажите rating"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            new_rating = float(new_rating)
            if new_rating < 0 or new_rating > 5:
                raise ValueError
        except (ValueError, TypeError):
            return Response({"error": "Рейтинг должен быть числом от 0 до 5"}, status=status.HTTP_400_BAD_REQUEST)
        supplier.rating = new_rating
        supplier.save()
        return Response({"status": "success", "rating": supplier.rating})

    @action(methods=["GET"], detail=False)
    def complex_filter_5(self, request):
        """Сложный запрос 5: топ-поставщики Apple/Samsung с рейтингом > 4.0."""
        suppliers = complex_query_5()
        return Response({
            "count": suppliers.count(),
            "description": "Топ-поставщики Apple/Samsung с большим ассортиментом",
            "results": self.get_serializer(suppliers, many=True).data,
        })


class ReviewViewSet(viewsets.ModelViewSet):
    """API для работы с отзывами; покупатели видят только одобренные."""

    queryset = Review.objects.select_related("product", "product__category").all()
    serializer_class = ReviewSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = ReviewFilter
    search_fields = ["customer_name", "comment"]
    ordering_fields = ["rating", "created_at"]

    def get_permissions(self):
        """
        Чтение/создание — всем аутентифицированным;
        модерация и удаление — менеджерам/администраторам.
        """
        if self.action in ("list", "retrieve", "high_rated", "complex_filter_6"):
            return [AllowAny()]
        if self.action == "create":
            return [IsAuthenticated()]
        if self.action in ("approve", "verify_purchase", "pending_approval"):
            return [IsManagerOrAdmin()]
        if self.action in ("update", "partial_update", "destroy"):
            return [IsManagerOrAdmin()]
        return [IsAuthenticated()]

    def get_queryset(self):
        """
        Анонимы и покупатели видят только одобренные отзывы;
        менеджеры/администраторы — все.
        """
        queryset = super().get_queryset()
        user = self.request.user
        if user.is_authenticated:
            try:
                role = user.profile.role
                if role in ("admin", "manager"):
                    return queryset
            except AttributeError:
                pass
        return queryset.filter(is_approved=True)

    @action(methods=["GET"], detail=False)
    def high_rated(self, request):
        """Одобренные отзывы с оценкой 4–5 звёзд."""
        reviews = self.get_queryset().filter(rating__gte=4).order_by("-rating", "-created_at")
        page = self.paginate_queryset(reviews)
        if page is not None:
            return self.get_paginated_response(self.get_serializer(page, many=True).data)
        return Response(self.get_serializer(reviews, many=True).data)

    @action(methods=["GET"], detail=False)
    def pending_approval(self, request):
        """Отзывы, ожидающие модерации (менеджер/администратор)."""
        reviews = Review.objects.filter(is_approved=False).select_related("product").order_by("created_at")
        return Response({"count": reviews.count(), "results": self.get_serializer(reviews, many=True).data})

    @action(methods=["POST"], detail=True)
    def approve(self, request, pk=None):
        """
        Одобрить отзыв (менеджер/администратор).

        Args:
            request: HTTP-запрос
            pk: Первичный ключ отзыва
        """
        review = self.get_object()
        review.is_approved = True
        review.save()
        return Response({"status": "success", "message": "Отзыв одобрен", "is_approved": review.is_approved})

    @action(methods=["POST"], detail=True)
    def verify_purchase(self, request, pk=None):
        """
        Пометить отзыв как подтверждённую покупку (менеджер/администратор).

        Args:
            request: HTTP-запрос
            pk: Первичный ключ отзыва
        """
        review = self.get_object()
        review.is_verified_purchase = True
        review.save()
        return Response({"status": "success", "message": "Покупка подтверждена", "is_verified_purchase": review.is_verified_purchase})

    @action(methods=["GET"], detail=False)
    def complex_filter_6(self, request):
        """Сложный запрос 6: качественные свежие отзывы на технику."""
        reviews = complex_query_6()
        return Response({
            "count": reviews.count(),
            "description": "Качественные свежие отзывы на технику",
            "results": self.get_serializer(reviews, many=True).data,
        })


# ---------------------------------------------------------------------------
# Cart & Favorites API
# ---------------------------------------------------------------------------

class CartViewSet(viewsets.ViewSet):
    """API корзины текущего пользователя: позиции, изменение, оформление заказа."""

    permission_classes = [IsAuthenticated]

    def _get_cart(self, user) -> Cart:
        """Возвращает (создавая при необходимости) корзину пользователя."""
        cart, _ = Cart.objects.get_or_create(user=user)
        return cart

    def list(self, request):
        """Содержимое корзины текущего пользователя (GET /api/cart/)."""
        cart = self._get_cart(request.user)
        return Response(CartSerializer(cart, context={"request": request}).data)

    @action(methods=["POST"], detail=False)
    def add_item(self, request):
        """
        Добавить товар в корзину или увеличить его количество.

        Args:
            request: HTTP-запрос с полями product (id) и quantity (по умолчанию 1)

        BL: проверяется наличие запрошенного количества на складе.
        """
        cart = self._get_cart(request.user)
        product = get_object_or_404(Product, pk=request.data.get("product"))
        try:
            quantity = int(request.data.get("quantity", 1))
        except (TypeError, ValueError):
            return Response({"error": "Некорректное количество"}, status=status.HTTP_400_BAD_REQUEST)
        if quantity <= 0:
            return Response({"error": "Количество должно быть больше нуля"}, status=status.HTTP_400_BAD_REQUEST)

        item, created = CartItem.objects.get_or_create(cart=cart, product=product)
        new_quantity = quantity if created else item.quantity + quantity
        if new_quantity > product.stock_quantity:
            if created:
                item.delete()
            return Response(
                {"error": f"Недостаточно товара на складе. Доступно: {product.stock_quantity}"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        item.quantity = new_quantity
        item.save()
        return Response(CartSerializer(cart, context={"request": request}).data, status=status.HTTP_200_OK)

    @action(methods=["POST"], detail=False)
    def update_item(self, request):
        """
        Установить точное количество товара в корзине.

        Args:
            request: HTTP-запрос с полями product (id) и quantity
        """
        cart = self._get_cart(request.user)
        item = get_object_or_404(CartItem, cart=cart, product_id=request.data.get("product"))
        try:
            quantity = int(request.data.get("quantity"))
        except (TypeError, ValueError):
            return Response({"error": "Некорректное количество"}, status=status.HTTP_400_BAD_REQUEST)
        if quantity <= 0:
            item.delete()
            return Response(CartSerializer(cart, context={"request": request}).data)
        if quantity > item.product.stock_quantity:
            return Response(
                {"error": f"Недостаточно товара на складе. Доступно: {item.product.stock_quantity}"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        item.quantity = quantity
        item.save()
        return Response(CartSerializer(cart, context={"request": request}).data)

    @action(methods=["POST"], detail=False)
    def remove_item(self, request):
        """
        Удалить товар из корзины.

        Args:
            request: HTTP-запрос с полем product (id)
        """
        cart = self._get_cart(request.user)
        CartItem.objects.filter(cart=cart, product_id=request.data.get("product")).delete()
        return Response(CartSerializer(cart, context={"request": request}).data)

    @action(methods=["POST"], detail=False)
    def clear(self, request):
        """Полностью очистить корзину."""
        cart = self._get_cart(request.user)
        cart.items.all().delete()
        return Response(CartSerializer(cart, context={"request": request}).data)

    @action(methods=["POST"], detail=False)
    def checkout(self, request):
        """
        Оформить заказ из корзины.

        Args:
            request: HTTP-запрос с полями customer_name, customer_email,
                customer_phone, delivery_address

        BL: корзина не пуста, адрес валиден, сумма в пределах 500–100 000 ₽,
        каждого товара достаточно на складе. На каждую позицию создаётся
        отдельный заказ; склад списывается, корзина очищается.
        """
        cart = self._get_cart(request.user)
        items = list(cart.items.select_related("product"))
        if not items:
            return Response({"error": "Корзина пуста"}, status=status.HTTP_400_BAD_REQUEST)

        # Валидация адреса доставки
        try:
            address = validate_delivery_address(request.data.get("delivery_address", ""))
        except serializers.ValidationError as exc:
            return Response({"delivery_address": exc.detail}, status=status.HTTP_400_BAD_REQUEST)

        # Валидация наличия на складе и суммы заказа
        total = cart.total_price
        try:
            validate_order_amount(total)
        except serializers.ValidationError as exc:
            return Response({"amount": exc.detail}, status=status.HTTP_400_BAD_REQUEST)
        for item in items:
            if item.quantity > item.product.stock_quantity:
                return Response(
                    {"error": f"«{item.product.name}»: на складе только {item.product.stock_quantity} шт."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        customer_name = request.data.get("customer_name", "").strip()
        customer_email = request.data.get("customer_email", "").strip()
        customer_phone = request.data.get("customer_phone", "").strip()
        if not (customer_name and customer_email and customer_phone):
            return Response(
                {"error": "Укажите имя, email и телефон покупателя"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        created_orders = []
        for item in items:
            order = Order.objects.create(
                user=request.user,
                product=item.product,
                customer_name=customer_name,
                customer_email=customer_email,
                customer_phone=customer_phone,
                quantity=item.quantity,
                total_price=item.subtotal,
                delivery_address=address,
            )
            product = item.product
            product.stock_quantity -= item.quantity
            if product.stock_quantity <= 0:
                product.is_available = False
            product.save()
            created_orders.append(order)

        cart.items.all().delete()
        send_order_confirmation(customer_name, customer_email, created_orders, total)
        return Response(
            {
                "status": "success",
                "message": f"Оформлено заказов: {len(created_orders)} на сумму {total} ₽",
                "order_ids": [o.id for o in created_orders],
            },
            status=status.HTTP_201_CREATED,
        )


class FavoriteViewSet(viewsets.ModelViewSet):
    """API избранного: список, добавление, удаление, переключение."""

    serializer_class = FavoriteSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """Только избранное текущего пользователя."""
        return Favorite.objects.filter(user=self.request.user).select_related(
            "product", "product__category"
        )

    def perform_create(self, serializer) -> None:
        """Привязывает запись избранного к текущему пользователю."""
        serializer.save(user=self.request.user)

    @action(methods=["POST"], detail=False)
    def toggle(self, request):
        """
        Переключить товар в избранном.

        Args:
            request: HTTP-запрос с полем product (id)

        Если товара нет в избранном — добавляет, иначе удаляет.
        """
        product = get_object_or_404(Product, pk=request.data.get("product"))
        favorite = Favorite.objects.filter(user=request.user, product=product).first()
        if favorite:
            favorite.delete()
            return Response({"status": "removed", "is_favorite": False, "product": product.id})
        Favorite.objects.create(user=request.user, product=product)
        return Response(
            {"status": "added", "is_favorite": True, "product": product.id},
            status=status.HTTP_201_CREATED,
        )


# ---------------------------------------------------------------------------
# Traditional web views
# ---------------------------------------------------------------------------

def product_list(request):
    """Главная страница с каталогом товаров и фильтрацией."""
    products = Product.objects.select_related("category").filter(is_available=True)

    category_id = request.GET.get("category")
    if category_id:
        products = products.filter(category_id=category_id)

    search = request.GET.get("search")
    if search:
        products = products.filter(
            Q(name__icontains=search) | Q(brand__icontains=search) | Q(description__icontains=search)
        )

    if request.GET.get("on_sale") == "true":
        products = products.filter(discount_price__isnull=False)

    sort_by = request.GET.get("sort", "-created_at")
    products = products.order_by(sort_by)

    categories = Category.objects.filter(is_active=True)

    favorite_ids = []
    if request.user.is_authenticated:
        favorite_ids = list(
            Favorite.objects.filter(user=request.user).values_list("product_id", flat=True)
        )

    return render(request, "shop/product_list.html", {
        "products": products,
        "categories": categories,
        "current_category": category_id,
        "search_query": search or "",
        "on_sale": request.GET.get("on_sale"),
        "favorite_ids": favorite_ids,
    })


def product_detail(request, pk):
    """Страница конкретного товара с отзывами и похожими товарами."""
    product = get_object_or_404(Product.objects.select_related("category"), pk=pk)
    reviews = product.reviews.filter(is_approved=True).order_by("-created_at")[:10]
    suppliers = product.suppliers.all()
    similar_products = Product.objects.filter(
        category=product.category, is_available=True
    ).exclude(pk=product.pk)[:4]

    is_favorite = False
    if request.user.is_authenticated:
        is_favorite = Favorite.objects.filter(
            user=request.user, product=product
        ).exists()

    return render(request, "shop/product_detail.html", {
        "product": product,
        "reviews": reviews,
        "suppliers": suppliers,
        "similar_products": similar_products,
        "is_favorite": is_favorite,
    })


def add_review(request, product_id):
    """Добавление отзыва на товар через веб-форму."""
    if request.method == "POST":
        product = get_object_or_404(Product, pk=product_id)
        Review.objects.create(
            product=product,
            customer_name=request.POST.get("customer_name"),
            customer_email=request.POST.get("customer_email"),
            rating=int(request.POST.get("rating")),
            comment=request.POST.get("comment"),
            advantages=request.POST.get("advantages", ""),
            disadvantages=request.POST.get("disadvantages", ""),
        )
        return redirect("product_detail", pk=product_id)
    return redirect("product_list")


def product_create(request):
    """Создание товара через веб-форму."""
    if request.method == "POST":
        form = ProductCreateForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect("product_list")
    else:
        form = ProductCreateForm()
    return render(request, "shop/product_create.html", {"form": form})


def web_login_view(request):
    """Страница входа в аккаунт."""
    if request.user.is_authenticated:
        return redirect("product_list")
    error = None
    if request.method == "POST":
        user = authenticate(
            request,
            username=request.POST.get("username"),
            password=request.POST.get("password"),
        )
        if user:
            login(request, user)
            return redirect(request.GET.get("next", "product_list"))
        error = "Неверный логин или пароль"
    return render(request, "shop/login.html", {"error": error})


def web_register_view(request):
    """Страница регистрации нового пользователя."""
    if request.user.is_authenticated:
        return redirect("product_list")
    error = None
    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        email = request.POST.get("email", "").strip()
        password = request.POST.get("password", "")
        password2 = request.POST.get("password2", "")
        if password != password2:
            error = "Пароли не совпадают"
        elif len(password) < 8:
            error = "Пароль должен содержать минимум 8 символов"
        elif User.objects.filter(username=username).exists():
            error = "Пользователь с таким именем уже существует"
        else:
            user = User.objects.create_user(username=username, email=email, password=password)
            login(request, user)
            return redirect("product_list")
    return render(request, "shop/register.html", {"error": error})


def web_logout_view(request):
    """Выход из аккаунта."""
    logout(request)
    return redirect("product_list")


# ---------------------------------------------------------------------------
# Cart & Favorites web views
# ---------------------------------------------------------------------------

def cart_view(request):
    """Страница корзины текущего пользователя."""
    if not request.user.is_authenticated:
        return redirect(f"/login/?next={request.path}")
    cart, _ = Cart.objects.get_or_create(user=request.user)
    items = cart.items.select_related("product", "product__category")
    return render(request, "shop/cart.html", {"cart": cart, "items": items})


def cart_add(request, product_id):
    """Добавить товар в корзину (веб-форма)."""
    from django.contrib import messages

    if not request.user.is_authenticated:
        return redirect(f"/login/?next=/product/{product_id}/")
    if request.method != "POST":
        return redirect("product_detail", pk=product_id)

    product = get_object_or_404(Product, pk=product_id)
    cart, _ = Cart.objects.get_or_create(user=request.user)
    try:
        quantity = max(1, int(request.POST.get("quantity", 1)))
    except (TypeError, ValueError):
        quantity = 1

    item, created = CartItem.objects.get_or_create(cart=cart, product=product)
    new_quantity = quantity if created else item.quantity + quantity
    if new_quantity > product.stock_quantity:
        if created:
            item.delete()
        messages.error(request, f"Недостаточно на складе. Доступно: {product.stock_quantity} шт.")
    else:
        item.quantity = new_quantity
        item.save()
        messages.success(request, f"«{product.name}» добавлен в корзину")
    next_url = request.POST.get("next")
    return redirect(next_url) if next_url else redirect("cart")


def cart_update(request):
    """Изменить количество товара в корзине (веб-форма)."""
    if not request.user.is_authenticated:
        return redirect("login")
    if request.method == "POST":
        cart, _ = Cart.objects.get_or_create(user=request.user)
        item = CartItem.objects.filter(
            cart=cart, product_id=request.POST.get("product_id")
        ).first()
        if item:
            try:
                quantity = int(request.POST.get("quantity", item.quantity))
            except (TypeError, ValueError):
                quantity = item.quantity
            if quantity <= 0:
                item.delete()
            elif quantity <= item.product.stock_quantity:
                item.quantity = quantity
                item.save()
    return redirect("cart")


def cart_remove(request, product_id):
    """Удалить товар из корзины (веб-форма)."""
    if not request.user.is_authenticated:
        return redirect("login")
    if request.method == "POST":
        cart, _ = Cart.objects.get_or_create(user=request.user)
        CartItem.objects.filter(cart=cart, product_id=product_id).delete()
    return redirect("cart")


def cart_checkout(request):
    """Оформление заказа из корзины (веб-форма)."""
    from django.contrib import messages

    if not request.user.is_authenticated:
        return redirect("login")
    cart, _ = Cart.objects.get_or_create(user=request.user)
    items = list(cart.items.select_related("product"))

    if request.method != "POST":
        return render(request, "shop/checkout.html", {"cart": cart, "items": items})

    if not items:
        messages.error(request, "Корзина пуста")
        return redirect("cart")

    # Валидация адреса
    try:
        address = validate_delivery_address(request.POST.get("delivery_address", ""))
    except serializers.ValidationError as exc:
        messages.error(request, "; ".join(str(e) for e in exc.detail))
        return render(request, "shop/checkout.html", {"cart": cart, "items": items})

    # Валидация суммы заказа
    total = cart.total_price
    try:
        validate_order_amount(total)
    except serializers.ValidationError as exc:
        messages.error(request, "; ".join(str(e) for e in exc.detail))
        return render(request, "shop/checkout.html", {"cart": cart, "items": items})

    # Валидация наличия на складе
    for item in items:
        if item.quantity > item.product.stock_quantity:
            messages.error(request, f"«{item.product.name}»: на складе только {item.product.stock_quantity} шт.")
            return redirect("cart")

    customer_name = request.POST.get("customer_name", "").strip()
    customer_email = request.POST.get("customer_email", "").strip()
    customer_phone = request.POST.get("customer_phone", "").strip()
    if not (customer_name and customer_email and customer_phone):
        messages.error(request, "Заполните имя, email и телефон")
        return render(request, "shop/checkout.html", {"cart": cart, "items": items})

    created_orders = []
    for item in items:
        order = Order.objects.create(
            user=request.user, product=item.product,
            customer_name=customer_name, customer_email=customer_email,
            customer_phone=customer_phone, quantity=item.quantity,
            total_price=item.subtotal, delivery_address=address,
        )
        product = item.product
        product.stock_quantity -= item.quantity
        if product.stock_quantity <= 0:
            product.is_available = False
        product.save()
        created_orders.append(order)

    cart.items.all().delete()
    send_order_confirmation(customer_name, customer_email, created_orders, total)
    messages.success(request, f"Заказ оформлен! Создано заказов: {len(created_orders)} на сумму {total} ₽")
    return redirect("product_list")


def favorites_view(request):
    """Страница «Избранное» текущего пользователя."""
    if not request.user.is_authenticated:
        return redirect(f"/login/?next={request.path}")
    favorites = Favorite.objects.filter(user=request.user).select_related(
        "product", "product__category"
    )
    products = [f.product for f in favorites]
    return render(request, "shop/favorites.html", {"products": products})


def favorite_toggle(request, product_id):
    """Переключить товар в избранном (веб-форма)."""
    if not request.user.is_authenticated:
        return redirect(f"/login/?next=/product/{product_id}/")
    if request.method == "POST":
        product = get_object_or_404(Product, pk=product_id)
        favorite = Favorite.objects.filter(user=request.user, product=product).first()
        if favorite:
            favorite.delete()
        else:
            Favorite.objects.create(user=request.user, product=product)
    return redirect(request.POST.get("next", "product_list"))
