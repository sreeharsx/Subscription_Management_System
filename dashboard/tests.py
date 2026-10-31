from decimal import Decimal
from datetime import date
from django.test import TestCase, Client
from django.contrib.auth.models import User
from accounts.models import CustomerProfile
from products.models import Product, SubscriptionPlan, TaxConfiguration
from quotations.models import Quotation
from subscriptions.services import create_subscription_from_quotation
from billing.services import generate_invoice_for_subscription, record_payment


class DashboardMetricsTestCase(TestCase):
    def setUp(self):
        self.client = Client()
        self.staff_user = User.objects.create_user('staff_dash', 'staff@example.com', 'pass123', is_staff=True)
        self.cust_user = User.objects.create_user('cust_dash', 'cust@example.com', 'pass123')
        self.customer = CustomerProfile.objects.create(user=self.cust_user, company_name="Dash Corp")

        self.product = Product.objects.create(name="Suite D")
        self.plan = SubscriptionPlan.objects.create(
            product=self.product,
            name="Plan D",
            billing_cycle="MONTHLY",
            base_price=Decimal("1000.00")
        )
        self.tax = TaxConfiguration.objects.create(name="GST 18%", rate=Decimal("18.00"))

        self.quotation = Quotation.objects.create(
            customer=self.customer,
            plan=self.plan,
            tax=self.tax,
            status='ACCEPTED'
        )
        self.subscription = create_subscription_from_quotation(self.quotation)
        self.invoice, _ = generate_invoice_for_subscription(self.subscription, billing_date=date(2026, 10, 1))

    def test_dashboard_collected_revenue_reflects_only_completed_payments(self):
        """Total revenue must equal sum of completed payments, not issued invoices."""
        self.client.login(username='staff_dash', password='pass123')

        # 1. Before payment: invoice = 1180.00, revenue = 0.00, outstanding = 1180.00
        res1 = self.client.get('/dashboard/')
        self.assertEqual(res1.context['total_revenue'], Decimal('0.00'))
        self.assertEqual(res1.context['total_outstanding'], Decimal('1180.00'))

        # 2. Pay 500.00: revenue = 500.00, outstanding = 680.00
        record_payment(
            invoice=self.invoice,
            amount=Decimal("500.00"),
            payment_method="BANK_TRANSFER",
            payment_date=date(2026, 10, 5),
            recorded_by=self.staff_user
        )
        res2 = self.client.get('/dashboard/')
        self.assertEqual(res2.context['total_revenue'], Decimal('500.00'))
        self.assertEqual(res2.context['total_outstanding'], Decimal('680.00'))
