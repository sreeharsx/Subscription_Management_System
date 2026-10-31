"""
Subscription business logic services.
"""
from datetime import date
from dateutil.relativedelta import relativedelta
from django.db import transaction
from .models import Subscription


def get_next_billing_date(start_date: date, billing_cycle: str) -> date:
    """Calculate next billing date based on cycle."""
    cycle_map = {'MONTHLY': 1, 'QUARTERLY': 3, 'ANNUALLY': 12}
    months = cycle_map.get(billing_cycle, 1)
    return start_date + relativedelta(months=months)


def create_subscription_from_quotation(quotation) -> Subscription:
    """
    Convert an accepted quotation into a Subscription.
    Idempotency is enforced by the OneToOneField on Quotation.
    """
    today = date.today()
    billing_cycle = quotation.plan.billing_cycle
    tax_rate = quotation.tax.rate if quotation.tax else 0

    subscription = Subscription.objects.create(
        quotation=quotation,
        customer=quotation.customer,
        plan=quotation.plan,
        status='ACTIVE',
        billing_cycle=billing_cycle,
        plan_price=quotation.base_price,
        discount_amount=quotation.discount_amount,
        tax_rate=tax_rate,
        start_date=today,
        next_billing_date=today,  # Bill immediately on creation
    )
    return subscription


def renew_subscription(subscription: Subscription) -> Subscription:
    """
    Renew an EXPIRED subscription by reactivating it and extending its term.
    Option 1: Extends existing subscription without creating new quotations/subscriptions.

    Concurrency safe:
    Uses an atomic compare-and-set query (status='EXPIRED') to prevent duplicate renewals.
    """
    if not subscription.can_renew:
        raise ValueError(f"Cannot renew subscription in {subscription.status} status. Only EXPIRED subscriptions can be renewed.")

    cycle_map = {'MONTHLY': 1, 'QUARTERLY': 3, 'ANNUALLY': 12}
    months = cycle_map.get(subscription.billing_cycle, 1)
    today = date.today()

    # 1. Determine new end_date if end_date was previously set
    new_end_date = None
    if subscription.end_date is not None:
        anchor_date = max(today, subscription.end_date)
        new_end_date = anchor_date + relativedelta(months=months)

    # 2. Determine new next_billing_date
    current_period_key = today.strftime('%Y-%m')
    has_invoice_for_current_month = subscription.invoices.filter(billing_period_key=current_period_key).exists()

    if has_invoice_for_current_month:
        # Use existing subscription.next_billing_date as the billing-cycle anchor
        # Advance it using cycle duration until it is past today and beyond the current invoiced month
        anchor_date = subscription.next_billing_date or today
        candidate_date = anchor_date
        while candidate_date <= today or candidate_date.strftime('%Y-%m') == current_period_key:
            candidate_date = candidate_date + relativedelta(months=months)
        new_next_billing_date = candidate_date
    else:
        # No invoice for current month -> bill immediately today
        new_next_billing_date = today

    # 3. Explicit model validation before applying changes
    subscription.end_date = new_end_date
    subscription.next_billing_date = new_next_billing_date
    subscription.full_clean()

    # 4. Atomic Compare-And-Set (CAS) to protect against concurrent renewal races on SQLite
    with transaction.atomic():
        updated_count = Subscription.objects.filter(
            pk=subscription.pk,
            status='EXPIRED'
        ).update(
            status='ACTIVE',
            end_date=new_end_date,
            next_billing_date=new_next_billing_date
        )

        if updated_count == 0:
            raise ValueError("Subscription renewal conflict: The subscription was already renewed or its status changed.")

        subscription.refresh_from_db()

    return subscription
