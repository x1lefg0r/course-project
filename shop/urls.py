from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    CategoryViewSet,
    ProductViewSet,
    OrderViewSet,
    SupplierViewSet,
    ReviewViewSet,
    product_list,
    product_detail,
    add_review,
    product_create,
    web_login_view,
    web_register_view,
    web_logout_view,
)


router = DefaultRouter()
router.register(r"categories", CategoryViewSet, basename="category")
router.register(r"products", ProductViewSet, basename="product")
router.register(r"orders", OrderViewSet, basename="order")
router.register(r"suppliers", SupplierViewSet, basename="supplier")
router.register(r"reviews", ReviewViewSet, basename="review")

urlpatterns = [
    # Веб-страницы
    path("", product_list, name="product_list"),
    path("product/<int:pk>/", product_detail, name="product_detail"),
    path("product/<int:product_id>/add-review/", add_review, name="add_review"),
    # API
    path("api/", include(router.urls)),
    # Фильтр по именованным аргументам в URL
    path(
        "api/products/by-category/<int:category_id>/",
        ProductViewSet.as_view({"get": "list_by_category"}),
        name="products-by-category",
    ),
    path(
        "api/products/by-brand/<str:brand_name>/",
        ProductViewSet.as_view({"get": "list_by_brand"}),
        name="products-by-brand",
    ),
    path(
        "api/orders/by-customer/<str:customer_name>/",
        OrderViewSet.as_view({"get": "list_by_customer"}),
        name="orders-by-customer",
    ),
    path("product/add/", product_create, name="product_add"),
    # Авторизация (веб)
    path("login/", web_login_view, name="login"),
    path("register/", web_register_view, name="register"),
    path("logout/", web_logout_view, name="logout"),
]
