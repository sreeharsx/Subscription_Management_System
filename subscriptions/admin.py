from django.contrib import admin
from .models import Subscription


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ['__str__', 'customer', 'plan', 'status', 'start_date', 'next_billing_date']
    list_filter = ['status', 'billing_cycle']
    search_fields = ['customer__user__username', 'customer__company_name']
