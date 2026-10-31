from django import forms
from .models import Quotation


class QuotationForm(forms.ModelForm):
    class Meta:
        model = Quotation
        fields = ['customer', 'plan', 'tax', 'discount', 'valid_until', 'notes']
        widgets = {
            'valid_until': forms.DateInput(attrs={'type': 'date'}),
            'notes': forms.Textarea(attrs={'rows': 3}),
        }
