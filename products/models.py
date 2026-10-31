from django.db import models
from decimal import Decimal
from django.core.validators import MinValueValidator


class Product(models.Model):
    name = models.CharField(max_length=200)

    product_type = models.CharField(
        max_length=100,
        blank=True
    )

    sales_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))]
    )

    cost_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))]
    )

    description = models.TextField(
        blank=True,
        verbose_name="Notes"
    )

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

    class Meta:
        ordering = ['name']

class ProductVariant(models.Model):
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='variants'
    )

    name = models.CharField(max_length=200)

    additional_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))]
    )

    description = models.TextField(blank=True)

    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.product.name} - {self.name}"

    class Meta:
        ordering = ['product', 'name']
class SubscriptionPlan(models.Model):
    BILLING_CYCLE_CHOICES = [
        ('DAILY', 'Daily'),
        ('WEEKLY', 'Weekly'),
        ('MONTHLY', 'Monthly'),
        ('YEARLY', 'Yearly'),
    ]

    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT,
        related_name='plans'
    )
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)

    billing_cycle = models.CharField(
        max_length=20,
        choices=BILLING_CYCLE_CHOICES,
        default='MONTHLY'
    )

    base_price = models.DecimalField(max_digits=10, decimal_places=2)

    minimum_quantity = models.PositiveIntegerField(default=1)

    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)

    auto_close = models.BooleanField(default=False)

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.product.name} — {self.name} ({self.get_billing_cycle_display()})"

    def get_cycle_months(self):
        return {
            'MONTHLY': 1,
            'YEARLY': 12
        }.get(self.billing_cycle, 0)

    class Meta:
        ordering = ['product', 'name']


class TaxConfiguration(models.Model):
    name = models.CharField(max_length=100)
    rate = models.DecimalField(max_digits=5, decimal_places=2, help_text="Percentage, e.g. 18.00 for 18%")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} ({self.rate}%)"

    class Meta:
        ordering = ['name']
        verbose_name = "Tax Configuration"
        verbose_name_plural = "Tax Configurations"


class DiscountConfiguration(models.Model):
    DISCOUNT_TYPE_CHOICES = [
        ('PERCENTAGE', 'Percentage'),
        ('FIXED', 'Fixed Amount'),
    ]

    name = models.CharField(max_length=200)
    code = models.CharField(max_length=50, unique=True)
    discount_type = models.CharField(max_length=20, choices=DISCOUNT_TYPE_CHOICES)
    value = models.DecimalField(max_digits=10, decimal_places=2, help_text="Percentage or fixed amount")
    valid_from = models.DateField(null=True, blank=True)
    valid_until = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        if self.discount_type == 'PERCENTAGE':
            return f"{self.name} ({self.value}%)"
        return f"{self.name} (₹{self.value})"

    def calculate_discount(self, base_price: Decimal) -> Decimal:
        """Return discount amount for a given base price."""
        if self.discount_type == 'PERCENTAGE':
            return (base_price * self.value / Decimal('100')).quantize(Decimal('0.01'))
        return min(self.value, base_price)

    class Meta:
        ordering = ['name']
        verbose_name = "Discount Configuration"
        verbose_name_plural = "Discount Configurations"
