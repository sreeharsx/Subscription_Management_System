from datetime import date, timedelta
from decimal import Decimal
from dateutil.relativedelta import relativedelta
from django.test import TestCase
from django.core.exceptions import ValidationError
from django.contrib.auth.models import User
from accounts.models import CustomerProfile
from products.models import Product, SubscriptionPlan, TaxConfiguration
from quotations.models import Quotation
from subscriptions.models import Subscription
from subscriptions.services import renew_subscription, get_next_billing_date
from billing.services import generate_invoice_for_subscription
from billing.models import Invoice


class SubscriptionModelAndRenewalServiceTests(TestCase):
    def setUp(self):
        # Users & Customer
        self.staff_user = User.objects.create_user(
            username='staff_test',
            email='staff@brightloop.com',
            password='StaffPassword123!',
            is_staff=True
        )
        self.cust_user = User.objects.create_user(
            username='customer_test',
            email='customer@example.com',
            password='Password123!'
        )
        self.cust_profile = CustomerProfile.objects.create(
            user=self.cust_user,
            company_name='Nexus Technologies'
        )

        # Products & Plans
        self.product = Product.objects.create(name='Nexus CRM')
        self.plan_monthly = SubscriptionPlan.objects.create(
            product=self.product,
            name='Pro Monthly Plan',
            billing_cycle='MONTHLY',
            base_price=Decimal('1000.00'),
            is_active=True
        )
        self.plan_quarterly = SubscriptionPlan.objects.create(
            product=self.product,
            name='Pro Quarterly Plan',
            billing_cycle='QUARTERLY',
            base_price=Decimal('2800.00'),
            is_active=True
        )
        self.plan_annual = SubscriptionPlan.objects.create(
            product=self.product,
            name='Pro Annual Plan',
            billing_cycle='ANNUALLY',
            base_price=Decimal('10000.00'),
            is_active=True
        )

        # Tax
        self.tax_18 = TaxConfiguration.objects.create(name='GST 18%', rate=Decimal('18.00'), is_active=True)

        # Quotation
        self.quotation = Quotation.objects.create(
            customer=self.cust_profile,
            plan=self.plan_monthly,
            tax=self.tax_18,
            status='ACCEPTED',
            base_price=Decimal('1000.00'),
            discount_amount=Decimal('100.00'),
            tax_amount=Decimal('162.00'),
            total_amount=Decimal('1062.00'),
            created_by=self.staff_user
        )

    def _create_subscription(self, status='EXPIRED', end_date=None, plan=None):
        target_plan = plan or self.plan_monthly
        return Subscription.objects.create(
            quotation=self.quotation,
            customer=self.cust_profile,
            plan=target_plan,
            status=status,
            billing_cycle=target_plan.billing_cycle,
            plan_price=self.quotation.base_price,
            discount_amount=self.quotation.discount_amount,
            tax_rate=Decimal('18.00'),
            start_date=date.today() - timedelta(days=60),
            end_date=end_date,
            next_billing_date=date.today() - timedelta(days=30),
        )

    # --- Model Validation Tests ---
    def test_clean_rejects_end_date_before_start_date(self):
        sub = Subscription(
            quotation=self.quotation,
            customer=self.cust_profile,
            plan=self.plan_monthly,
            status='ACTIVE',
            billing_cycle='MONTHLY',
            plan_price=Decimal('1000.00'),
            start_date=date(2026, 10, 15),
            end_date=date(2026, 10, 10),  # Earlier than start_date
            next_billing_date=date(2026, 10, 15),
        )
        with self.assertRaises(ValidationError) as ctx:
            sub.clean()
        self.assertIn('end_date', ctx.exception.message_dict)

    def test_clean_rejects_next_billing_date_before_start_date(self):
        sub = Subscription(
            quotation=self.quotation,
            customer=self.cust_profile,
            plan=self.plan_monthly,
            status='ACTIVE',
            billing_cycle='MONTHLY',
            plan_price=Decimal('1000.00'),
            start_date=date(2026, 10, 15),
            next_billing_date=date(2026, 10, 1),  # Earlier than start_date
        )
        with self.assertRaises(ValidationError) as ctx:
            sub.clean()
        self.assertIn('next_billing_date', ctx.exception.message_dict)

    def test_clean_passes_valid_dates(self):
        sub = Subscription(
            quotation=self.quotation,
            customer=self.cust_profile,
            plan=self.plan_monthly,
            status='ACTIVE',
            billing_cycle='MONTHLY',
            plan_price=Decimal('1000.00'),
            start_date=date(2026, 10, 15),
            end_date=date(2026, 11, 15),
            next_billing_date=date(2026, 10, 15),
        )
        sub.clean()

    # --- can_renew and Transition Control Tests ---
    def test_can_renew_returns_true_only_for_expired(self):
        sub = self._create_subscription(status='EXPIRED')
        self.assertTrue(sub.can_renew)

        sub.status = 'ACTIVE'
        self.assertFalse(sub.can_renew)

        sub.status = 'PAUSED'
        self.assertFalse(sub.can_renew)

        sub.status = 'CANCELLED'
        self.assertFalse(sub.can_renew)

    def test_generic_transition_from_expired_to_active_remains_blocked(self):
        sub = self._create_subscription(status='EXPIRED')
        self.assertFalse(sub.can_transition_to('ACTIVE'))
        self.assertEqual(sub.VALID_TRANSITIONS.get('EXPIRED'), [])

    # --- Renewal Service Tests ---
    def test_renew_reactivates_expired_subscription(self):
        sub = self._create_subscription(status='EXPIRED')
        original_pk = sub.pk

        renewed = renew_subscription(sub)
        self.assertEqual(renewed.pk, original_pk)
        self.assertEqual(renewed.status, 'ACTIVE')
        self.assertEqual(renewed.customer, self.cust_profile)
        self.assertEqual(renewed.quotation, self.quotation)
        self.assertEqual(renewed.plan, self.plan_monthly)

    def test_renew_preserves_pricing_snapshots_even_if_catalogue_changed(self):
        sub = self._create_subscription(status='EXPIRED')
        orig_price = sub.plan_price
        orig_discount = sub.discount_amount
        orig_tax = sub.tax_rate

        # Change catalogue plan price
        self.plan_monthly.base_price = Decimal('9999.00')
        self.plan_monthly.save()

        renewed = renew_subscription(sub)
        self.assertEqual(renewed.plan_price, orig_price)
        self.assertEqual(renewed.discount_amount, orig_discount)
        self.assertEqual(renewed.tax_rate, orig_tax)

    def test_renew_rejects_non_expired_subscription(self):
        sub = self._create_subscription(status='ACTIVE')
        with self.assertRaises(ValueError) as ctx:
            renew_subscription(sub)
        self.assertIn("Only EXPIRED subscriptions can be renewed", str(ctx.exception))

    def test_renew_preserves_invoice_history_and_does_not_create_new_records(self):
        sub = self._create_subscription(status='EXPIRED')
        inv = Invoice.objects.create(
            subscription=sub,
            invoice_number=f"INV-{sub.pk:05d}-2026-08",
            billing_period_key="2026-08",
            status='PAID',
            base_amount=Decimal('1000.00'),
            discount_amount=Decimal('0.00'),
            tax_amount=Decimal('180.00'),
            total_amount=Decimal('1180.00'),
            issue_date=date(2026, 8, 1),
            due_date=date(2026, 8, 16)
        )

        initial_sub_count = Subscription.objects.count()
        initial_quotation_count = Quotation.objects.count()
        initial_invoice_count = Invoice.objects.count()

        renew_subscription(sub)

        # 1. Assert invoice count remains unchanged immediately after renewal
        self.assertEqual(Invoice.objects.count(), initial_invoice_count)
        self.assertEqual(sub.invoices.count(), 1)
        # 2. Assert previous invoice remains linked to the exact same subscription
        self.assertEqual(sub.invoices.first().pk, inv.pk)
        # 3. Assert no extra subscription or quotation created
        self.assertEqual(Subscription.objects.count(), initial_sub_count)
        self.assertEqual(Quotation.objects.count(), initial_quotation_count)

    def test_renew_keeps_end_date_null_when_originally_null(self):
        sub = self._create_subscription(status='EXPIRED', end_date=None)
        renewed = renew_subscription(sub)
        self.assertIsNone(renewed.end_date)

    # --- End-Date Extension Exact Calculation Tests (Monthly, Quarterly, Annual) ---
    def test_renew_extends_end_date_monthly_exact_calculation(self):
        past_end = date.today() - timedelta(days=10)
        sub = self._create_subscription(status='EXPIRED', end_date=past_end, plan=self.plan_monthly)

        renewed = renew_subscription(sub)
        expected_end = max(date.today(), past_end) + relativedelta(months=1)
        self.assertEqual(renewed.end_date, expected_end)

    def test_renew_extends_end_date_quarterly_exact_calculation(self):
        q_quotation = Quotation.objects.create(
            customer=self.cust_profile,
            plan=self.plan_quarterly,
            status='ACCEPTED',
            base_price=Decimal('2800.00'),
            total_amount=Decimal('2800.00'),
            created_by=self.staff_user
        )
        past_end = date.today() - timedelta(days=15)
        sub = Subscription.objects.create(
            quotation=q_quotation,
            customer=self.cust_profile,
            plan=self.plan_quarterly,
            status='EXPIRED',
            billing_cycle='QUARTERLY',
            plan_price=Decimal('2800.00'),
            start_date=date.today() - timedelta(days=120),
            end_date=past_end,
            next_billing_date=date.today() - timedelta(days=30),
        )

        renewed = renew_subscription(sub)
        expected_end = max(date.today(), past_end) + relativedelta(months=3)
        self.assertEqual(renewed.end_date, expected_end)

    def test_renew_extends_end_date_annual_exact_calculation(self):
        a_quotation = Quotation.objects.create(
            customer=self.cust_profile,
            plan=self.plan_annual,
            status='ACCEPTED',
            base_price=Decimal('10000.00'),
            total_amount=Decimal('10000.00'),
            created_by=self.staff_user
        )
        past_end = date.today() - timedelta(days=5)
        sub = Subscription.objects.create(
            quotation=a_quotation,
            customer=self.cust_profile,
            plan=self.plan_annual,
            status='EXPIRED',
            billing_cycle='ANNUALLY',
            plan_price=Decimal('10000.00'),
            start_date=date.today() - timedelta(days=370),
            end_date=past_end,
            next_billing_date=date.today() - timedelta(days=30),
        )

        renewed = renew_subscription(sub)
        expected_end = max(date.today(), past_end) + relativedelta(months=12)
        self.assertEqual(renewed.end_date, expected_end)

    # --- Billing Date Exact Calculations for Monthly, Quarterly, and Annual ---
    def test_billing_date_monthly_unbilled_and_already_billed(self):
        sub = self._create_subscription(status='EXPIRED', plan=self.plan_monthly)
        today = date.today()
        current_period = today.strftime('%Y-%m')

        # 1. Unbilled for current month -> next_billing_date is today
        renew_subscription(sub)
        self.assertEqual(sub.next_billing_date, today)

        # 2. Generate invoice for current period
        inv, created = generate_invoice_for_subscription(sub, billing_date=today)
        self.assertTrue(created)
        self.assertEqual(inv.billing_period_key, current_period)

        # Re-expire to simulate renewal while already billed in current month
        sub.status = 'EXPIRED'
        sub.save()

        # 3. Renewed when invoice exists for current month -> advances by 1 month
        renew_subscription(sub)
        expected_next = today + relativedelta(months=1)
        self.assertEqual(sub.next_billing_date, expected_next)

        # 4. Verify no duplicate invoice is generated for the current period
        dup_inv, dup_created = generate_invoice_for_subscription(sub, billing_date=today)
        self.assertFalse(dup_created)
        self.assertEqual(dup_inv.pk, inv.pk)

    def test_billing_date_quarterly_unbilled_and_already_billed(self):
        q_quotation = Quotation.objects.create(
            customer=self.cust_profile,
            plan=self.plan_quarterly,
            status='ACCEPTED',
            base_price=Decimal('2800.00'),
            total_amount=Decimal('2800.00'),
            created_by=self.staff_user
        )
        sub = Subscription.objects.create(
            quotation=q_quotation,
            customer=self.cust_profile,
            plan=self.plan_quarterly,
            status='EXPIRED',
            billing_cycle='QUARTERLY',
            plan_price=Decimal('2800.00'),
            start_date=date.today() - timedelta(days=120),
            next_billing_date=date.today() - timedelta(days=90),
        )
        today = date.today()

        # 1. Unbilled -> next_billing_date is today
        renew_subscription(sub)
        self.assertEqual(sub.next_billing_date, today)

        # 2. Bill for current month
        inv, created = generate_invoice_for_subscription(sub, billing_date=today)
        self.assertTrue(created)

        # 3. Renew again when already billed -> advances by 3 months
        sub.status = 'EXPIRED'
        sub.save()
        renew_subscription(sub)
        expected_next = today + relativedelta(months=3)
        self.assertEqual(sub.next_billing_date, expected_next)

    def test_billing_date_annual_unbilled_and_already_billed(self):
        a_quotation = Quotation.objects.create(
            customer=self.cust_profile,
            plan=self.plan_annual,
            status='ACCEPTED',
            base_price=Decimal('10000.00'),
            total_amount=Decimal('10000.00'),
            created_by=self.staff_user
        )
        sub = Subscription.objects.create(
            quotation=a_quotation,
            customer=self.cust_profile,
            plan=self.plan_annual,
            status='EXPIRED',
            billing_cycle='ANNUALLY',
            plan_price=Decimal('10000.00'),
            start_date=date.today() - timedelta(days=370),
            next_billing_date=date.today() - timedelta(days=30),
        )
        today = date.today()

        # 1. Unbilled -> next_billing_date is today
        renew_subscription(sub)
        self.assertEqual(sub.next_billing_date, today)

        # 2. Bill for current month
        inv, created = generate_invoice_for_subscription(sub, billing_date=today)
        self.assertTrue(created)

        # 3. Renew again when already billed -> advances by 12 months
        sub.status = 'EXPIRED'
        sub.save()
        renew_subscription(sub)
        expected_next = today + relativedelta(months=12)
        self.assertEqual(sub.next_billing_date, expected_next)

    # --- Failure Safety & State Preservation Tests ---
    def test_failed_renewal_leaves_database_state_and_records_unchanged(self):
        orig_start = date.today() - timedelta(days=40)
        orig_end = date.today() - timedelta(days=10)
        orig_next = date.today() - timedelta(days=10)

        sub = Subscription.objects.create(
            quotation=self.quotation,
            customer=self.cust_profile,
            plan=self.plan_monthly,
            status='ACTIVE',  # NOT EXPIRED -> invalid for renewal
            billing_cycle='MONTHLY',
            plan_price=Decimal('1000.00'),
            start_date=orig_start,
            end_date=orig_end,
            next_billing_date=orig_next,
        )

        initial_sub_count = Subscription.objects.count()
        initial_quotation_count = Quotation.objects.count()
        initial_invoice_count = Invoice.objects.count()

        # Attempt renewal on active subscription
        with self.assertRaises(ValueError):
            renew_subscription(sub)

        # Confirm database state was NOT modified
        sub.refresh_from_db()
        self.assertEqual(sub.status, 'ACTIVE')
        self.assertEqual(sub.start_date, orig_start)
        self.assertEqual(sub.end_date, orig_end)
        self.assertEqual(sub.next_billing_date, orig_next)

        # Confirm no extra records created
        self.assertEqual(Subscription.objects.count(), initial_sub_count)
        self.assertEqual(Quotation.objects.count(), initial_quotation_count)
        self.assertEqual(Invoice.objects.count(), initial_invoice_count)

    # --- Duplicate Renewal Test & SQLite Concurrency Documentation ---
    def test_duplicate_renewal_conflict_prevented_sequentially(self):
        """
        Verify sequential duplicate-renewal prevention.
        Note: Simultaneous thread-based concurrency testing on SQLite is notoriously flaky
        due to SQLite's coarse database locking and lack of true row-level locks in memory/file mode.
        True concurrency safety in production relies on database engine transaction isolation
        (such as PostgreSQL row-level locks or the atomic compare-and-set query in renew_subscription).
        """
        sub = self._create_subscription(status='EXPIRED')

        # First renewal succeeds
        renew_subscription(sub)
        self.assertEqual(sub.status, 'ACTIVE')

        # Second renewal attempt immediately fails with ValueError
        with self.assertRaises(ValueError) as ctx:
            renew_subscription(sub)
        self.assertIn("Only EXPIRED subscriptions can be renewed", str(ctx.exception))
