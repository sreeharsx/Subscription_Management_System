from django.contrib import admin
from .models import Product, ProductVariant, SubscriptionPlan, TaxConfiguration, DiscountConfiguration


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ['name', 'is_active', 'created_at']
    list_filter = ['is_active']
    search_fields = ['name']

@admin.register(ProductVariant)
class ProductVariantAdmin(admin.ModelAdmin):
    list_display = ['name', 'product', 'additional_price', 'is_active']
    list_filter = ['is_active', 'product']
    search_fields = ['name', 'product__name']
    
@admin.register(SubscriptionPlan)
class SubscriptionPlanAdmin(admin.ModelAdmin):
    list_display = ['name', 'product', 'billing_cycle', 'base_price', 'is_active']
    list_filter = ['billing_cycle', 'is_active', 'product']


@admin.register(TaxConfiguration)
class TaxConfigurationAdmin(admin.ModelAdmin):
    list_display = ['name', 'rate', 'is_active']


@admin.register(DiscountConfiguration)
class DiscountConfigurationAdmin(admin.ModelAdmin):
    list_display = ['name', 'code', 'discount_type', 'value', 'is_active', 'valid_until']
