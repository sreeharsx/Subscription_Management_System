from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import transaction, IntegrityError
from django.db.models import Q
from .models import Quotation
from .forms import QuotationForm
from accounts.models import CustomerProfile


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
    search_query = request.GET.get('q', '').strip()
    status_filter = request.GET.get('status', '').strip().upper()

    if request.user.is_staff or request.user.is_superuser:
        quotations = Quotation.objects.select_related('customer__user', 'plan').all()
    elif hasattr(request.user, 'customer_profile'):
        quotations = Quotation.objects.filter(customer=request.user.customer_profile).select_related('customer__user', 'plan')
    else:
        quotations = Quotation.objects.none()

    if status_filter in dict(Quotation.STATUS_CHOICES):
        quotations = quotations.filter(status=status_filter)

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
        elif search_query.upper().startswith('QT-') and search_query[3:].isdigit():
            query_filter |= Q(pk=int(search_query[3:]))
        quotations = quotations.filter(query_filter)

    return render(request, 'quotations/quotation_list.html', {
        'quotations': quotations,
        'search_query': search_query,
        'status_filter': status_filter,
        'status_choices': Quotation.STATUS_CHOICES,
    })


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
        initial = {}
        customer_id = request.GET.get('customer')
        if customer_id:
            try:
                customer = CustomerProfile.objects.get(pk=customer_id)
                initial['customer'] = customer
            except (CustomerProfile.DoesNotExist, ValueError):
                pass
        form = QuotationForm(initial=initial)
    return render(request, 'quotations/quotation_form.html', {'form': form, 'title': 'Create Quotation'})


@login_required
def quotation_detail(request, pk):
    quotation = get_quotation_for_user(request, pk)
    subscription = getattr(quotation, 'subscription', None)
    is_owner_customer = (
        not (request.user.is_staff or request.user.is_superuser) and
        hasattr(request.user, 'customer_profile') and
        quotation.customer == request.user.customer_profile
    )
    return render(request, 'quotations/quotation_detail.html', {
        'quotation': quotation,
        'subscription': subscription,
        'is_owner_customer': is_owner_customer,
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
            changed = form.changed_data

            if 'plan' in changed:
                q.calculate_totals(preserve_base_price=False)
            elif 'tax' in changed or 'discount' in changed:
                q.calculate_totals(preserve_base_price=True)
            elif q.total_amount is None:
                q.calculate_totals(preserve_base_price=(q.base_price is not None))

            q.save()
            messages.success(request, "Quotation updated.")
            return redirect('quotations:quotation_detail', pk=pk)
    else:
        form = QuotationForm(instance=quotation)
    return render(request, 'quotations/quotation_form.html', {'form': form, 'title': 'Edit Quotation', 'edit': True})


@login_required
@staff_required
@require_POST
def quotation_send(request, pk):
    quotation = get_object_or_404(Quotation, pk=pk)
    if not quotation.can_send():
        messages.error(request, "Quotation cannot be sent in its current state.")
        return redirect('quotations:quotation_detail', pk=pk)
    quotation.status = 'SENT'
    quotation.save()
    messages.success(request, "Quotation sent to customer.")
    return redirect('quotations:quotation_detail', pk=pk)


def _execute_quotation_acceptance(request, quotation_pk):
    """
    Internal helper for atomic quotation acceptance and subscription creation.
    Handles concurrency and IntegrityError safely.
    """
    try:
        with transaction.atomic():
            # select_for_update() locks row where supported (PostgreSQL/MySQL),
            # while SQLite benefits from transaction.atomic() + DB constraint handling
            try:
                quotation = Quotation.objects.select_for_update().get(pk=quotation_pk)
            except Quotation.DoesNotExist:
                messages.error(request, "Quotation not found.")
                return redirect('quotations:quotation_list')

            if hasattr(quotation, 'subscription'):
                messages.warning(request, "A subscription already exists for this quotation.")
                return redirect('subscriptions:subscription_detail', pk=quotation.subscription.pk)

            if not quotation.can_accept():
                messages.error(request, "Quotation cannot be accepted in its current state.")
                return redirect('quotations:quotation_detail', pk=quotation_pk)

            quotation.status = 'ACCEPTED'
            quotation.save()

            from subscriptions.services import create_subscription_from_quotation
            subscription = create_subscription_from_quotation(quotation)
            messages.success(request, f"Quotation accepted. Subscription #{subscription.pk} created.")
            return redirect('subscriptions:subscription_detail', pk=subscription.pk)

    except IntegrityError:
        # Race condition handled: subscription already created concurrently
        quotation = get_object_or_404(Quotation, pk=quotation_pk)
        if hasattr(quotation, 'subscription'):
            messages.warning(request, "A subscription already exists for this quotation.")
            return redirect('subscriptions:subscription_detail', pk=quotation.subscription.pk)
        messages.error(request, "Could not accept quotation due to a conflict.")
        return redirect('quotations:quotation_detail', pk=quotation_pk)


@login_required
@staff_required
@require_POST
def quotation_accept(request, pk):
    quotation = get_object_or_404(Quotation, pk=pk)
    if not quotation.can_accept():
        messages.error(request, "Only sent quotations can be accepted.")
        return redirect('quotations:quotation_detail', pk=pk)
    return _execute_quotation_acceptance(request, pk)


@login_required
@staff_required
@require_POST
def quotation_reject(request, pk):
    quotation = get_object_or_404(Quotation, pk=pk)
    if not quotation.can_reject(is_staff=True):
        messages.error(request, "Quotation cannot be rejected in its current state.")
        return redirect('quotations:quotation_detail', pk=pk)
    quotation.status = 'REJECTED'
    quotation.save()
    messages.success(request, "Quotation rejected.")
    return redirect('quotations:quotation_detail', pk=pk)


@login_required
@require_POST
def quotation_customer_accept(request, pk):
    quotation = get_quotation_for_user(request, pk)
    # Ensure caller is indeed the owning customer profile
    if not (hasattr(request.user, 'customer_profile') and quotation.customer == request.user.customer_profile):
        raise PermissionDenied

    if not quotation.can_accept():
        messages.error(request, "This quotation cannot be accepted or has expired.")
        return redirect('quotations:quotation_detail', pk=pk)

    return _execute_quotation_acceptance(request, pk)


@login_required
@require_POST
def quotation_customer_reject(request, pk):
    quotation = get_quotation_for_user(request, pk)
    # Ensure caller is indeed the owning customer profile
    if not (hasattr(request.user, 'customer_profile') and quotation.customer == request.user.customer_profile):
        raise PermissionDenied

    if not quotation.can_reject(is_staff=False):
        messages.error(request, "Only sent quotations can be rejected.")
        return redirect('quotations:quotation_detail', pk=pk)

    quotation.status = 'REJECTED'
    quotation.save()
    messages.success(request, "You have rejected this quotation.")
    return redirect('quotations:quotation_detail', pk=pk)
