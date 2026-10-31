"""
Subscription business logic services.
"""
from datetime import date
from dateutil.relativedelta import relativedelta
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
