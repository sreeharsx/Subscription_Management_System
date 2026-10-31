from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from accounts.services import log_activity
from .models import Subscription


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
    if request.user.is_staff or request.user.is_superuser:
        subs = Subscription.objects.select_related('customer__user', 'plan__product').all()
    elif hasattr(request.user, 'customer_profile'):
        subs = Subscription.objects.filter(customer=request.user.customer_profile).select_related('plan__product')
    else:
        subs = Subscription.objects.none()
    return render(request, 'subscriptions/subscription_list.html', {'subscriptions': subs})


@login_required
def subscription_detail(request, pk):
    sub = get_subscription_for_user(request, pk)
    invoices = sub.invoices.all().order_by('-issue_date')
    return render(request, 'subscriptions/subscription_detail.html', {'subscription': sub, 'invoices': invoices})


@login_required
@staff_required
def subscription_pause(request, pk):
    sub = get_object_or_404(Subscription, pk=pk)
    if request.method == 'POST':
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
def subscription_resume(request, pk):
    sub = get_object_or_404(Subscription, pk=pk)
    if request.method == 'POST':
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
def subscription_cancel(request, pk):
    sub = get_object_or_404(Subscription, pk=pk)
    if request.method == 'POST':
        if sub.can_transition_to('CANCELLED'):
            sub.status = 'CANCELLED'
            sub.save()
            log_activity(request.user, 'SUBSCRIPTION_CANCELLED', sub, f"Subscription SUB-{sub.pk:04d} cancelled.")
            messages.success(request, "Subscription cancelled.")
        else:
            messages.error(request, f"Cannot cancel a {sub.status} subscription.")
    return redirect('subscriptions:subscription_detail', pk=pk)
