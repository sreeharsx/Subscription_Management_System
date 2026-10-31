from django import forms
from .models import Product,ProductVariant, SubscriptionPlan, TaxConfiguration, DiscountConfiguration


class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = [
            'name',
            'product_type',
            'sales_price',
            'cost_price',
            'description',
            'is_active'
        ]
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
        }
class ProductVariantForm(forms.ModelForm):
    class Meta:
        model = ProductVariant
        fields = ['name', 'additional_price', 'description', 'is_active']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
        }

class SubscriptionPlanForm(forms.ModelForm):
    class Meta:
        model = SubscriptionPlan
        fields = [
            'product',
            'name',
            'description',
            'billing_cycle',
            'base_price',
            'minimum_quantity',
            'start_date',
            'end_date',
            'auto_close',
            'is_active'
        ]

        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
            'start_date': forms.DateInput(attrs={'type': 'date'}),
            'end_date': forms.DateInput(attrs={'type': 'date'}),
        }


class TaxConfigurationForm(forms.ModelForm):
    class Meta:
        model = TaxConfiguration
        fields = [
            'name',
            'rate',
            'tax_scope',
            'product',
            'valid_from',
            'valid_until',
            'is_active'
        ]

        widgets = {
            'valid_from': forms.DateInput(attrs={'type': 'date'}),
            'valid_until': forms.DateInput(attrs={'type': 'date'}),
        }

class DiscountConfigurationForm(forms.ModelForm):
    class Meta:
        model = DiscountConfiguration
        fields = ['name', 'code', 'discount_type', 'value', 'valid_from', 'valid_until', 'is_active']
        widgets = {
            'valid_from': forms.DateInput(attrs={'type': 'date'}),
            'valid_until': forms.DateInput(attrs={'type': 'date'}),
        }
