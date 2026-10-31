from django import forms
from django.contrib.auth.models import User
from .models import CustomerProfile


class CustomerUserForm(forms.ModelForm):
    password = forms.CharField(widget=forms.PasswordInput, label="Password")
    confirm_password = forms.CharField(widget=forms.PasswordInput, label="Confirm Password")

    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name', 'email']

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
            'address': forms.Textarea(attrs={'rows': 3}),
        }
