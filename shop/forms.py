from django import forms
from .models import Product


class ProductCreateForm(forms.ModelForm):
    """Форма создания товара через веб-интерфейс."""

    class Meta:
        model = Product
        fields = [
            "name",
            "category",
            "brand",
            "model",
            "description",
            "price",
            "discount_price",
            "condition",
            "stock_quantity",
            "warranty_months",
            "release_year",
            "is_available",
        ]

        widgets = {
            "description": forms.Textarea(attrs={"rows": 4}),
        }
