from django.db import models
from django.core.exceptions import ValidationError
from decimal import Decimal
from accounts.models import CustomerProfile
from products.models import SubscriptionPlan
from quotations.models import Quotation


class Subscription(models.Model):
    STATUS_CHOICES = [
        ('ACTIVE', 'Active'),
        ('PAUSED', 'Paused'),
        ('CANCELLED', 'Cancelled'),
        ('EXPIRED', 'Expired'),
    ]

    VALID_TRANSITIONS = {
        'ACTIVE': ['PAUSED', 'CANCELLED', 'EXPIRED'],
        'PAUSED': ['ACTIVE', 'CANCELLED'],
        'CANCELLED': [],
        'EXPIRED': [],
    }

    quotation = models.OneToOneField(
        Quotation, on_delete=models.PROTECT, related_name='subscription',
        help_text="Source quotation — enforces one subscription per quotation"
    )
    customer = models.ForeignKey(CustomerProfile, on_delete=models.PROTECT, related_name='subscriptions')
    plan = models.ForeignKey(SubscriptionPlan, on_delete=models.PROTECT, related_name='subscriptions')

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='ACTIVE')

    # Pricing snapshots from quotation
    billing_cycle = models.CharField(max_length=20)
    plan_price = models.DecimalField(max_digits=10, decimal_places=2)
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'))

    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    next_billing_date = models.DateField()

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"SUB-{self.pk:04d} — {self.customer} ({self.status})"

    def can_transition_to(self, new_status):
        return new_status in self.VALID_TRANSITIONS.get(self.status, [])

    @property
    def can_renew(self):
        """Only EXPIRED subscriptions can be renewed."""
        return self.status == 'EXPIRED'

    def clean(self):
        """Validate date relationships without breaking nullable fields or existing records."""
        super().clean()
        if self.start_date:
            if self.end_date and self.end_date < self.start_date:
                raise ValidationError({'end_date': "End date cannot be earlier than start date."})
            if self.next_billing_date and self.next_billing_date < self.start_date:
                raise ValidationError({'next_billing_date': "Next billing date cannot be earlier than start date."})

    def get_invoiceable_amount(self):
        """Return (base, discount, tax, total) using Decimal arithmetic."""
        base = self.plan_price
        discount = self.discount_amount
        taxable = base - discount
        tax = (taxable * self.tax_rate / Decimal('100')).quantize(Decimal('0.01'))
        total = taxable + tax
        return base, discount, tax, total

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Subscription"
        verbose_name_plural = "Subscriptions"
