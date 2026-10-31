from django.db import models
from django.contrib.auth.models import User
from decimal import Decimal
from subscriptions.models import Subscription


class Invoice(models.Model):
    STATUS_CHOICES = [
        ('DRAFT', 'Draft'),
        ('ISSUED', 'Issued'),
        ('PAID', 'Paid'),
        ('PARTIALLY_PAID', 'Partially Paid'),
        ('OVERDUE', 'Overdue'),
        ('VOID', 'Void'),
    ]

    subscription = models.ForeignKey(Subscription, on_delete=models.PROTECT, related_name='invoices')
    invoice_number = models.CharField(max_length=50, unique=True)
    # billing_period_key e.g. "2026-10" prevents duplicate invoices for same period
    billing_period_key = models.CharField(max_length=20)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='ISSUED')

    base_amount = models.DecimalField(max_digits=10, decimal_places=2)
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    tax_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    amount_paid = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))

    issue_date = models.DateField()
    due_date = models.DateField()
    paid_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def outstanding_balance(self):
        return self.total_amount - self.amount_paid

    def update_payment_status(self):
        """Recalculate and save payment status based on amount_paid."""
        from django.utils import timezone
        if self.amount_paid >= self.total_amount:
            self.status = 'PAID'
            if not self.paid_date:
                self.paid_date = timezone.now().date()
        elif self.amount_paid > Decimal('0.00'):
            self.status = 'PARTIALLY_PAID'
        else:
            from datetime import date
            if self.due_date < date.today() and self.status not in ('VOID',):
                self.status = 'OVERDUE'
            elif self.status not in ('VOID',):
                self.status = 'ISSUED'

    def __str__(self):
        return f"{self.invoice_number} — {self.subscription.customer}"

    class Meta:
        ordering = ['-issue_date']
        verbose_name = "Invoice"
        verbose_name_plural = "Invoices"
        # MANDATORY: prevent duplicate invoices for same subscription+period
        unique_together = [('subscription', 'billing_period_key')]
        indexes = [
            models.Index(fields=['subscription', 'billing_period_key']),
            models.Index(fields=['status']),
            models.Index(fields=['due_date']),
        ]


class Payment(models.Model):
    METHOD_CHOICES = [
        ('BANK_TRANSFER', 'Bank Transfer'),
        ('CASH', 'Cash'),
        ('CHEQUE', 'Cheque'),
        ('ONLINE', 'Online'),
        ('UPI', 'UPI'),
    ]

    STATUS_CHOICES = [
        ('COMPLETED', 'Completed'),
        ('FAILED', 'Failed'),
        ('REFUNDED', 'Refunded'),
    ]

    invoice = models.ForeignKey(Invoice, on_delete=models.PROTECT, related_name='payments')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_date = models.DateField()
    payment_method = models.CharField(max_length=20, choices=METHOD_CHOICES)
    reference_number = models.CharField(max_length=100, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='COMPLETED')
    recorded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='recorded_payments')
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Payment ₹{self.amount} for {self.invoice.invoice_number}"

    class Meta:
        ordering = ['-payment_date']
        verbose_name = "Payment"
        verbose_name_plural = "Payments"
