from django import forms
from decimal import Decimal
from .models import Payment


class PaymentForm(forms.Form):
    amount = forms.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal('0.01'))
    payment_method = forms.ChoiceField(choices=Payment.METHOD_CHOICES)
    payment_date = forms.DateField(widget=forms.DateInput(attrs={'type': 'date'}))
    reference_number = forms.CharField(max_length=100, required=False)
    notes = forms.CharField(widget=forms.Textarea(attrs={'rows': 2}), required=False)


class RunBillingForm(forms.Form):
    billing_date = forms.DateField(
        widget=forms.DateInput(attrs={'type': 'date'}),
        label="Billing Date",
        help_text="Generate invoices for all active subscriptions due on or before this date."
    )
