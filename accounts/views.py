from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib import messages
from .models import CustomerProfile
from .forms import CustomerProfileForm, CustomerUserForm


def staff_required(view_func):
    """Decorator: requires staff or superuser."""
    from functools import wraps
    from django.core.exceptions import PermissionDenied
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
@staff_required  # type: ignore[arg-type]
def customer_list(request):
    customers = CustomerProfile.objects.select_related('user').all()
    return render(request, 'accounts/customer_list.html', {'customers': customers})


@login_required
@staff_required  # type: ignore[arg-type]
def customer_create(request):
    if request.method == 'POST':
        user_form = CustomerUserForm(request.POST)
        profile_form = CustomerProfileForm(request.POST)
        if user_form.is_valid() and profile_form.is_valid():
            user = user_form.save(commit=False)
            user.set_password(user_form.cleaned_data['password'])
            user.save()
            profile = profile_form.save(commit=False)
            profile.user = user
            profile.save()
            messages.success(request, f"Customer '{user.get_full_name() or user.username}' created successfully.")
            return redirect('accounts:customer_list')
    else:
        user_form = CustomerUserForm()
        profile_form = CustomerProfileForm()
    return render(request, 'accounts/customer_form.html', {
        'user_form': user_form,
        'profile_form': profile_form,
        'title': 'Add Customer',
    })


@login_required
def customer_detail(request, pk):
    customer = get_object_or_404(CustomerProfile, pk=pk)
    # Staff/admin can see any customer; customer can only see themselves
    if not (request.user.is_staff or request.user.is_superuser):
        if not hasattr(request.user, 'customer_profile') or request.user.customer_profile.pk != pk:
            from django.core.exceptions import PermissionDenied
            raise PermissionDenied
    return render(request, 'accounts/customer_detail.html', {'customer': customer})


@login_required
@staff_required  # type: ignore[arg-type]
def customer_edit(request, pk):
    customer = get_object_or_404(CustomerProfile, pk=pk)
    if request.method == 'POST':
        profile_form = CustomerProfileForm(request.POST, instance=customer)
        if profile_form.is_valid():
            profile_form.save()
            messages.success(request, "Customer updated.")
            return redirect('accounts:customer_detail', pk=pk)
    else:
        profile_form = CustomerProfileForm(instance=customer)
    return render(request, 'accounts/customer_form.html', {
        'profile_form': profile_form,
        'title': 'Edit Customer',
        'edit': True,
    })
