from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Q
from .models import CustomerProfile
from .forms import CustomerProfileForm, CustomerUserForm, CustomerUserEditForm


def staff_required(view_func):
    """Decorator: requires staff or superuser."""
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


@login_required
@staff_required
def customer_list(request):
    """List all customers with real-time search filtering."""
    query = request.GET.get('q', '').strip()
    customers_qs = CustomerProfile.objects.select_related('user').all()

    if query:
        customers_qs = customers_qs.filter(
            Q(user__username__icontains=query) |
            Q(user__first_name__icontains=query) |
            Q(user__last_name__icontains=query) |
            Q(user__email__icontains=query) |
            Q(company_name__icontains=query) |
            Q(phone__icontains=query) |
            Q(gst_number__icontains=query)
        ).distinct()

    total_count = CustomerProfile.objects.count()
    return render(request, 'accounts/customer_list.html', {
        'customers': customers_qs,
        'query': query,
        'total_count': total_count,
        'filtered_count': customers_qs.count(),
    })


@login_required
@staff_required
def customer_create(request):
    """Create a new customer user and profile inside an atomic transaction."""
    if request.method == 'POST':
        user_form = CustomerUserForm(request.POST)
        profile_form = CustomerProfileForm(request.POST)
        if user_form.is_valid() and profile_form.is_valid():
            with transaction.atomic():
                user = user_form.save(commit=False)
                user.set_password(user_form.cleaned_data['password'])
                user.save()
                profile = profile_form.save(commit=False)
                profile.user = user
                profile.save()
            messages.success(request, f"Customer '{user.get_full_name() or user.username}' created successfully.")
            return redirect('accounts:customer_detail', pk=profile.pk)
    else:
        user_form = CustomerUserForm()
        profile_form = CustomerProfileForm()

    return render(request, 'accounts/customer_form.html', {
        'user_form': user_form,
        'profile_form': profile_form,
        'title': 'Add Customer',
        'edit': False,
    })


@login_required
def customer_detail(request, pk):
    """View customer details, quotations, and subscriptions with row-level RBAC."""
    customer = get_object_or_404(CustomerProfile.objects.select_related('user'), pk=pk)

    # Server-side data isolation: Staff/admin can see any customer; customer can only see themselves
    if not (request.user.is_staff or request.user.is_superuser):
        if not hasattr(request.user, 'customer_profile') or request.user.customer_profile.pk != pk:
            raise PermissionDenied

    subscriptions = customer.subscriptions.select_related('plan').order_by('-created_at')
    quotations = customer.quotations.select_related('plan').order_by('-created_at')

    return render(request, 'accounts/customer_detail.html', {
        'customer': customer,
        'subscriptions': subscriptions,
        'quotations': quotations,
    })


@login_required
@staff_required
def customer_edit(request, pk):
    """Edit customer profile and login user details with validation."""
    customer = get_object_or_404(CustomerProfile.objects.select_related('user'), pk=pk)

    if request.method == 'POST':
        user_form = CustomerUserEditForm(request.POST, instance=customer.user)
        profile_form = CustomerProfileForm(request.POST, instance=customer)
        if user_form.is_valid() and profile_form.is_valid():
            with transaction.atomic():
                user_form.save()
                profile_form.save()
            messages.success(request, f"Customer '{customer.user.get_full_name() or customer.user.username}' updated successfully.")
            return redirect('accounts:customer_detail', pk=pk)
    else:
        user_form = CustomerUserEditForm(instance=customer.user)
        profile_form = CustomerProfileForm(instance=customer)

    return render(request, 'accounts/customer_form.html', {
        'user_form': user_form,
        'profile_form': profile_form,
        'title': f'Edit Customer: {customer.user.get_full_name() or customer.user.username}',
        'edit': True,
        'customer': customer,
    })
