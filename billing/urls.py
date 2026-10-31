from django.urls import path
from . import views

app_name = 'billing'

urlpatterns = [
    path('invoices/', views.invoice_list, name='invoice_list'),
    path('invoices/<int:pk>/', views.invoice_detail, name='invoice_detail'),
    path('invoices/<int:pk>/pay/', views.record_payment_view, name='record_payment'),
    path('invoices/<int:pk>/customer-pay/', views.customer_pay_invoice_view, name='customer_pay_invoice'),
    path('run-billing/', views.run_billing_view, name='run_billing'),
    path('payments/', views.payment_list, name='payment_list'),
]
