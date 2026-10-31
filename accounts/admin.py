from django.contrib import admin
from .models import CustomerProfile, AuditLog


@admin.register(CustomerProfile)
class CustomerProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'company_name', 'phone', 'gst_number', 'created_at']
    search_fields = ['user__username', 'user__first_name', 'company_name']


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ['timestamp', 'actor', 'action', 'model_name', 'object_repr']
    list_filter = ['action', 'model_name', 'timestamp']
    search_fields = ['actor__username', 'object_repr', 'details']
    readonly_fields = ['timestamp', 'actor', 'action', 'model_name', 'object_id', 'object_repr', 'details']

