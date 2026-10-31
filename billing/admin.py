from django.contrib import admin
from .models import Invoice, Payment


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ['invoice_number', 'subscription', 'status', 'total_amount', 'amount_paid', 'due_date']
    list_filter = ['status']
    search_fields = ['invoice_number', 'subscription__customer__user__username']
    readonly_fields = ['invoice_number', 'billing_period_key']


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ['__str__', 'invoice', 'amount', 'payment_date', 'payment_method', 'status']
    list_filter = ['status', 'payment_method']
