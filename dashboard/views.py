from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Count, Q
from django.utils import timezone
from datetime import date, timedelta
from decimal import Decimal
from subscriptions.models import Subscription
from billing.models import Invoice, Payment


@login_required
def dashboard_index(request):
    today = date.today()
    next_30_days = today + timedelta(days=30)

    if request.user.is_staff or request.user.is_superuser:
        # === Admin/Staff metrics ===
        active_subscriptions = Subscription.objects.filter(status='ACTIVE').count()
        paused_subscriptions = Subscription.objects.filter(status='PAUSED').count()
        cancelled_subscriptions = Subscription.objects.filter(status='CANCELLED').count()

        # Revenue = sum of COMPLETED payments
        total_revenue = Payment.objects.filter(
            status='COMPLETED'
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

        # Outstanding = sum of outstanding_balance where invoice not fully paid
        outstanding_data = Invoice.objects.filter(
            status__in=['ISSUED', 'PARTIALLY_PAID', 'OVERDUE']
        ).aggregate(
            total_invoiced=Sum('total_amount'),
            total_paid=Sum('amount_paid')
        )
        total_invoiced = outstanding_data['total_invoiced'] or Decimal('0.00')
        total_inv_paid = outstanding_data['total_paid'] or Decimal('0.00')
        total_outstanding = total_invoiced - total_inv_paid

        # Overdue
        overdue_invoices = Invoice.objects.filter(
            status__in=['ISSUED', 'PARTIALLY_PAID'],
            due_date__lt=today
        ).select_related('subscription__customer__user')[:10]
        overdue_count = Invoice.objects.filter(
            status__in=['ISSUED', 'PARTIALLY_PAID'],
            due_date__lt=today
        ).count()

        overdue_agg = Invoice.objects.filter(
            status__in=['ISSUED', 'PARTIALLY_PAID'],
            due_date__lt=today
        ).aggregate(
            total=Sum('total_amount'),
            paid=Sum('amount_paid')
        )
        overdue_balance_val = (overdue_agg['total'] or Decimal('0.00')) - (overdue_agg['paid'] or Decimal('0.00'))

        # Upcoming renewals
        upcoming_renewals = Subscription.objects.filter(
            status='ACTIVE',
            next_billing_date__lte=next_30_days,
            next_billing_date__gte=today,
        ).select_related('customer__user', 'plan').order_by('next_billing_date')[:10]

        # Recent payments
        recent_payments = Payment.objects.filter(
            status='COMPLETED'
        ).select_related('invoice__subscription__customer__user').order_by('-payment_date')[:10]

        # Monthly revenue (last 6 months) for chart
        monthly_revenue = []
        for i in range(5, -1, -1):
            month_date = today.replace(day=1) - timedelta(days=i * 30)
            month_start = month_date.replace(day=1)
            if month_start.month == 12:
                month_end = month_start.replace(year=month_start.year + 1, month=1, day=1)
            else:
                month_end = month_start.replace(month=month_start.month + 1, day=1)
            month_total = Payment.objects.filter(
                status='COMPLETED',
                payment_date__gte=month_start,
                payment_date__lt=month_end,
            ).aggregate(t=Sum('amount'))['t'] or Decimal('0.00')
            monthly_revenue.append({
                'label': month_start.strftime('%b %Y'),
                'amount': float(month_total),
            })

        context = {
            'is_staff_view': True,
            'active_subscriptions': active_subscriptions,
            'paused_subscriptions': paused_subscriptions,
            'cancelled_subscriptions': cancelled_subscriptions,
            'total_revenue': total_revenue,
            'total_outstanding': total_outstanding,
            'overdue_count': overdue_count,
            'overdue_balance': overdue_balance_val,
            'overdue_invoices': overdue_invoices,
            'upcoming_renewals': upcoming_renewals,
            'recent_payments': recent_payments,
            'monthly_revenue': monthly_revenue,
        }
    else:
        # Customer view
        if hasattr(request.user, 'customer_profile'):
            cp = request.user.customer_profile
            my_subs = Subscription.objects.filter(customer=cp)
            my_invoices = Invoice.objects.filter(subscription__customer=cp)
            my_payments = Payment.objects.filter(invoice__subscription__customer=cp, status='COMPLETED')

            context = {
                'is_staff_view': False,
                'active_subscriptions': my_subs.filter(status='ACTIVE').count(),
                'total_invoices': my_invoices.count(),
                'total_paid': my_payments.aggregate(t=Sum('amount'))['t'] or Decimal('0.00'),
                'outstanding': (
                    (my_invoices.filter(status__in=['ISSUED', 'PARTIALLY_PAID', 'OVERDUE'])
                     .aggregate(t=Sum('total_amount'))['t'] or Decimal('0.00')) -
                    (my_invoices.filter(status__in=['ISSUED', 'PARTIALLY_PAID', 'OVERDUE'])
                     .aggregate(p=Sum('amount_paid'))['p'] or Decimal('0.00'))
                ),
                'recent_invoices': my_invoices.order_by('-issue_date')[:5],
                'recent_payments': my_payments.order_by('-payment_date')[:5],
            }
        else:
            context = {'is_staff_view': False}

    return render(request, 'dashboard/index.html', context)
