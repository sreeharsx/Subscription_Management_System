"""
Billing engine — idempotent invoice generation.
All monetary calculations use Decimal.
"""
from datetime import date
from decimal import Decimal
from django.db import transaction, IntegrityError
from django.db.models import F
from django.utils import timezone
from subscriptions.models import Subscription
from accounts.services import log_activity
from .models import Invoice, Payment


def get_billing_period_key(billing_date: date) -> str:
    """Return a string key for the billing period. e.g. '2026-10'"""
    return billing_date.strftime('%Y-%m')


def generate_invoice_number(subscription_id: int, period_key: str) -> str:
    """Generate a deterministic, human-readable invoice number."""
    return f"INV-{subscription_id:05d}-{period_key}"


def generate_invoice_for_subscription(subscription: Subscription, billing_date: date = None) -> tuple:
    """
    Generate an invoice for a subscription for the current billing period.
    Returns (invoice, created) — created=False means it already existed.

    IDEMPOTENCY: protected by UNIQUE(subscription, billing_period_key) and
    transaction + get_or_create pattern. Running this twice is safe.
    """
    if billing_date is None:
        billing_date = date.today()

    if subscription.status != 'ACTIVE':
        raise ValueError(f"Cannot generate invoice for {subscription.status} subscription.")

    period_key = get_billing_period_key(billing_date)
    invoice_number = generate_invoice_number(subscription.pk, period_key)

    base, discount, tax, total = subscription.get_invoiceable_amount()

    # Due in 15 days
    from dateutil.relativedelta import relativedelta
    due_date = billing_date + relativedelta(days=15)

    try:
        with transaction.atomic():
            invoice, created = Invoice.objects.get_or_create(
                subscription=subscription,
                billing_period_key=period_key,
                defaults={
                    'invoice_number': invoice_number,
                    'status': 'ISSUED',
                    'base_amount': base,
                    'discount_amount': discount,
                    'tax_amount': tax,
                    'total_amount': total,
                    'amount_paid': Decimal('0.00'),
                    'issue_date': billing_date,
                    'due_date': due_date,
                }
            )
            return invoice, created
    except IntegrityError:
        # Race condition: another process created it — retrieve it
        invoice = Invoice.objects.get(subscription=subscription, billing_period_key=period_key)
        return invoice, False


def record_payment(invoice: Invoice, amount: Decimal, payment_method: str,
                   payment_date: date, recorded_by, reference_number: str = '', notes: str = '') -> Payment:
    """
    Record a payment against an invoice.
    Validates that payment does not exceed outstanding balance.
    """
    if invoice.status == 'VOID':
        raise ValueError("Cannot record payment against a void invoice.")

    outstanding = invoice.outstanding_balance
    if amount <= Decimal('0.00'):
        raise ValueError("Payment amount must be positive.")
    if amount > outstanding:
        raise ValueError(f"Payment amount ₹{amount} exceeds outstanding balance ₹{outstanding}.")

    with transaction.atomic():
        payment = Payment.objects.create(
            invoice=invoice,
            amount=amount,
            payment_date=payment_date,
            payment_method=payment_method,
            reference_number=reference_number,
            status='COMPLETED',
            recorded_by=recorded_by,
            notes=notes,
        )
        # Update invoice
        invoice.amount_paid = invoice.amount_paid + amount
        invoice.update_payment_status()
        invoice.save()
        log_activity(recorded_by, 'PAYMENT_RECORDED', payment, f"Payment of ₹{amount} recorded for {invoice.invoice_number}")

    return payment


def update_overdue_invoices(as_of_date: date = None, dry_run: bool = False) -> dict:
    """
    Mark past-due invoices with outstanding balances as OVERDUE.
    Excludes PAID and VOID invoices.
    Avoids duplicate processing for invoices already marked OVERDUE.

    Returns a summary dict with counts and per-invoice details.
    """
    if as_of_date is None:
        as_of_date = timezone.localdate()

    eligible_invoices = Invoice.objects.filter(
        due_date__lt=as_of_date,
        total_amount__gt=F("amount_paid"),
    ).exclude(status__in=["PAID", "VOID"]).order_by("pk")

    eligible_count = eligible_invoices.count()
    updated_count = 0
    already_overdue_count = 0
    details = []

    with transaction.atomic():
        for invoice in eligible_invoices:
            outstanding_balance = invoice.outstanding_balance
            previous_status = invoice.status
            is_updated = False

            if previous_status == "OVERDUE":
                already_overdue_count += 1
            else:
                updated_count += 1
                if not dry_run:
                    invoice.status = "OVERDUE"
                    invoice.save(update_fields=["status"])
                    is_updated = True

            details.append({
                "invoice": invoice,
                "invoice_number": invoice.invoice_number,
                "previous_status": previous_status,
                "new_status": "OVERDUE",
                "outstanding_balance": outstanding_balance,
                "is_updated": is_updated,
            })

    return {
        "as_of_date": as_of_date,
        "eligible_count": eligible_count,
        "updated_count": updated_count,
        "already_overdue_count": already_overdue_count,
        "dry_run": dry_run,
        "details": details,
    }


def run_billing_for_all_active_subscriptions(billing_date: date = None) -> dict:
    """
    Run billing for all active subscriptions due on or before billing_date.
    Returns summary dict with counts.
    """
    if billing_date is None:
        billing_date = date.today()

    overdue_summary = update_overdue_invoices(as_of_date=billing_date)

    active_subs = Subscription.objects.filter(
        status='ACTIVE',
        next_billing_date__lte=billing_date
    ).select_related('plan', 'customer')

    created_count = 0
    skipped_count = 0
    error_count = 0
    errors = []

    from dateutil.relativedelta import relativedelta
    cycle_map = {'MONTHLY': 1, 'QUARTERLY': 3, 'ANNUALLY': 12}

    for sub in active_subs:
        try:
            invoice, created = generate_invoice_for_subscription(sub, billing_date)
            if created:
                created_count += 1
                # Advance next_billing_date
                months = cycle_map.get(sub.billing_cycle, 1)
                sub.next_billing_date = sub.next_billing_date + relativedelta(months=months)
                sub.save(update_fields=['next_billing_date'])
            else:
                skipped_count += 1
        except Exception as e:
            error_count += 1
            errors.append(f"SUB-{sub.pk}: {e}")

    return {
        'billing_date': billing_date,
        'total_processed': active_subs.count(),
        'invoices_created': created_count,
        'invoices_skipped': skipped_count,
        'errors': error_count,
        'error_details': errors,
        'overdue_invoices_updated': overdue_summary['updated_count'],
    }
