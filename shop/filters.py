import django_filters
from .models import Product, Order, Review, Supplier


class ProductFilter(django_filters.FilterSet):
    """Фильтры для товаров по цене, категории, производителю и другим критериям."""

    min_price = django_filters.NumberFilter(field_name="price", lookup_expr="gte", label="Цена от")
    max_price = django_filters.NumberFilter(field_name="price", lookup_expr="lte", label="Цена до")
    year_from = django_filters.NumberFilter(field_name="release_year", lookup_expr="gte", label="Год от")
    year_to = django_filters.NumberFilter(field_name="release_year", lookup_expr="lte", label="Год до")
    on_sale = django_filters.BooleanFilter(method="filter_on_sale", label="Со скидкой")
    brand = django_filters.CharFilter(lookup_expr="iexact", label="Бренд")
    min_warranty = django_filters.NumberFilter(field_name="warranty_months", lookup_expr="gte", label="Гарантия от (мес.)")

    def filter_on_sale(self, queryset, name, value):
        """Фильтр: товары со скидкой или без."""
        if value:
            return queryset.filter(discount_price__isnull=False)
        return queryset.filter(discount_price__isnull=True)

    class Meta:
        model = Product
        fields = ["category", "brand", "condition", "is_available"]


class OrderFilter(django_filters.FilterSet):
    """Фильтры для заказов."""

    date_from = django_filters.DateTimeFilter(field_name="order_date", lookup_expr="gte", label="Дата от")
    date_to = django_filters.DateTimeFilter(field_name="order_date", lookup_expr="lte", label="Дата до")
    min_total = django_filters.NumberFilter(field_name="total_price", lookup_expr="gte", label="Сумма от")
    max_total = django_filters.NumberFilter(field_name="total_price", lookup_expr="lte", label="Сумма до")

    class Meta:
        model = Order
        fields = ["status", "product"]


class ReviewFilter(django_filters.FilterSet):
    """Фильтры для отзывов."""

    min_rating = django_filters.NumberFilter(field_name="rating", lookup_expr="gte", label="Оценка от")
    max_rating = django_filters.NumberFilter(field_name="rating", lookup_expr="lte", label="Оценка до")

    class Meta:
        model = Review
        fields = ["product", "rating", "is_approved", "is_verified_purchase"]


class SupplierFilter(django_filters.FilterSet):
    """Фильтры для поставщиков."""

    min_rating = django_filters.NumberFilter(field_name="rating", lookup_expr="gte", label="Рейтинг от")

    class Meta:
        model = Supplier
        fields = ["country", "is_active"]
