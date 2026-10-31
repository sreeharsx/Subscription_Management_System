from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import transaction
from accounts.services import log_activity
from .models import Quotation
from .forms import QuotationForm


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


def get_quotation_for_user(request, pk):
    """Return quotation if user has access, raise 403 otherwise."""
    quotation = get_object_or_404(Quotation, pk=pk)
    if request.user.is_staff or request.user.is_superuser:
        return quotation
    # Customer: must own this quotation
    if hasattr(request.user, 'customer_profile') and quotation.customer == request.user.customer_profile:
        return quotation
    raise PermissionDenied


@login_required
def quotation_list(request):
    if request.user.is_staff or request.user.is_superuser:
        quotations = Quotation.objects.select_related('customer__user', 'plan').all()
    elif hasattr(request.user, 'customer_profile'):
        quotations = Quotation.objects.filter(customer=request.user.customer_profile).select_related('plan')
    else:
        quotations = Quotation.objects.none()
    return render(request, 'quotations/quotation_list.html', {'quotations': quotations})


@login_required
@staff_required
def quotation_create(request):
    if request.method == 'POST':
        form = QuotationForm(request.POST)
        if form.is_valid():
            quotation = form.save(commit=False)
            quotation.created_by = request.user
            quotation.calculate_totals()
            quotation.save()
            messages.success(request, f"Quotation {quotation} created.")
            return redirect('quotations:quotation_detail', pk=quotation.pk)
    else:
        form = QuotationForm()
    return render(request, 'quotations/quotation_form.html', {'form': form, 'title': 'Create Quotation'})


@login_required
def quotation_detail(request, pk):
    quotation = get_quotation_for_user(request, pk)
    # Check if subscription exists
    subscription = getattr(quotation, 'subscription', None)
    return render(request, 'quotations/quotation_detail.html', {
        'quotation': quotation,
        'subscription': subscription,
    })


@login_required
@staff_required
def quotation_edit(request, pk):
    quotation = get_object_or_404(Quotation, pk=pk)
    if quotation.status != 'DRAFT':
        messages.error(request, "Only draft quotations can be edited.")
        return redirect('quotations:quotation_detail', pk=pk)
    if request.method == 'POST':
        form = QuotationForm(request.POST, instance=quotation)
        if form.is_valid():
            q = form.save(commit=False)
            q.calculate_totals()
            q.save()
            messages.success(request, "Quotation updated.")
            return redirect('quotations:quotation_detail', pk=pk)
    else:
        form = QuotationForm(instance=quotation)
    return render(request, 'quotations/quotation_form.html', {'form': form, 'title': 'Edit Quotation', 'edit': True})


@login_required
@staff_required
def quotation_send(request, pk):
    quotation = get_object_or_404(Quotation, pk=pk)
    if not quotation.can_send():
        messages.error(request, "Quotation cannot be sent in its current state.")
        return redirect('quotations:quotation_detail', pk=pk)
    if request.method == 'POST':
        quotation.status = 'SENT'
        quotation.save()
        messages.success(request, "Quotation sent to customer.")
    return redirect('quotations:quotation_detail', pk=pk)


@login_required
@staff_required
@transaction.atomic
def quotation_accept(request, pk):
    quotation = get_object_or_404(Quotation, pk=pk)
    if not quotation.can_accept():
        messages.error(request, "Only sent quotations can be accepted.")
        return redirect('quotations:quotation_detail', pk=pk)
    if request.method == 'POST':
        # Check if subscription already exists (idempotency guard)
        if hasattr(quotation, 'subscription'):
            messages.warning(request, "A subscription already exists for this quotation.")
            return redirect('subscriptions:subscription_detail', pk=quotation.subscription.pk)
        quotation.status = 'ACCEPTED'
        quotation.save()
        # Create subscription
        from subscriptions.services import create_subscription_from_quotation
        subscription = create_subscription_from_quotation(quotation)
        log_activity(request.user, 'QUOTATION_ACCEPTED', quotation, f"Accepted quotation; created SUB-{subscription.pk:04d}")
        messages.success(request, f"Quotation accepted. Subscription #{subscription.pk} created.")
        return redirect('subscriptions:subscription_detail', pk=subscription.pk)
    return redirect('quotations:quotation_detail', pk=pk)


@login_required
@staff_required
def quotation_reject(request, pk):
    quotation = get_object_or_404(Quotation, pk=pk)
    if not quotation.can_reject():
        messages.error(request, "Quotation cannot be rejected in its current state.")
        return redirect('quotations:quotation_detail', pk=pk)
    if request.method == 'POST':
        quotation.status = 'REJECTED'
        quotation.save()
        log_activity(request.user, 'QUOTATION_REJECTED', quotation, f"Quotation QT-{quotation.pk:04d} rejected.")
        messages.success(request, "Quotation rejected.")
    return redirect('quotations:quotation_detail', pk=pk)
