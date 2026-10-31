from datetime import date
from django import forms
from django.db.models import Q
from .models import Quotation
from products.models import SubscriptionPlan, TaxConfiguration, DiscountConfiguration


class QuotationForm(forms.ModelForm):
    class Meta:
        model = Quotation
        fields = ['customer', 'plan', 'tax', 'discount', 'valid_until', 'notes']
        widgets = {
            'customer': forms.Select(attrs={'class': 'form-select'}),
            'plan': forms.Select(attrs={'class': 'form-select'}),
            'tax': forms.Select(attrs={'class': 'form-select'}),
            'discount': forms.Select(attrs={'class': 'form-select'}),
            'valid_until': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'notes': forms.Textarea(attrs={'rows': 3, 'class': 'form-control', 'placeholder': 'Optional notes or commercial terms...'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Inactive catalogue item rule:
        # 1. New quotations: display only active plans, taxes and discounts.
        # 2. Editing existing quotation: display active items PLUS the currently selected items
        #    (retains catalogue items even if they subsequently became inactive, without silent replacement).
        if self.instance and self.instance.pk:
            plan_filter = Q(is_active=True)
            if self.instance.plan_id:
                plan_filter |= Q(pk=self.instance.plan_id)
            self.fields['plan'].queryset = SubscriptionPlan.objects.filter(plan_filter).select_related('product')

            tax_filter = Q(is_active=True)
            if self.instance.tax_id:
                tax_filter |= Q(pk=self.instance.tax_id)
            self.fields['tax'].queryset = TaxConfiguration.objects.filter(tax_filter)

            discount_filter = Q(is_active=True)
            if self.instance.discount_id:
                discount_filter |= Q(pk=self.instance.discount_id)
            self.fields['discount'].queryset = DiscountConfiguration.objects.filter(discount_filter)
        else:
            self.fields['plan'].queryset = SubscriptionPlan.objects.filter(is_active=True).select_related('product')
            self.fields['tax'].queryset = TaxConfiguration.objects.filter(is_active=True)
            self.fields['discount'].queryset = DiscountConfiguration.objects.filter(is_active=True)

        self.fields['customer'].queryset = self.fields['customer'].queryset.select_related('user')

    def clean_valid_until(self):
        valid_until = self.cleaned_data.get('valid_until')
        if valid_until and valid_until < date.today():
            raise forms.ValidationError("Validity date cannot be in the past.")
        return valid_until
