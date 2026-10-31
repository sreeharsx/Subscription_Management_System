from django.contrib import admin
from .models import Quotation


@admin.register(Quotation)
class QuotationAdmin(admin.ModelAdmin):
    list_display = ['__str__', 'customer', 'plan', 'status', 'total_amount', 'created_at']
    list_filter = ['status']
    search_fields = ['customer__user__username', 'customer__company_name']
