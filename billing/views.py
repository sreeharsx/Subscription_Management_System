from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db.models import Sum, Q
from datetime import date
from decimal import Decimal
import uuid
from .models import Invoice, Payment
from .forms import PaymentForm, RunBillingForm, CustomerPaymentForm
from .services import run_billing_for_all_active_subscriptions, record_payment


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


def get_invoice_for_user(request, pk):
    invoice = get_object_or_404(Invoice, pk=pk)
    if request.user.is_staff or request.user.is_superuser:
        return invoice
    if hasattr(request.user, 'customer_profile'):
        if invoice.subscription.customer == request.user.customer_profile:
            return invoice
    raise PermissionDenied


@login_required
def invoice_list(request):
    if request.user.is_staff or request.user.is_superuser:
        invoices = Invoice.objects.select_related(
            'subscription__customer__user', 'subscription__plan'
        ).all()
    elif hasattr(request.user, 'customer_profile'):
        invoices = Invoice.objects.filter(
            subscription__customer=request.user.customer_profile
        ).select_related('subscription__plan')
    else:
        invoices = Invoice.objects.none()

    # Optional status filter
    status_filter = request.GET.get('status')
    if status_filter:
        invoices = invoices.filter(status=status_filter)

    return render(request, 'billing/invoice_list.html', {
        'invoices': invoices,
        'status_choices': Invoice.STATUS_CHOICES,
        'active_status': status_filter,
    })


@login_required
def invoice_detail(request, pk):
    invoice = get_invoice_for_user(request, pk)
    payments = invoice.payments.all()
    can_pay = request.user.is_staff or request.user.is_superuser
    can_customer_pay = (
        not can_pay and
        invoice.status in ('ISSUED', 'OVERDUE', 'PARTIALLY_PAID') and
        invoice.outstanding_balance > Decimal('0.00')
    )
    return render(request, 'billing/invoice_detail.html', {
        'invoice': invoice,
        'payments': payments,
        'can_pay': can_pay,
        'can_customer_pay': can_customer_pay,
    })


@login_required
def customer_pay_invoice_view(request, pk):
    invoice = get_invoice_for_user(request, pk)

    # Check if invoice is in a payable state
    if invoice.status == 'VOID':
        messages.error(request, "Cannot pay a cancelled/void invoice.")
        return redirect('billing:invoice_detail', pk=pk)
    if invoice.status == 'PAID' or invoice.outstanding_balance <= Decimal('0.00'):
        messages.info(request, "This invoice is already fully paid.")
        return redirect('billing:invoice_detail', pk=pk)

    if request.method == 'POST':
        form = CustomerPaymentForm(request.POST)
        if form.is_valid():
            payment_method = form.cleaned_data['payment_method']
            # Outstanding balance is verified and taken strictly from the server-side model
            amount = invoice.outstanding_balance
            ref_no = f"SIM-{uuid.uuid4().hex[:8].upper()}"
            try:
                record_payment(
                    invoice=invoice,
                    amount=amount,
                    payment_method=payment_method,
                    payment_date=date.today(),
                    recorded_by=request.user,
                    reference_number=ref_no,
                    notes="Customer self-service payment (Demo Simulation)",
                )
                messages.success(request, f"Payment of ₹{amount} processed successfully! Reference: {ref_no}")
                return redirect('billing:invoice_detail', pk=pk)
            except ValueError as e:
                messages.error(request, str(e))
    else:
        form = CustomerPaymentForm()

    return render(request, 'billing/customer_pay.html', {
        'invoice': invoice,
        'form': form,
    })


@login_required
@staff_required
def record_payment_view(request, pk):
    invoice = get_object_or_404(Invoice, pk=pk)
    if invoice.status == 'VOID':
        messages.error(request, "Cannot record payment against a void invoice.")
        return redirect('billing:invoice_detail', pk=pk)
    if invoice.status == 'PAID':
        messages.error(request, "Invoice is already fully paid.")
        return redirect('billing:invoice_detail', pk=pk)

    if request.method == 'POST':
        form = PaymentForm(request.POST)
        if form.is_valid():
            amount = form.cleaned_data['amount']
            try:
                record_payment(
                    invoice=invoice,
                    amount=amount,
                    payment_method=form.cleaned_data['payment_method'],
                    payment_date=form.cleaned_data['payment_date'],
                    recorded_by=request.user,
                    reference_number=form.cleaned_data.get('reference_number', ''),
                    notes=form.cleaned_data.get('notes', ''),
                )
                messages.success(request, f"Payment of ₹{amount} recorded successfully.")
                return redirect('billing:invoice_detail', pk=pk)
            except ValueError as e:
                messages.error(request, str(e))
    else:
        form = PaymentForm(initial={'payment_date': date.today(), 'amount': invoice.outstanding_balance})

    return render(request, 'billing/record_payment.html', {
        'form': form,
        'invoice': invoice,
    })


@login_required
@staff_required
def run_billing_view(request):
    result = None
    if request.method == 'POST':
        form = RunBillingForm(request.POST)
        if form.is_valid():
            billing_date = form.cleaned_data.get('billing_date') or date.today()
            result = run_billing_for_all_active_subscriptions(billing_date)
            messages.success(
                request,
                f"Billing run complete: {result['invoices_created']} invoices created, "
                f"{result['invoices_skipped']} skipped, {result['errors']} errors."
            )
    else:
        form = RunBillingForm(initial={'billing_date': date.today()})

    return render(request, 'billing/run_billing.html', {
        'form': form,
        'result': result,
    })


@login_required
@staff_required
def payment_list(request):
    payments = Payment.objects.select_related(
        'invoice__subscription__customer__user',
        'recorded_by',
    ).all()
    total_received = Payment.objects.filter(status='COMPLETED').aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    return render(request, 'billing/payment_list.html', {
        'payments': payments,
        'total_received': total_received,
    })
