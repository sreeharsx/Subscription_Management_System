from django.db import models
from django.contrib.auth.models import User
from decimal import Decimal
from accounts.models import CustomerProfile
from products.models import SubscriptionPlan, TaxConfiguration, DiscountConfiguration


class Quotation(models.Model):
    STATUS_CHOICES = [
        ('DRAFT', 'Draft'),
        ('SENT', 'Sent'),
        ('ACCEPTED', 'Accepted'),
        ('REJECTED', 'Rejected'),
    ]

    customer = models.ForeignKey(CustomerProfile, on_delete=models.PROTECT, related_name='quotations')
    plan = models.ForeignKey(SubscriptionPlan, on_delete=models.PROTECT, related_name='quotations')
    tax = models.ForeignKey(TaxConfiguration, on_delete=models.SET_NULL, null=True, blank=True)
    discount = models.ForeignKey(DiscountConfiguration, on_delete=models.SET_NULL, null=True, blank=True)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='DRAFT')

    # Snapshot pricing at quotation time
    base_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    tax_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    valid_until = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_quotations')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"QT-{self.pk:04d} — {self.customer} ({self.status})"

    def can_accept(self):
        return self.status == 'SENT'

    def can_reject(self):
        return self.status in ('DRAFT', 'SENT')

    def can_send(self):
        return self.status == 'DRAFT'

    def calculate_totals(self):
        """Recalculate and set pricing fields."""
        base = self.plan.base_price
        self.base_price = base

        discount_amt = Decimal('0.00')
        if self.discount:
            discount_amt = self.discount.calculate_discount(base)
        self.discount_amount = discount_amt

        taxable = base - discount_amt
        tax_amt = Decimal('0.00')
        if self.tax:
            tax_amt = (taxable * self.tax.rate / Decimal('100')).quantize(Decimal('0.01'))
        self.tax_amount = tax_amt
        self.total_amount = taxable + tax_amt

    def save(self, *args, **kwargs):
        if self.base_price is None or self.total_amount is None:
            self.calculate_totals()
        super().save(*args, **kwargs)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Quotation"
        verbose_name_plural = "Quotations"
