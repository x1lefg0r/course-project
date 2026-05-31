from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from simple_history.admin import SimpleHistoryAdmin
from import_export.admin import ImportExportModelAdmin
from import_export import resources, fields
from import_export.widgets import ForeignKeyWidget
from .models import Category, Product, Order, Supplier, Review, UserProfile


class CategoryResource(resources.ModelResource):
    """Ресурс для экспорта категорий"""

    products_count = fields.Field()

    class Meta:
        model = Category
        fields = (
            "id",
            "name",
            "description",
            "is_active",
            "created_at",
            "products_count",
        )
        export_order = (
            "id",
            "name",
            "description",
            "is_active",
            "created_at",
            "products_count",
        )

    def get_export_queryset(self, queryset):
        """Экспортируем только активные категории"""
        return queryset.filter(is_active=True).order_by("name")

    def dehydrate_products_count(self, category):
        """Добавляем количество товаров в категории"""
        return category.products.count()

    def get_export_headers(self):
        """Кастомные заголовки для экспорта"""
        headers = super().get_export_headers()
        custom_headers = {
            "id": "ID категории",
            "name": "Название",
            "description": "Описание",
            "is_active": "Активна",
            "created_at": "Дата создания",
            "products_count": "Количество товаров",
        }
        return [custom_headers.get(h, h) for h in headers]


class ProductResource(resources.ModelResource):
    """Ресурс для экспорта товаров"""

    category = fields.Field(
        column_name="category",
        attribute="category",
        widget=ForeignKeyWidget(Category, "name"),
    )
    discount_percentage = fields.Field()
    final_price = fields.Field()
    status = fields.Field()

    class Meta:
        model = Product
        fields = (
            "id",
            "name",
            "category",
            "brand",
            "model",
            "price",
            "discount_price",
            "discount_percentage",
            "final_price",
            "condition",
            "stock_quantity",
            "warranty_months",
            "release_year",
            "is_available",
            "status",
        )
        export_order = fields

    def get_export_queryset(self, queryset):
        """Экспортируем только доступные товары с остатком на складе"""
        return queryset.filter(is_available=True, stock_quantity__gt=0).select_related(
            "category"
        )

    def dehydrate_discount_percentage(self, product):
        """Вычисляем процент скидки"""
        if product.discount_price:
            discount = ((product.price - product.discount_price) / product.price) * 100
            return f"{round(discount, 2)}%"
        return "0%"

    def dehydrate_final_price(self, product):
        """Возвращаем финальную цену (с учётом скидки)"""
        return product.discount_price if product.discount_price else product.price

    def dehydrate_status(self, product):
        """Определяем статус товара"""
        if product.stock_quantity == 0:
            return "Нет в наличии"
        elif product.stock_quantity < 5:
            return "Заканчивается"
        else:
            return "В наличии"


class OrderResource(resources.ModelResource):
    """Ресурс для экспорта заказов"""

    product = fields.Field(
        column_name="product",
        attribute="product",
        widget=ForeignKeyWidget(Product, "name"),
    )
    product_brand = fields.Field()
    days_since_order = fields.Field()

    class Meta:
        model = Order
        fields = (
            "id",
            "product",
            "product_brand",
            "customer_name",
            "customer_email",
            "customer_phone",
            "quantity",
            "total_price",
            "status",
            "order_date",
            "days_since_order",
        )

    def get_export_queryset(self, queryset):
        """Экспортируем заказы за последний месяц"""
        from datetime import timedelta, date

        last_month = date.today() - timedelta(days=30)
        return queryset.filter(order_date__gte=last_month).select_related("product")

    def dehydrate_product_brand(self, order):
        """Добавляем бренд товара"""
        return order.product.brand

    def dehydrate_days_since_order(self, order):
        """Вычисляем количество дней с момента заказа"""
        from datetime import date

        delta = date.today() - order.order_date.date()
        return delta.days


@admin.register(Category)
class CategoryAdmin(SimpleHistoryAdmin, ImportExportModelAdmin):
    """Админка для категорий"""

    resource_class = CategoryResource

    list_display = [
        "id",
        "name",
        "is_active",
        "products_count_display",
        "created_at_display",
    ]

    list_filter = ["is_active", "created_at"]

    search_fields = ["name", "description"]

    fieldsets = (
        ("Основная информация", {"fields": ("name", "description")}),
        ("Статус", {"fields": ("is_active",)}),
    )

    readonly_fields = ["created_at"]

    list_display_links = ["id", "name"]

    @admin.display(description="Количество товаров", ordering="products__count")
    def products_count_display(self, obj):
        """Показываем количество товаров с ссылкой"""
        count = obj.products.count()
        url = (
            reverse("admin:shop_product_changelist") + f"?category__id__exact={obj.id}"
        )
        return format_html('<a href="{}">{} товаров</a>', url, count)

    @admin.display(description="Дата создания", ordering="created_at")
    def created_at_display(self, obj):
        """Форматируем дату"""
        return obj.created_at.strftime("%d.%m.%Y %H:%M")


class ProductInline(admin.TabularInline):
    """Отображение товаров внутри категории"""

    model = Product
    extra = 0
    fields = ["name", "brand", "price", "stock_quantity", "is_available"]
    readonly_fields = ["name", "brand"]
    can_delete = False
    show_change_link = True


CategoryAdmin.inlines = [ProductInline]


@admin.register(Product)
class ProductAdmin(SimpleHistoryAdmin, ImportExportModelAdmin):
    """Админка для товаров"""

    resource_class = ProductResource

    list_display = [
        "id",
        "name",
        "category_link",
        "brand",
        "price_display",
        "stock_status",
        "is_available",
        "created_at_short",
    ]

    list_filter = ["category", "brand", "condition", "is_available", "release_year"]

    search_fields = ["name", "brand", "model", "description"]

    fieldsets = (
        (
            "Основная информация",
            {"fields": ("name", "category", "brand", "model", "description")},
        ),
        (
            "Цены",
            {
                "fields": ("price", "discount_price"),
                "classes": ("collapse",),
            },
        ),
        (
            "Характеристики",
            {"fields": ("condition", "release_year", "warranty_months")},
        ),
        (
            "Склад",
            {
                "fields": ("stock_quantity", "is_available"),
                "classes": ("wide",),
            },
        ),
    )

    readonly_fields = ["created_at", "updated_at"]

    list_display_links = ["id", "name"]
    list_editable = ["is_available"]
    list_per_page = 20
    date_hierarchy = "created_at"

    @admin.display(description="Категория", ordering="category__name")
    def category_link(self, obj):
        """Ссылка на категорию"""
        url = reverse("admin:shop_category_change", args=[obj.category.id])
        return format_html('<a href="{}">{}</a>', url, obj.category.name)

    @admin.display(description="Цена", ordering="price")
    def price_display(self, obj):
        """Показываем цену с учётом скидки"""
        if obj.discount_price:
            discount_percent = ((obj.price - obj.discount_price) / obj.price) * 100
            return format_html(
                '<span style="text-decoration: line-through;">{}</span> '
                '<span style="color: red; font-weight: bold;">{}</span> '
                '<span style="color: green;">(-{}%)</span>',
                f"{obj.price}₽",
                f"{obj.discount_price}₽",
                round(discount_percent),
            )
        return f"{obj.price}₽"

    @admin.display(description="Статус склада", ordering="stock_quantity")
    def stock_status(self, obj):
        """Цветной индикатор остатка"""
        if obj.stock_quantity == 0:
            color = "red"
            text = "Нет в наличии"
        elif obj.stock_quantity < 5:
            color = "orange"
            text = f"Осталось {obj.stock_quantity} шт."
        else:
            color = "green"
            text = f"{obj.stock_quantity} шт."
        return format_html('<span style="color: {};">{}</span>', color, text)

    @admin.display(description="Добавлен", ordering="created_at")
    def created_at_short(self, obj):
        """Короткая дата"""
        return obj.created_at.strftime("%d.%m.%Y")


class OrderInline(admin.TabularInline):
    """Отображение заказов внутри товара"""

    model = Order
    extra = 0
    fields = ["customer_name", "quantity", "status", "order_date"]
    readonly_fields = ["customer_name", "quantity", "order_date"]
    can_delete = False
    show_change_link = True


@admin.register(Order)
class OrderAdmin(SimpleHistoryAdmin, ImportExportModelAdmin):
    """Админка для заказов"""

    resource_class = OrderResource

    list_display = [
        "id",
        "product_link",
        "customer_name",
        "quantity",
        "total_price_display",
        "status",
        "order_date_display",
    ]

    list_filter = ["status", "order_date", "product__category"]

    search_fields = [
        "customer_name",
        "customer_email",
        "customer_phone",
        "product__name",
    ]

    fieldsets = (
        ("Информация о товаре", {"fields": ("product", "quantity", "total_price")}),
        (
            "Информация о покупателе",
            {
                "fields": (
                    "customer_name",
                    "customer_email",
                    "customer_phone",
                    "delivery_address",
                )
            },
        ),
        ("Статус заказа", {"fields": ("status", "delivery_date", "notes")}),
    )

    readonly_fields = ["order_date"]

    list_display_links = ["id"]
    list_editable = ["status"]
    date_hierarchy = "order_date"
    list_per_page = 25

    @admin.display(description="Товар", ordering="product__name")
    def product_link(self, obj):
        """Ссылка на товар"""
        url = reverse("admin:shop_product_change", args=[obj.product.id])
        return format_html('<a href="{}">{}</a>', url, obj.product.name)

    @admin.display(description="Сумма", ordering="total_price")
    def total_price_display(self, obj):
        """Форматированная сумма"""
        return format_html("<strong>{} ₽</strong>", f"{obj.total_price:,.2f}")

    @admin.display(description="Статус", ordering="status")
    def status_display(self, obj):
        """Цветной статус"""
        colors = {
            "pending": "orange",
            "processing": "blue",
            "shipped": "purple",
            "delivered": "green",
            "cancelled": "red",
        }
        color = colors.get(obj.status, "black")
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color,
            obj.get_status_display(),
        )

    @admin.display(description="Дата заказа", ordering="order_date")
    def order_date_display(self, obj):
        """Форматированная дата"""
        return obj.order_date.strftime("%d.%m.%Y %H:%M")


class SupplierResource(resources.ModelResource):
    """Ресурс для экспорта поставщиков"""

    products_count = fields.Field()
    top_products = fields.Field()

    class Meta:
        model = Supplier
        fields = (
            "id",
            "name",
            "contact_person",
            "contact_email",
            "country",
            "rating",
            "is_active",
            "products_count",
            "top_products",
        )

    def get_export_queryset(self, queryset):
        """Экспортируем только активных поставщиков"""
        return queryset.filter(is_active=True).order_by("-rating")

    def dehydrate_products_count(self, supplier):
        """Количество товаров"""
        return supplier.products.count()

    def dehydrate_top_products(self, supplier):
        """ТОП-3 товара"""
        products = supplier.products.all()[:3]
        return ", ".join([p.name for p in products])


class ReviewResource(resources.ModelResource):
    """Ресурс для экспорта отзывов"""

    product = fields.Field(
        column_name="product",
        attribute="product",
        widget=ForeignKeyWidget(Product, "name"),
    )
    rating_stars = fields.Field()
    status = fields.Field()

    class Meta:
        model = Review
        fields = (
            "id",
            "product",
            "customer_name",
            "rating",
            "rating_stars",
            "comment",
            "is_approved",
            "is_verified_purchase",
            "status",
            "created_at",
        )

    def get_export_queryset(self, queryset):
        """Экспортируем только одобренные отзывы"""
        return queryset.filter(is_approved=True).order_by("-created_at")

    def dehydrate_rating_stars(self, review):
        """Визуализация рейтинга звёздами"""
        return "⭐" * review.rating

    def dehydrate_status(self, review):
        """Статус отзыва"""
        if review.is_verified_purchase:
            return "Подтверждённая покупка"
        elif review.is_approved:
            return "Одобрен"
        else:
            return "На модерации"


@admin.register(Supplier)
class SupplierAdmin(SimpleHistoryAdmin, ImportExportModelAdmin):
    """Админка для поставщиков"""

    resource_class = SupplierResource

    list_display = [
        "id",
        "name",
        "country",
        "rating_display",
        "products_count_display",
        "is_active",
        "created_at_short",
    ]

    list_filter = ["country", "is_active", "rating"]
    search_fields = ["name", "contact_person", "country"]

    fieldsets = (
        ("Основная информация", {"fields": ("name", "country", "is_active", "rating")}),
        (
            "Контакты",
            {"fields": ("contact_person", "contact_email", "contact_phone", "address")},
        ),
        ("Товары", {"fields": ("products",), "classes": ("collapse",)}),
    )

    filter_horizontal = ["products"]
    list_display_links = ["id", "name"]
    list_per_page = 20

    @admin.display(description="Рейтинг", ordering="rating")
    def rating_display(self, obj):
        """Цветной рейтинг"""
        if obj.rating >= 4.5:
            color = "green"
        elif obj.rating >= 3.5:
            color = "orange"
        else:
            color = "red"
        return format_html(
            '<span style="color: {}; font-weight: bold;">{} ⭐</span>',
            color,
            obj.rating,
        )

    @admin.display(description="Товары", ordering="products__count")
    def products_count_display(self, obj):
        """Количество товаров с ссылкой"""
        count = obj.products.count()
        if count > 0:
            url = (
                reverse("admin:shop_product_changelist")
                + f"?suppliers__id__exact={obj.id}"
            )
            return format_html('<a href="{}">{} товаров</a>', url, count)
        return "0 товаров"

    @admin.display(description="Добавлен", ordering="created_at")
    def created_at_short(self, obj):
        return obj.created_at.strftime("%d.%m.%Y")


@admin.register(Review)
class ReviewAdmin(SimpleHistoryAdmin, ImportExportModelAdmin):
    """Админка для отзывов"""

    resource_class = ReviewResource

    list_display = [
        "id",
        "product_link",
        "customer_name",
        "rating_display",
        "is_approved",
        "is_verified_purchase",
        "created_at_short",
    ]

    list_filter = ["rating", "is_approved", "is_verified_purchase", "created_at"]
    search_fields = ["customer_name", "customer_email", "comment"]

    fieldsets = (
        (
            "Товар и покупатель",
            {"fields": ("product", "customer_name", "customer_email")},
        ),
        (
            "Оценка и комментарий",
            {"fields": ("rating", "comment", "advantages", "disadvantages")},
        ),
        (
            "Модерация",
            {"fields": ("is_approved", "is_verified_purchase"), "classes": ("wide",)},
        ),
    )

    readonly_fields = ["created_at", "updated_at"]
    list_display_links = ["id"]
    list_editable = ["is_approved"]
    date_hierarchy = "created_at"

    @admin.display(description="Товар", ordering="product__name")
    def product_link(self, obj):
        """Ссылка на товар"""
        url = reverse("admin:shop_product_change", args=[obj.product.id])
        return format_html('<a href="{}">{}</a>', url, obj.product.name)

    @admin.display(description="Оценка", ordering="rating")
    def rating_display(self, obj):
        """Визуализация рейтинга"""
        stars = "⭐" * obj.rating
        colors = {1: "red", 2: "orange", 3: "gray", 4: "blue", 5: "green"}
        color = colors.get(obj.rating, "black")
        return format_html(
            '<span style="color: {}; font-size: 16px;">{}</span>', color, stars
        )

    @admin.display(description="Дата", ordering="created_at")
    def created_at_short(self, obj):
        return obj.created_at.strftime("%d.%m.%Y")


class ReviewInline(admin.TabularInline):
    """Отображение отзывов внутри товара"""

    model = Review
    extra = 0
    fields = ["customer_name", "rating", "is_approved", "created_at"]
    readonly_fields = ["customer_name", "rating", "created_at"]
    can_delete = False
    show_change_link = True


ProductAdmin.inlines = [OrderInline, ReviewInline]


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    """Админка для профилей пользователей с ролями."""

    list_display = ["id", "user", "role_display", "phone", "created_at_short"]
    list_filter = ["role"]
    search_fields = ["user__username", "user__email", "phone"]
    readonly_fields = ["created_at"]

    fieldsets = (
        ("Пользователь", {"fields": ("user", "role")}),
        ("Контакты", {"fields": ("phone", "address")}),
    )

    @admin.display(description="Роль", ordering="role")
    def role_display(self, obj):
        colors = {"admin": "red", "manager": "blue", "buyer": "green"}
        color = colors.get(obj.role, "black")
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>', color, obj.get_role_display()
        )

    @admin.display(description="Дата регистрации", ordering="created_at")
    def created_at_short(self, obj):
        return obj.created_at.strftime("%d.%m.%Y")
