from decimal import Decimal
from django.test import TestCase, Client
from django.contrib.auth.models import User
from accounts.models import CustomerProfile
from products.models import Product, SubscriptionPlan, TaxConfiguration, DiscountConfiguration
from quotations.models import Quotation
from subscriptions.models import Subscription
from subscriptions.services import create_subscription_from_quotation


class SubscriptionsLifecycleTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('cust_sub', 'sub@example.com', 'pass123')
        self.customer = CustomerProfile.objects.create(user=self.user, company_name="Sub Corp")

        self.product = Product.objects.create(name="Product S")
        self.plan = SubscriptionPlan.objects.create(
            product=self.product,
            name="Plan S",
            billing_cycle="MONTHLY",
            base_price=Decimal("1500.00")
        )
        self.tax = TaxConfiguration.objects.create(name="GST 18%", rate=Decimal("18.00"))
        self.discount = DiscountConfiguration.objects.create(
            name="Flat 100", code="FL100", discount_type="FIXED", value=Decimal("100.00")
        )

        self.quotation = Quotation.objects.create(
            customer=self.customer,
            plan=self.plan,
            tax=self.tax,
            discount=self.discount,
            status='ACCEPTED'
        )

    def test_subscription_creation_from_accepted_quotation(self):
        """Converting accepted quotation creates active subscription with snapshot pricing."""
        sub = create_subscription_from_quotation(self.quotation)
        self.assertEqual(sub.status, 'ACTIVE')
        self.assertEqual(sub.plan_price, Decimal("1500.00"))
        self.assertEqual(sub.discount_amount, Decimal("100.00"))
        self.assertEqual(sub.tax_rate, Decimal("18.00"))

    def test_single_subscription_per_quotation_guard(self):
        """Cannot create two subscriptions for the same quotation."""
        create_subscription_from_quotation(self.quotation)
        with self.assertRaises(Exception):
            create_subscription_from_quotation(self.quotation)

    def test_state_machine_valid_and_invalid_transitions(self):
        """
        Valid: ACTIVE -> PAUSED -> ACTIVE -> CANCELLED
        Invalid: CANCELLED -> ACTIVE
        """
        sub = create_subscription_from_quotation(self.quotation)

        self.assertTrue(sub.can_transition_to('PAUSED'))
        sub.status = 'PAUSED'
        sub.save()

        self.assertTrue(sub.can_transition_to('ACTIVE'))
        sub.status = 'ACTIVE'
        sub.save()

        self.assertTrue(sub.can_transition_to('CANCELLED'))
        sub.status = 'CANCELLED'
        sub.save()

        # Cannot reactivate a cancelled subscription
        self.assertFalse(sub.can_transition_to('ACTIVE'))

    def test_catalogue_price_change_does_not_affect_existing_subscription(self):
        """Changing the plan price in catalogue does NOT alter the subscription's plan_price."""
        sub = create_subscription_from_quotation(self.quotation)
        self.assertEqual(sub.plan_price, Decimal("1500.00"))

        # Update catalogue price to 2500
        self.plan.base_price = Decimal("2500.00")
        self.plan.save()

        sub.refresh_from_db()
        self.assertEqual(sub.plan_price, Decimal("1500.00"))
