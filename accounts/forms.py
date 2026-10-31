from django import forms
from django.contrib.auth.models import User
from .models import CustomerProfile

_fc = {'class': 'form-control'}


class CustomerUserForm(forms.ModelForm):
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={**_fc, 'placeholder': 'Set a strong password'}),
        label="Password",
    )
    confirm_password = forms.CharField(
        widget=forms.PasswordInput(attrs={**_fc, 'placeholder': 'Repeat password'}),
        label="Confirm Password",
    )

    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name', 'email']
        widgets = {
            'username': forms.TextInput(attrs={**_fc, 'placeholder': 'Unique login name'}),
            'first_name': forms.TextInput(attrs={**_fc, 'placeholder': 'First name'}),
            'last_name': forms.TextInput(attrs={**_fc, 'placeholder': 'Last name'}),
            'email': forms.EmailInput(attrs={**_fc, 'placeholder': 'user@example.com'}),
        }

    def clean(self):
        cleaned = super().clean()
        p1 = cleaned.get('password')
        p2 = cleaned.get('confirm_password')
        if p1 and p2 and p1 != p2:
            raise forms.ValidationError("Passwords do not match.")
        return cleaned


class CustomerProfileForm(forms.ModelForm):
    class Meta:
        model = CustomerProfile
        fields = ['company_name', 'phone', 'address', 'gst_number']
        widgets = {
            'company_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Company Ltd.'}),
            'phone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '+91 98765 43210'}),
            'address': forms.Textarea(attrs={'class': 'form-control', 'rows': '3', 'placeholder': 'Full address...'}),
            'gst_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '22AAAAA0000A1Z5'}),
        }
