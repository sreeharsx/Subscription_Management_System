from django import forms
from .models import Product, ProductVariant, SubscriptionPlan, TaxConfiguration, DiscountConfiguration

_fc = {'class': 'form-control'}
_fcs = {'class': 'form-select'}


class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = ['name', 'product_type', 'sales_price', 'cost_price', 'description', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={**_fc, 'placeholder': 'e.g. BrightLoop Pro'}),
            'product_type': forms.Select(attrs=_fcs),
            'sales_price': forms.NumberInput(attrs={**_fc, 'step': '0.01', 'placeholder': '0.00'}),
            'cost_price': forms.NumberInput(attrs={**_fc, 'step': '0.01', 'placeholder': '0.00'}),
            'description': forms.Textarea(attrs={**_fc, 'rows': '3', 'placeholder': 'Brief description...'}),
        }


class ProductVariantForm(forms.ModelForm):
    class Meta:
        model = ProductVariant
        fields = ['name', 'additional_price', 'description', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={**_fc, 'placeholder': 'e.g. Enterprise Add-on'}),
            'additional_price': forms.NumberInput(attrs={**_fc, 'step': '0.01', 'placeholder': '0.00'}),
            'description': forms.Textarea(attrs={**_fc, 'rows': '3', 'placeholder': 'Variant details...'}),
        }


class SubscriptionPlanForm(forms.ModelForm):
    class Meta:
        model = SubscriptionPlan
        fields = ['product', 'name', 'description', 'billing_cycle', 'base_price', 'is_active']
        widgets = {
            'product': forms.Select(attrs=_fcs),
            'name': forms.TextInput(attrs={**_fc, 'placeholder': 'e.g. Starter Monthly'}),
            'description': forms.Textarea(attrs={**_fc, 'rows': '3'}),
            'billing_cycle': forms.Select(attrs=_fcs),
            'base_price': forms.NumberInput(attrs={**_fc, 'step': '0.01', 'placeholder': '0.00'}),
        }


class TaxConfigurationForm(forms.ModelForm):
    class Meta:
        model = TaxConfiguration
        fields = ['name', 'rate', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={**_fc, 'placeholder': 'e.g. GST 18%'}),
            'rate': forms.NumberInput(attrs={**_fc, 'step': '0.01', 'placeholder': '18.00'}),
        }


class DiscountConfigurationForm(forms.ModelForm):
    class Meta:
        model = DiscountConfiguration
        fields = ['name', 'code', 'discount_type', 'value', 'valid_from', 'valid_until', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={**_fc, 'placeholder': 'e.g. Summer Sale 20%'}),
            'code': forms.TextInput(attrs={**_fc, 'placeholder': 'SUMMER20'}),
            'discount_type': forms.Select(attrs=_fcs),
            'value': forms.NumberInput(attrs={**_fc, 'step': '0.01', 'placeholder': '20.00'}),
            'valid_from': forms.DateInput(attrs={**_fc, 'type': 'date'}),
            'valid_until': forms.DateInput(attrs={**_fc, 'type': 'date'}),
        }
