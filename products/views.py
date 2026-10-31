from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from .models import Product, SubscriptionPlan, TaxConfiguration, DiscountConfiguration
from .forms import ProductForm, SubscriptionPlanForm, TaxConfigurationForm, DiscountConfigurationForm


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


# --- Products ---

@login_required
def product_list(request):
    products = Product.objects.prefetch_related('plans').all()
    return render(request, 'products/product_list.html', {'products': products})


@login_required
@staff_required
def product_create(request):
    if request.method == 'POST':
        form = ProductForm(request.POST)
        if form.is_valid():
            product = form.save()
            messages.success(request, f"Product '{product.name}' created.")
            return redirect('products:product_detail', pk=product.pk)
    else:
        form = ProductForm()
    return render(request, 'products/product_form.html', {'form': form, 'title': 'Add Product'})


@login_required
def product_detail(request, pk):
    product = get_object_or_404(Product, pk=pk)
    plans = product.plans.all()
    return render(request, 'products/product_detail.html', {'product': product, 'plans': plans})


@login_required
@staff_required
def product_edit(request, pk):
    product = get_object_or_404(Product, pk=pk)
    if request.method == 'POST':
        form = ProductForm(request.POST, instance=product)
        if form.is_valid():
            form.save()
            messages.success(request, "Product updated.")
            return redirect('products:product_detail', pk=pk)
    else:
        form = ProductForm(instance=product)
    return render(request, 'products/product_form.html', {'form': form, 'title': 'Edit Product', 'edit': True})


# --- Plans ---

@login_required
def plan_list(request):
    plans = SubscriptionPlan.objects.select_related('product').all()
    return render(request, 'products/plan_list.html', {'plans': plans})


@login_required
@staff_required
def plan_create(request):
    if request.method == 'POST':
        form = SubscriptionPlanForm(request.POST)
        if form.is_valid():
            plan = form.save()
            messages.success(request, f"Plan '{plan.name}' created.")
            return redirect('products:plan_list')
    else:
        form = SubscriptionPlanForm()
    return render(request, 'products/plan_form.html', {'form': form, 'title': 'Add Plan'})


@login_required
def plan_detail(request, pk):
    plan = get_object_or_404(SubscriptionPlan, pk=pk)
    return render(request, 'products/plan_detail.html', {'plan': plan})


@login_required
@staff_required
def plan_edit(request, pk):
    plan = get_object_or_404(SubscriptionPlan, pk=pk)
    if request.method == 'POST':
        form = SubscriptionPlanForm(request.POST, instance=plan)
        if form.is_valid():
            form.save()
            messages.success(request, "Plan updated.")
            return redirect('products:plan_list')
    else:
        form = SubscriptionPlanForm(instance=plan)
    return render(request, 'products/plan_form.html', {'form': form, 'title': 'Edit Plan', 'edit': True})


# --- Taxes ---

@login_required
@staff_required
def tax_list(request):
    taxes = TaxConfiguration.objects.all()
    return render(request, 'products/tax_list.html', {'taxes': taxes})


@login_required
@staff_required
def tax_create(request):
    if request.method == 'POST':
        form = TaxConfigurationForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Tax configuration created.")
            return redirect('products:tax_list')
    else:
        form = TaxConfigurationForm()
    return render(request, 'products/tax_form.html', {'form': form, 'title': 'Add Tax'})


@login_required
@staff_required
def tax_edit(request, pk):
    tax = get_object_or_404(TaxConfiguration, pk=pk)
    if request.method == 'POST':
        form = TaxConfigurationForm(request.POST, instance=tax)
        if form.is_valid():
            form.save()
            messages.success(request, "Tax updated.")
            return redirect('products:tax_list')
    else:
        form = TaxConfigurationForm(instance=tax)
    return render(request, 'products/tax_form.html', {'form': form, 'title': 'Edit Tax', 'edit': True})


# --- Discounts ---

@login_required
@staff_required
def discount_list(request):
    discounts = DiscountConfiguration.objects.all()
    return render(request, 'products/discount_list.html', {'discounts': discounts})


@login_required
@staff_required
def discount_create(request):
    if request.method == 'POST':
        form = DiscountConfigurationForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Discount created.")
            return redirect('products:discount_list')
    else:
        form = DiscountConfigurationForm()
    return render(request, 'products/discount_form.html', {'form': form, 'title': 'Add Discount'})


@login_required
@staff_required
def discount_edit(request, pk):
    discount = get_object_or_404(DiscountConfiguration, pk=pk)
    if request.method == 'POST':
        form = DiscountConfigurationForm(request.POST, instance=discount)
        if form.is_valid():
            form.save()
            messages.success(request, "Discount updated.")
            return redirect('products:discount_list')
    else:
        form = DiscountConfigurationForm(instance=discount)
    return render(request, 'products/discount_form.html', {'form': form, 'title': 'Edit Discount', 'edit': True})
