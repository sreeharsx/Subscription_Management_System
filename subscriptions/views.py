from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from .models import Subscription
from .services import renew_subscription
from accounts.services import log_activity


def staff_required(view_func):
    from functools import wraps
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            from django.conf import settings
            return redirect(settings.LOGIN_URL)
        if not (request.user.is_staff or request.user.is_superuser):
            raise PermissionDenied
        return view_func(request, *args, **kwargs)
    return wrapper


def get_subscription_for_user(request, pk):
    sub = get_object_or_404(Subscription, pk=pk)
    if request.user.is_staff or request.user.is_superuser:
        return sub
    if hasattr(request.user, 'customer_profile') and sub.customer == request.user.customer_profile:
        return sub
    raise PermissionDenied


@login_required
def subscription_list(request):
    search_query = request.GET.get('q', '').strip()
    status_filter = request.GET.get('status', '').strip().upper()

    # Initial queryset with strict role-based access control
    if request.user.is_staff or request.user.is_superuser:
        subs = Subscription.objects.select_related('customer__user', 'plan__product').all()
    elif hasattr(request.user, 'customer_profile'):
        # Customer ownership filtering applied strictly BEFORE search and status filtering
        subs = Subscription.objects.filter(customer=request.user.customer_profile).select_related('customer__user', 'plan__product')
    else:
        subs = Subscription.objects.none()

    # Status filtering (ignoring invalid values safely)
    if status_filter in dict(Subscription.STATUS_CHOICES):
        subs = subs.filter(status=status_filter)

    # Search filtering
    if search_query:
        query_filter = (
            Q(customer__company_name__icontains=search_query) |
            Q(customer__user__first_name__icontains=search_query) |
            Q(customer__user__last_name__icontains=search_query) |
            Q(customer__user__email__icontains=search_query) |
            Q(plan__name__icontains=search_query)
        )
        if search_query.isdigit():
            query_filter |= Q(pk=int(search_query))
        elif search_query.upper().startswith('SUB-') and search_query[4:].isdigit():
            query_filter |= Q(pk=int(search_query[4:]))
        subs = subs.filter(query_filter)

    return render(request, 'subscriptions/subscription_list.html', {
        'subscriptions': subs,
        'search_query': search_query,
        'status_filter': status_filter,
        'status_choices': Subscription.STATUS_CHOICES,
    })


@login_required
def subscription_detail(request, pk):
    sub = get_subscription_for_user(request, pk)
    invoices = sub.invoices.all().order_by('-issue_date')
    return render(request, 'subscriptions/subscription_detail.html', {'subscription': sub, 'invoices': invoices})


@login_required
@staff_required
@require_POST
def subscription_pause(request, pk):
    sub = get_object_or_404(Subscription, pk=pk)
    if sub.can_transition_to('PAUSED'):
        sub.status = 'PAUSED'
        sub.save()
        log_activity(request.user, 'SUBSCRIPTION_PAUSED', sub, f"Subscription SUB-{sub.pk:04d} paused.")
        messages.success(request, "Subscription paused.")
    else:
        messages.error(request, f"Cannot pause a {sub.status} subscription.")
    return redirect('subscriptions:subscription_detail', pk=pk)


@login_required
@staff_required
@require_POST
def subscription_resume(request, pk):
    sub = get_object_or_404(Subscription, pk=pk)
    if sub.can_transition_to('ACTIVE'):
        sub.status = 'ACTIVE'
        sub.save()
        log_activity(request.user, 'SUBSCRIPTION_RESUMED', sub, f"Subscription SUB-{sub.pk:04d} resumed to active.")
        messages.success(request, "Subscription resumed.")
    else:
        messages.error(request, f"Cannot resume a {sub.status} subscription.")
    return redirect('subscriptions:subscription_detail', pk=pk)


@login_required
@staff_required
@require_POST
def subscription_cancel(request, pk):
    sub = get_object_or_404(Subscription, pk=pk)
    if sub.can_transition_to('CANCELLED'):
        sub.status = 'CANCELLED'
        sub.save()
        log_activity(request.user, 'SUBSCRIPTION_CANCELLED', sub, f"Subscription SUB-{sub.pk:04d} cancelled.")
        messages.success(request, "Subscription cancelled.")
    else:
        messages.error(request, f"Cannot cancel a {sub.status} subscription.")
    return redirect('subscriptions:subscription_detail', pk=pk)


@login_required
@staff_required
@require_POST
def subscription_renew(request, pk):
    sub = get_object_or_404(Subscription, pk=pk)
    try:
        renew_subscription(sub)
        log_activity(request.user, 'SUBSCRIPTION_RENEWED', sub, f"Subscription SUB-{sub.pk:04d} renewed.")
        messages.success(request, f"Subscription SUB-{sub.pk:04d} successfully renewed and reactivated.")
    except ValueError as e:
        messages.error(request, str(e))
    return redirect('subscriptions:subscription_detail', pk=pk)
