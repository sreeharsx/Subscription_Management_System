from decimal import Decimal
from datetime import date, timedelta
from io import StringIO

from django.core.management import call_command
from django.contrib.auth.models import User
from django.test import TestCase, Client
from django.utils import timezone
from accounts.models import CustomerProfile
from products.models import Product, SubscriptionPlan, TaxConfiguration, DiscountConfiguration
from quotations.models import Quotation
from subscriptions.models import Subscription
from subscriptions.services import create_subscription_from_quotation
from billing.models import Invoice, Payment
from billing.services import (
    generate_invoice_for_subscription,
    record_payment,
    run_billing_for_all_active_subscriptions,
)


class CompleteWorkflowTestCase(TestCase):
    def setUp(self):
        # Create users: admin, staff, and two customers (customer1, customer2)
        self.admin_user = User.objects.create_superuser('admin', 'admin@brightloop.com', 'adminpass123')
        self.staff_user = User.objects.create_user('staff', 'staff@brightloop.com', 'staffpass123', is_staff=True)
        
        self.user1 = User.objects.create_user('cust1', 'cust1@example.com', 'custpass123')
        self.cust1 = CustomerProfile.objects.create(
            user=self.user1, company_name="Acme Corp", phone="9876543210", gst_number="GSTIN0123"
        )

        self.user2 = User.objects.create_user('cust2', 'cust2@example.com', 'custpass123')
        self.cust2 = CustomerProfile.objects.create(
            user=self.user2, company_name="Beta Ltd", phone="9123456780"
        )

        # Products & Plans
        self.product = Product.objects.create(name="BrightCloud", description="Cloud SaaS Suite")
        self.plan = SubscriptionPlan.objects.create(
            product=self.product,
            name="Pro Monthly",
            billing_cycle="MONTHLY",
            base_price=Decimal("1000.00")
        )

        # Tax: 18% GST
        self.tax = TaxConfiguration.objects.create(name="GST 18%", rate=Decimal("18.00"))

        # Discount: 10%
        self.discount = DiscountConfiguration.objects.create(
            name="Early Bird 10%",
            code="EARLY10",
            discount_type="PERCENTAGE",
            value=Decimal("10.00")
        )

    def test_financial_calculation_order(self):
        """
        Rule: base price -> eligible discount -> applicable tax -> final invoice amount.
        Base: 1000.00
        Discount (10%): 100.00
        Taxable: 900.00
        Tax (18% on 900.00): 162.00
        Total: 1062.00
        """
        quotation = Quotation.objects.create(
            customer=self.cust1,
            plan=self.plan,
            tax=self.tax,
            discount=self.discount,
            status='DRAFT'
        )
        quotation.calculate_totals()
        quotation.save()

        self.assertEqual(quotation.base_price, Decimal("1000.00"))
        self.assertEqual(quotation.discount_amount, Decimal("100.00"))
        self.assertEqual(quotation.tax_amount, Decimal("162.00"))
        self.assertEqual(quotation.total_amount, Decimal("1062.00"))

    def test_quotation_acceptance_and_subscription_creation(self):
        """
        Quotation workflow: Draft -> Sent -> Accepted -> Subscription created.
        """
        quotation = Quotation.objects.create(
            customer=self.cust1,
            plan=self.plan,
            tax=self.tax,
            discount=self.discount,
            status='DRAFT'
        )
        quotation.calculate_totals()
        quotation.save()

        # Cannot accept Draft directly
        self.assertFalse(quotation.can_accept())

        # Move to Sent
        quotation.status = 'SENT'
        quotation.save()
        self.assertTrue(quotation.can_accept())

        # Accept quotation
        sub = create_subscription_from_quotation(quotation)
        self.assertEqual(sub.status, 'ACTIVE')
        self.assertEqual(sub.customer, self.cust1)
        self.assertEqual(sub.plan, self.plan)
        self.assertEqual(sub.plan_price, Decimal("1000.00"))
        self.assertEqual(sub.discount_amount, Decimal("100.00"))
        self.assertEqual(sub.tax_rate, Decimal("18.00"))

    def test_duplicate_subscription_prevention(self):
        """
        Cannot create two subscriptions for the same quotation (OneToOne constraint).
        """
        quotation = Quotation.objects.create(
            customer=self.cust1,
            plan=self.plan,
            tax=self.tax,
            discount=self.discount,
            status='ACCEPTED'
        )
        quotation.calculate_totals()
        quotation.save()

        sub1 = create_subscription_from_quotation(quotation)
        self.assertIsNotNone(sub1.pk)

        # Attempt to create another subscription from same quotation must fail
        with self.assertRaises(Exception):
            create_subscription_from_quotation(quotation)

    def test_subscription_lifecycle_state_machine(self):
        """
        Valid transitions:
        ACTIVE -> PAUSED -> ACTIVE -> CANCELLED
        Invalid:
        CANCELLED -> ACTIVE
        """
        quotation = Quotation.objects.create(
            customer=self.cust1,
            plan=self.plan,
            status='ACCEPTED'
        )
        quotation.calculate_totals()
        quotation.save()
        sub = create_subscription_from_quotation(quotation)

        # Active -> Paused
        self.assertTrue(sub.can_transition_to('PAUSED'))
        sub.status = 'PAUSED'
        sub.save()

        # Paused -> Active
        self.assertTrue(sub.can_transition_to('ACTIVE'))
        sub.status = 'ACTIVE'
        sub.save()

        # Active -> Cancelled
        self.assertTrue(sub.can_transition_to('CANCELLED'))
        sub.status = 'CANCELLED'
        sub.save()

        # Cancelled -> Active (MUST BE FORBIDDEN)
        self.assertFalse(sub.can_transition_to('ACTIVE'))

    def test_duplicate_invoice_prevention_billing_idempotency(self):
        """
        Running the billing process twice for the same subscription and period
        MUST NOT create duplicate invoices.
        Enforced by UNIQUE(subscription, billing_period_key).
        """
        quotation = Quotation.objects.create(
            customer=self.cust1,
            plan=self.plan,
            tax=self.tax,
            discount=self.discount,
            status='ACCEPTED'
        )
        quotation.calculate_totals()
        quotation.save()
        sub = create_subscription_from_quotation(quotation)

        today = date(2026, 10, 31)
        invoice1, created1 = generate_invoice_for_subscription(sub, billing_date=today)
        self.assertTrue(created1)
        self.assertEqual(invoice1.total_amount, Decimal("1062.00"))
        self.assertEqual(invoice1.billing_period_key, "2026-10")

        # Second run for the SAME period
        invoice2, created2 = generate_invoice_for_subscription(sub, billing_date=today)
        self.assertFalse(created2)
        self.assertEqual(invoice1.pk, invoice2.pk)
        self.assertEqual(Invoice.objects.filter(subscription=sub).count(), 1)

    def test_payment_and_outstanding_balance_tracking(self):
        """
        Invoice ₹1062.
        Partial payment ₹500 -> outstanding ₹562, status PARTIALLY_PAID.
        Final payment ₹562 -> outstanding ₹0, status PAID.
        Overpayment of ₹1 -> rejected.
        """
        quotation = Quotation.objects.create(
            customer=self.cust1,
            plan=self.plan,
            tax=self.tax,
            discount=self.discount,
            status='ACCEPTED'
        )
        quotation.calculate_totals()
        quotation.save()
        sub = create_subscription_from_quotation(quotation)
        invoice, _ = generate_invoice_for_subscription(sub, billing_date=date(2026, 10, 31))

        self.assertEqual(invoice.outstanding_balance, Decimal("1062.00"))
        self.assertEqual(invoice.status, "ISSUED")

        # 1. Partial payment: ₹500
        p1 = record_payment(
            invoice=invoice,
            amount=Decimal("500.00"),
            payment_method="BANK_TRANSFER",
            payment_date=date(2026, 10, 31),
            recorded_by=self.staff_user
        )
        invoice.refresh_from_db()
        self.assertEqual(invoice.amount_paid, Decimal("500.00"))
        self.assertEqual(invoice.outstanding_balance, Decimal("562.00"))
        self.assertEqual(invoice.status, "PARTIALLY_PAID")

        # 2. Overpayment attempt: ₹600 (exceeds ₹562)
        with self.assertRaises(ValueError):
            record_payment(
                invoice=invoice,
                amount=Decimal("600.00"),
                payment_method="UPI",
                payment_date=date(2026, 10, 31),
                recorded_by=self.staff_user
            )

        # 3. Final payment: ₹562
        p2 = record_payment(
            invoice=invoice,
            amount=Decimal("562.00"),
            payment_method="UPI",
            payment_date=date(2026, 10, 31),
            recorded_by=self.staff_user
        )
        invoice.refresh_from_db()
        self.assertEqual(invoice.amount_paid, Decimal("1062.00"))
        self.assertEqual(invoice.outstanding_balance, Decimal("0.00"))
        self.assertEqual(invoice.status, "PAID")
        self.assertIsNotNone(invoice.paid_date)

    def test_customer_data_isolation_role_based_access(self):
        """
        Customer 1 must not be able to access Customer 2's quotation or invoice.
        Server returns 403 Forbidden.
        """
        client = Client()

        # Customer 2 creates a quotation & invoice
        q2 = Quotation.objects.create(
            customer=self.cust2,
            plan=self.plan,
            status='SENT'
        )
        q2.calculate_totals()
        q2.save()
        sub2 = create_subscription_from_quotation(q2)
        inv2, _ = generate_invoice_for_subscription(sub2, billing_date=date(2026, 10, 31))

        # Log in as Customer 1
        client.login(username='cust1', password='custpass123')

        # Cust 1 tries to access Cust 2's quotation detail
        response = client.get(f'/quotations/{q2.pk}/')
        self.assertEqual(response.status_code, 403)

        # Cust 1 tries to access Cust 2's subscription detail
        response = client.get(f'/subscriptions/{sub2.pk}/')
        self.assertEqual(response.status_code, 403)

        # Cust 1 tries to access Cust 2's invoice detail
        response = client.get(f'/billing/invoices/{inv2.pk}/')
        self.assertEqual(response.status_code, 403)

        # Staff can access Cust 2's invoice
        client.login(username='staff', password='staffpass123')
        response = client.get(f'/billing/invoices/{inv2.pk}/')
        self.assertEqual(response.status_code, 200)

    def test_dashboard_collected_revenue_vs_invoiced_amounts(self):
        """
        Rule: Collected revenue must reflect RECORDED PAYMENTS, not merely issued invoices.
        """
        client = Client()
        client.login(username='staff', password='staffpass123')

        quotation = Quotation.objects.create(
            customer=self.cust1,
            plan=self.plan,
            tax=self.tax,
            discount=self.discount,
            status='ACCEPTED'
        )
        quotation.calculate_totals()
        quotation.save()
        sub = create_subscription_from_quotation(quotation)
        invoice, _ = generate_invoice_for_subscription(sub, billing_date=date(2026, 10, 31))

        # Invoice issued for ₹1062, but ₹0 paid yet
        response = client.get('/dashboard/')
        self.assertEqual(response.context['total_revenue'], Decimal('0.00'))
        self.assertEqual(response.context['total_outstanding'], Decimal('1062.00'))

        # Pay ₹400
        record_payment(invoice, Decimal("400.00"), "CASH", date(2026, 10, 31), self.staff_user)

        response = client.get('/dashboard/')
        self.assertEqual(response.context['total_revenue'], Decimal('400.00'))
        self.assertEqual(response.context['total_outstanding'], Decimal('662.00'))

    def test_record_payment_view_rendering_and_submission(self):
        """
        Test that /billing/invoices/<pk>/pay/ loads record_payment.html with 200 OK,
        displays invoice details, and processes payment submission.
        """
        client = Client()
        client.login(username='staff', password='staffpass123')

        quotation = Quotation.objects.create(
            customer=self.cust1,
            plan=self.plan,
            tax=self.tax,
            discount=self.discount,
            status='ACCEPTED'
        )
        sub = create_subscription_from_quotation(quotation)
        invoice, _ = generate_invoice_for_subscription(sub, billing_date=date(2026, 10, 31))

        # 1. GET returns 200 and uses billing/record_payment.html
        response = client.get(f'/billing/invoices/{invoice.pk}/pay/')
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'billing/record_payment.html')
        self.assertContains(response, invoice.invoice_number)
        self.assertContains(response, 'Record Payment')

        # 2. POST valid payment
        post_data = {
            'amount': '500.00',
            'payment_method': 'BANK_TRANSFER',
            'payment_date': '2026-10-31',
            'reference_number': 'TXN123',
            'notes': 'Test payment',
        }
        post_res = client.post(f'/billing/invoices/{invoice.pk}/pay/', post_data)
        self.assertEqual(post_res.status_code, 302)
        self.assertEqual(post_res.url, f'/billing/invoices/{invoice.pk}/')

        invoice.refresh_from_db()
        self.assertEqual(invoice.amount_paid, Decimal('500.00'))
        self.assertEqual(invoice.status, 'PARTIALLY_PAID')

    def test_invoice_detail_can_pay_context_and_visibility(self):
        """
        Regression test for D1: Ensure can_pay is passed to invoice_detail
        and the 'Record Payment' button is rendered for staff, but not for regular customer.
        """
        quotation = Quotation.objects.create(
            customer=self.cust1,
            plan=self.plan,
            tax=self.tax,
            discount=self.discount,
            status='ACCEPTED'
        )
        sub = create_subscription_from_quotation(quotation)
        invoice, _ = generate_invoice_for_subscription(sub, billing_date=date(2026, 10, 31))

        # Staff user sees Record Payment button and can_pay=True
        client = Client()
        client.login(username='staff', password='staffpass123')
        res = client.get(f'/billing/invoices/{invoice.pk}/')
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.context['can_pay'])
        self.assertContains(res, 'Record Payment')

        # Customer user sees invoice detail but NOT Record Payment button
        client.login(username='cust1', password='custpass123')
        res_cust = client.get(f'/billing/invoices/{invoice.pk}/')
        self.assertEqual(res_cust.status_code, 200)
        self.assertFalse(res_cust.context['can_pay'])
        self.assertNotContains(res_cust, 'Record Payment')

    def test_payment_list_total_received_aggregation(self):
        """
        Regression test for D2: Ensure payment_list passes total_received
        aggregated across completed payments.
        """
        quotation = Quotation.objects.create(
            customer=self.cust1,
            plan=self.plan,
            tax=self.tax,
            discount=self.discount,
            status='ACCEPTED'
        )
        sub = create_subscription_from_quotation(quotation)
        invoice, _ = generate_invoice_for_subscription(sub, billing_date=date(2026, 10, 31))

        record_payment(
            invoice=invoice,
            amount=Decimal("300.00"),
            payment_method="UPI",
            payment_date=date(2026, 10, 31),
            recorded_by=self.staff_user
        )
        record_payment(
            invoice=invoice,
            amount=Decimal("200.00"),
            payment_method="CASH",
            payment_date=date(2026, 10, 31),
            recorded_by=self.staff_user
        )

        client = Client()
        client.login(username='staff', password='staffpass123')
        res = client.get('/billing/payments/')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.context['total_received'], Decimal('500.00'))
        self.assertContains(res, '500.00')


class UpdateOverdueInvoicesTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='overdue-test-user',
            password='testpass123',
        )
        self.customer = CustomerProfile.objects.create(
            user=self.user,
            company_name='Overdue Test Company',
        )
        self.product = Product.objects.create(
            name='Overdue Test Product',
            description='Product for overdue invoice tests',
        )
        self.plan = SubscriptionPlan.objects.create(
            product=self.product,
            name='Overdue Test Plan',
            billing_cycle='MONTHLY',
            base_price=Decimal('100.00'),
        )
        quotation = Quotation.objects.create(
            customer=self.customer,
            plan=self.plan,
            status='ACCEPTED',
        )
        quotation.calculate_totals()
        quotation.save()
        self.subscription = create_subscription_from_quotation(quotation)
        self.invoice_sequence = 0

    def create_invoice(self, status='ISSUED', amount_paid=Decimal('0.00'), due_date=None):
        self.invoice_sequence += 1
        if due_date is None:
            due_date = timezone.localdate() - timedelta(days=1)

        return Invoice.objects.create(
            subscription=self.subscription,
            invoice_number=f'TEST-OVERDUE-{self.invoice_sequence}',
            billing_period_key=f'test-overdue-{self.invoice_sequence}',
            status=status,
            base_amount=Decimal('100.00'),
            discount_amount=Decimal('0.00'),
            tax_amount=Decimal('0.00'),
            total_amount=Decimal('100.00'),
            amount_paid=amount_paid,
            issue_date=due_date - timedelta(days=15),
            due_date=due_date,
        )

    def run_command(self, *args):
        output = StringIO()
        call_command('update_overdue_invoices', *args, stdout=output)
        return output.getvalue()

    def test_past_due_issued_invoice_becomes_overdue(self):
        invoice = self.create_invoice()

        self.run_command()

        invoice.refresh_from_db()
        self.assertEqual(invoice.status, 'OVERDUE')

    def test_past_due_partially_paid_invoice_becomes_overdue(self):
        invoice = self.create_invoice(
            status='PARTIALLY_PAID',
            amount_paid=Decimal('40.00'),
        )

        self.run_command()

        invoice.refresh_from_db()
        self.assertEqual(invoice.status, 'OVERDUE')
        self.assertEqual(invoice.amount_paid, Decimal('40.00'))

    def test_fully_paid_invoice_does_not_become_overdue(self):
        invoice = self.create_invoice(
            status='PAID',
            amount_paid=Decimal('100.00'),
        )

        self.run_command()

        invoice.refresh_from_db()
        self.assertEqual(invoice.status, 'PAID')

    def test_void_invoice_remains_void(self):
        invoice = self.create_invoice(
            status='VOID',
            amount_paid=Decimal('100.00'),
        )

        self.run_command()

        invoice.refresh_from_db()
        self.assertEqual(invoice.status, 'VOID')

    def test_invoice_due_today_does_not_become_overdue(self):
        invoice = self.create_invoice(due_date=timezone.localdate())

        self.run_command()

        invoice.refresh_from_db()
        self.assertEqual(invoice.status, 'ISSUED')

    def test_future_due_invoice_does_not_become_overdue(self):
        invoice = self.create_invoice(
            due_date=timezone.localdate() + timedelta(days=1),
        )

        self.run_command()

        invoice.refresh_from_db()
        self.assertEqual(invoice.status, 'ISSUED')

    def test_already_overdue_invoice_remains_unchanged(self):
        invoice = self.create_invoice(status='OVERDUE')
        invoice_number = invoice.invoice_number

        output = self.run_command()

        invoice.refresh_from_db()
        self.assertEqual(invoice.status, 'OVERDUE')
        self.assertEqual(invoice.invoice_number, invoice_number)
        self.assertIn('already overdue: 1', output)

    def test_dry_run_does_not_save_changes(self):
        invoice = self.create_invoice()

        output = self.run_command('--dry-run')

        invoice.refresh_from_db()
        self.assertEqual(invoice.status, 'ISSUED')
        self.assertIn(invoice.invoice_number, output)
        self.assertIn('would be updated: 1', output)

    def test_repeated_runs_produce_consistent_results(self):
        invoice = self.create_invoice()
        initial_count = Invoice.objects.count()

        first_output = self.run_command()
        invoice.refresh_from_db()
        first_status = invoice.status
        first_count = Invoice.objects.count()

        second_output = self.run_command()
        invoice.refresh_from_db()

        self.assertEqual(first_status, 'OVERDUE')
        self.assertEqual(invoice.status, 'OVERDUE')
        self.assertEqual(initial_count, first_count)
        self.assertEqual(first_count, Invoice.objects.count())
        self.assertIn('updated: 1', first_output)
        self.assertIn('updated: 0', second_output)
        self.assertIn('already overdue: 1', second_output)
