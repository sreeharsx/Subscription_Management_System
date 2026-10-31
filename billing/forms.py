from django import forms
from decimal import Decimal
from .models import Payment

_fc = {'class': 'form-control'}
_fcs = {'class': 'form-select'}


class PaymentForm(forms.Form):
    amount = forms.DecimalField(
        max_digits=10, decimal_places=2, min_value=Decimal('0.01'),
        widget=forms.NumberInput(attrs={**_fc, 'step': '0.01', 'placeholder': '0.00'}),
    )
    payment_method = forms.ChoiceField(
        choices=Payment.METHOD_CHOICES,
        widget=forms.Select(attrs=_fcs),
    )
    payment_date = forms.DateField(
        widget=forms.DateInput(attrs={**_fc, 'type': 'date'}),
    )
    reference_number = forms.CharField(
        max_length=100, required=False,
        widget=forms.TextInput(attrs={**_fc, 'placeholder': 'Ref / transaction ID (optional)'}),
    )
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={**_fc, 'rows': '3', 'placeholder': 'Optional notes...'}),
    )


class RunBillingForm(forms.Form):
    billing_date = forms.DateField(
        widget=forms.DateInput(attrs={**_fc, 'type': 'date'}),
        label="Billing Date",
        help_text="Generate invoices for all active subscriptions due on or before this date.",
    )
