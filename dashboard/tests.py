from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from accounts.models import CustomerProfile
from billing.models import Invoice, Payment
from products.models import Product, SubscriptionPlan
from quotations.models import Quotation
from subscriptions.models import Subscription
from subscriptions.services import create_subscription_from_quotation


class DashboardAuthenticationTests(TestCase):
    def setUp(self):
        self.client = Client()

    def test_anonymous_user_redirected_to_login(self):
        """Anonymous requests to /dashboard/ must redirect to login."""
        response = self.client.get(reverse('dashboard:index'))
        self.assertEqual(response.status_code, 302)
        expected_url = f"{reverse('accounts:login')}?next={reverse('dashboard:index')}"
        self.assertRedirects(response, expected_url)


class DashboardBaseTestCase(TestCase):
    def setUp(self):
        self.client = Client()
        self.quotation_seq = 0
        self.invoice_seq = 0

        # Create staff user
        self.staff_user = User.objects.create_user(
            username='staff_user',
            email='staff@example.com',
            password='staffpass123',
            is_staff=True,
        )

        # Create customer 1
        self.user1 = User.objects.create_user(
            username='cust1',
            email='cust1@example.com',
            password='custpass123',
        )
        self.cust1 = CustomerProfile.objects.create(
            user=self.user1,
            company_name="Acme Corp",
            phone="9876543210",
        )

        # Create customer 2
        self.user2 = User.objects.create_user(
            username='cust2',
            email='cust2@example.com',
            password='custpass123',
        )
        self.cust2 = CustomerProfile.objects.create(
            user=self.user2,
            company_name="Beta Ltd",
            phone="9123456780",
        )

        # Product & Plan
        self.product = Product.objects.create(
            name="BrightCloud",
            description="Cloud SaaS Suite",
        )
        self.plan = SubscriptionPlan.objects.create(
            product=self.product,
            name="Pro Monthly",
            billing_cycle="MONTHLY",
            base_price=Decimal("1000.00"),
        )

        # Subscriptions for customer 1 and customer 2
        self.sub1 = self.create_subscription(self.cust1)
        self.sub2 = self.create_subscription(self.cust2)

    def create_subscription(self, customer):
        self.quotation_seq += 1
        quotation = Quotation.objects.create(
            customer=customer,
            plan=self.plan,
            status='ACCEPTED',
        )
        quotation.calculate_totals()
        quotation.save()
        return create_subscription_from_quotation(quotation)

    def create_invoice(
        self,
        subscription,
        status='ISSUED',
        total_amount=Decimal('100.00'),
        amount_paid=Decimal('0.00'),
        due_date=None,
        issue_date=None,
    ):
        self.invoice_seq += 1
        today = date.today()
        if due_date is None:
            due_date = today - timedelta(days=5)
        if issue_date is None:
            issue_date = due_date - timedelta(days=15)

        return Invoice.objects.create(
            subscription=subscription,
            invoice_number=f"INV-DASH-{self.invoice_seq:04d}",
            billing_period_key=f"period-dash-{self.invoice_seq:04d}",
            status=status,
            base_amount=total_amount,
            discount_amount=Decimal('0.00'),
            tax_amount=Decimal('0.00'),
            total_amount=total_amount,
            amount_paid=amount_paid,
            issue_date=issue_date,
            due_date=due_date,
        )

    def create_payment(
        self,
        invoice,
        amount=Decimal('50.00'),
        status='COMPLETED',
        payment_date=None,
    ):
        if payment_date is None:
            payment_date = date.today()
        return Payment.objects.create(
            invoice=invoice,
            amount=amount,
            payment_date=payment_date,
            payment_method='UPI',
            status=status,
            recorded_by=self.staff_user,
        )


class DashboardStaffViewTests(DashboardBaseTestCase):
    def setUp(self):
        super().setUp()
        self.client.login(username='staff_user', password='staffpass123')

    def test_staff_user_can_access_dashboard(self):
        """Staff user can access the dashboard with is_staff_view=True and all staff metrics."""
        response = self.client.get(reverse('dashboard:index'))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['is_staff_view'])
        expected_keys = [
            'total_revenue',
            'total_outstanding',
            'overdue_count',
            'overdue_balance',
            'overdue_invoices',
            'upcoming_renewals',
            'recent_payments',
            'monthly_revenue',
            'active_subscriptions',
        ]
        for key in expected_keys:
            self.assertIn(key, response.context)

    def test_completed_payments_contribute_to_total_revenue(self):
        """Completed payments from any invoice contribute to total revenue."""
        inv = self.create_invoice(
            self.sub1,
            total_amount=Decimal('1000.00'),
            amount_paid=Decimal('650.00'),
        )
        self.create_payment(inv, amount=Decimal('400.00'), status='COMPLETED')
        self.create_payment(inv, amount=Decimal('250.00'), status='COMPLETED')

        response = self.client.get(reverse('dashboard:index'))
        self.assertEqual(response.context['total_revenue'], Decimal('650.00'))

    def test_failed_payments_do_not_contribute_to_total_revenue(self):
        """Failed payments do not contribute to total revenue."""
        inv = self.create_invoice(
            self.sub1,
            total_amount=Decimal('1000.00'),
            amount_paid=Decimal('300.00'),
        )
        self.create_payment(inv, amount=Decimal('300.00'), status='COMPLETED')
        self.create_payment(inv, amount=Decimal('500.00'), status='FAILED')

        response = self.client.get(reverse('dashboard:index'))
        self.assertEqual(response.context['total_revenue'], Decimal('300.00'))

    def test_outstanding_balance_includes_unpaid_amounts(self):
        """Outstanding balance sums unpaid amounts for ISSUED, PARTIALLY_PAID, and OVERDUE invoices."""
        # Unpaid 500
        self.create_invoice(
            self.sub1,
            status='ISSUED',
            total_amount=Decimal('500.00'),
            amount_paid=Decimal('0.00'),
        )
        # Unpaid 400
        self.create_invoice(
            self.sub1,
            status='PARTIALLY_PAID',
            total_amount=Decimal('600.00'),
            amount_paid=Decimal('200.00'),
        )
        # Unpaid 300
        self.create_invoice(
            self.sub1,
            status='OVERDUE',
            total_amount=Decimal('400.00'),
            amount_paid=Decimal('100.00'),
        )
        # Fully paid invoice (0 outstanding) - should be excluded
        self.create_invoice(
            self.sub1,
            status='PAID',
            total_amount=Decimal('300.00'),
            amount_paid=Decimal('300.00'),
        )
        # Void invoice (0 outstanding) - should be excluded
        self.create_invoice(
            self.sub1,
            status='VOID',
            total_amount=Decimal('200.00'),
            amount_paid=Decimal('0.00'),
        )

        response = self.client.get(reverse('dashboard:index'))
        self.assertEqual(response.context['total_outstanding'], Decimal('1200.00'))

    def test_already_overdue_invoices_appear_in_overdue_metrics(self):
        """Invoices with status='OVERDUE' appear in overdue_count, overdue_balance, and overdue_invoices."""
        inv = self.create_invoice(
            self.sub1,
            status='OVERDUE',
            total_amount=Decimal('500.00'),
            amount_paid=Decimal('100.00'),
            due_date=date.today() - timedelta(days=7),
        )

        response = self.client.get(reverse('dashboard:index'))
        self.assertEqual(response.context['overdue_count'], 1)
        self.assertEqual(response.context['overdue_balance'], Decimal('400.00'))
        self.assertIn(inv, response.context['overdue_invoices'])

    def test_past_due_issued_and_partially_paid_invoices_are_included(self):
        """Past-due ISSUED and PARTIALLY_PAID invoices are included; future-due invoices are excluded."""
        today = date.today()
        inv_past_issued = self.create_invoice(
            self.sub1,
            status='ISSUED',
            total_amount=Decimal('300.00'),
            amount_paid=Decimal('0.00'),
            due_date=today - timedelta(days=3),
        )
        inv_past_partial = self.create_invoice(
            self.sub1,
            status='PARTIALLY_PAID',
            total_amount=Decimal('500.00'),
            amount_paid=Decimal('200.00'),
            due_date=today - timedelta(days=5),
        )
        inv_future_issued = self.create_invoice(
            self.sub1,
            status='ISSUED',
            total_amount=Decimal('400.00'),
            amount_paid=Decimal('0.00'),
            due_date=today + timedelta(days=5),
        )
        inv_future_partial = self.create_invoice(
            self.sub1,
            status='PARTIALLY_PAID',
            total_amount=Decimal('600.00'),
            amount_paid=Decimal('100.00'),
            due_date=today + timedelta(days=2),
        )

        response = self.client.get(reverse('dashboard:index'))
        self.assertEqual(response.context['overdue_count'], 2)
        self.assertEqual(response.context['overdue_balance'], Decimal('600.00'))
        self.assertIn(inv_past_issued, response.context['overdue_invoices'])
        self.assertIn(inv_past_partial, response.context['overdue_invoices'])
        self.assertNotIn(inv_future_issued, response.context['overdue_invoices'])
        self.assertNotIn(inv_future_partial, response.context['overdue_invoices'])

    def test_paid_and_void_invoices_excluded_from_overdue_calculations(self):
        """Invoices with status='PAID' or 'VOID' are excluded from overdue calculations even if past due date."""
        today = date.today()
        self.create_invoice(
            self.sub1,
            status='PAID',
            total_amount=Decimal('400.00'),
            amount_paid=Decimal('400.00'),
            due_date=today - timedelta(days=10),
        )
        self.create_invoice(
            self.sub1,
            status='VOID',
            total_amount=Decimal('500.00'),
            amount_paid=Decimal('0.00'),
            due_date=today - timedelta(days=10),
        )

        response = self.client.get(reverse('dashboard:index'))
        self.assertEqual(response.context['overdue_count'], 0)
        self.assertEqual(response.context['overdue_balance'], Decimal('0.00'))
        self.assertEqual(len(response.context['overdue_invoices']), 0)


class DashboardCustomerViewTests(DashboardBaseTestCase):
    def test_customer_can_access_own_dashboard(self):
        """Customer can access their dashboard with is_staff_view=False."""
        self.client.login(username='cust1', password='custpass123')
        response = self.client.get(reverse('dashboard:index'))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context['is_staff_view'])
        expected_keys = [
            'total_paid',
            'outstanding',
            'total_invoices',
            'active_subscriptions',
            'recent_invoices',
            'recent_payments',
        ]
        for key in expected_keys:
            self.assertIn(key, response.context)

    def test_customer_sees_only_own_invoices_and_financial_totals(self):
        """Customer dashboard metrics reflect only that customer's invoices and completed payments."""
        inv = self.create_invoice(
            self.sub1,
            status='PARTIALLY_PAID',
            total_amount=Decimal('1000.00'),
            amount_paid=Decimal('400.00'),
        )
        self.create_payment(inv, amount=Decimal('400.00'), status='COMPLETED')

        self.client.login(username='cust1', password='custpass123')
        response = self.client.get(reverse('dashboard:index'))
        self.assertEqual(response.context['total_paid'], Decimal('400.00'))
        self.assertEqual(response.context['outstanding'], Decimal('600.00'))
        self.assertEqual(response.context['total_invoices'], 1)
        self.assertIn(inv, response.context['recent_invoices'])

    def test_customer1_cannot_see_customer2_invoice_or_payment_info(self):
        """Customer 1 cannot see Customer 2's invoices, payments, or totals."""
        inv1 = self.create_invoice(
            self.sub1,
            status='PARTIALLY_PAID',
            total_amount=Decimal('1000.00'),
            amount_paid=Decimal('400.00'),
        )
        pmt1 = self.create_payment(inv1, amount=Decimal('400.00'), status='COMPLETED')

        inv2 = self.create_invoice(
            self.sub2,
            status='PARTIALLY_PAID',
            total_amount=Decimal('2000.00'),
            amount_paid=Decimal('1500.00'),
        )
        pmt2 = self.create_payment(inv2, amount=Decimal('1500.00'), status='COMPLETED')

        self.client.login(username='cust1', password='custpass123')
        response = self.client.get(reverse('dashboard:index'))

        # Financial totals must strictly belong to Customer 1
        self.assertEqual(response.context['total_paid'], Decimal('400.00'))
        self.assertEqual(response.context['outstanding'], Decimal('600.00'))

        # Lists must contain only Customer 1's items
        self.assertIn(inv1, response.context['recent_invoices'])
        self.assertNotIn(inv2, response.context['recent_invoices'])
        self.assertIn(pmt1, response.context['recent_payments'])
        self.assertNotIn(pmt2, response.context['recent_payments'])

        # HTML response must not leak Customer 2's data
        self.assertContains(response, inv1.invoice_number)
        self.assertNotContains(response, inv2.invoice_number)
        self.assertNotContains(response, self.cust2.company_name)

    def test_customer_dashboard_does_not_expose_staff_wide_revenue_metrics(self):
        """Customer dashboard does not include staff-only context keys or staff chart markup."""
        self.client.login(username='cust1', password='custpass123')
        response = self.client.get(reverse('dashboard:index'))
        self.assertFalse(response.context['is_staff_view'])

        staff_only_keys = [
            'total_revenue',
            'total_outstanding',
            'overdue_count',
            'overdue_balance',
            'overdue_invoices',
            'monthly_revenue',
            'upcoming_renewals',
        ]
        for key in staff_only_keys:
            self.assertNotIn(key, response.context)

        # HTML must not render staff cards or charts
        self.assertNotContains(response, 'Total Revenue Collected')
        self.assertNotContains(response, 'revenueChart')
        self.assertNotContains(response, 'subChart')

    def test_user_without_customer_profile_handles_gracefully(self):
        """Authenticated user without a customer profile loads safely without errors."""
        User.objects.create_user(
            username='plain_user',
            email='plain@example.com',
            password='plainpass123',
        )
        self.client.login(username='plain_user', password='plainpass123')
        response = self.client.get(reverse('dashboard:index'))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context['is_staff_view'])
