from django import forms
from .models import Quotation

_fc = {'class': 'form-control'}
_fcs = {'class': 'form-select'}


class QuotationForm(forms.ModelForm):
    class Meta:
        model = Quotation
        fields = ['customer', 'plan', 'tax', 'discount', 'valid_until', 'notes']
        widgets = {
            'customer': forms.Select(attrs=_fcs),
            'plan': forms.Select(attrs=_fcs),
            'tax': forms.Select(attrs=_fcs),
            'discount': forms.Select(attrs=_fcs),
            'valid_until': forms.DateInput(attrs={**_fc, 'type': 'date'}),
            'notes': forms.Textarea(attrs={**_fc, 'rows': '3', 'placeholder': 'Optional notes for the customer...'}),
        }
