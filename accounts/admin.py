from django.contrib import admin
from .models import CustomerProfile


@admin.register(CustomerProfile)
class CustomerProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'company_name', 'phone', 'gst_number', 'created_at']
    search_fields = ['user__username', 'user__first_name', 'company_name']
