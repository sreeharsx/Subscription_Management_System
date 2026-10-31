from django import forms
from .models import Product, SubscriptionPlan, TaxConfiguration, DiscountConfiguration


class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = ['name', 'description', 'is_active']
        widgets = {'description': forms.Textarea(attrs={'rows': 3})}


class SubscriptionPlanForm(forms.ModelForm):
    class Meta:
        model = SubscriptionPlan
        fields = ['product', 'name', 'description', 'billing_cycle', 'base_price', 'is_active']
        widgets = {'description': forms.Textarea(attrs={'rows': 3})}


class TaxConfigurationForm(forms.ModelForm):
    class Meta:
        model = TaxConfiguration
        fields = ['name', 'rate', 'is_active']


class DiscountConfigurationForm(forms.ModelForm):
    class Meta:
        model = DiscountConfiguration
        fields = ['name', 'code', 'discount_type', 'value', 'valid_from', 'valid_until', 'is_active']
        widgets = {
            'valid_from': forms.DateInput(attrs={'type': 'date'}),
            'valid_until': forms.DateInput(attrs={'type': 'date'}),
        }
