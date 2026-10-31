from decimal import Decimal
from django.test import TestCase, Client
from django.contrib.auth.models import User
from accounts.models import CustomerProfile
from products.models import Product, SubscriptionPlan, TaxConfiguration, DiscountConfiguration
from quotations.models import Quotation


class QuotationsTestCase(TestCase):
    def setUp(self):
        self.client = Client()
        self.staff_user = User.objects.create_user('staff_qt', 'staff@example.com', 'pass123', is_staff=True)
        
        self.user1 = User.objects.create_user('cust_qt1', 'cust1@example.com', 'pass123')
        self.customer1 = CustomerProfile.objects.create(user=self.user1, company_name="Client A")
        
        self.user2 = User.objects.create_user('cust_qt2', 'cust2@example.com', 'pass123')
        self.customer2 = CustomerProfile.objects.create(user=self.user2, company_name="Client B")

        self.product = Product.objects.create(name="Analytics Pro")
        self.plan = SubscriptionPlan.objects.create(
            product=self.product,
            name="Monthly Plan",
            billing_cycle="MONTHLY",
            base_price=Decimal("2000.00")
        )
        self.tax = TaxConfiguration.objects.create(name="GST 18%", rate=Decimal("18.00"))
        self.discount = DiscountConfiguration.objects.create(
            name="10% Promo", code="P10", discount_type="PERCENTAGE", value=Decimal("10.00")
        )

    def test_quotation_calculation_order(self):
        """
        Base: 2000.00
        Discount (10%): 200.00
        Taxable: 1800.00
        Tax (18% on 1800.00): 324.00
        Total: 2124.00
        """
        quotation = Quotation(
            customer=self.customer1,
            plan=self.plan,
            tax=self.tax,
            discount=self.discount,
            status='DRAFT'
        )
        quotation.save()

        self.assertEqual(quotation.base_price, Decimal("2000.00"))
        self.assertEqual(quotation.discount_amount, Decimal("200.00"))
        self.assertEqual(quotation.tax_amount, Decimal("324.00"))
        self.assertEqual(quotation.total_amount, Decimal("2124.00"))

    def test_quotation_state_guards(self):
        """Draft can be sent, Sent can be accepted or rejected."""
        q = Quotation.objects.create(customer=self.customer1, plan=self.plan, status='DRAFT')
        self.assertTrue(q.can_send())
        self.assertFalse(q.can_accept())

        q.status = 'SENT'
        q.save()
        self.assertFalse(q.can_send())
        self.assertTrue(q.can_accept())
        self.assertTrue(q.can_reject())

        q.status = 'ACCEPTED'
        q.save()
        self.assertFalse(q.can_accept())
        self.assertFalse(q.can_reject())

    def test_quotation_customer_access_isolation(self):
        """Client B cannot view Client A's quotation via direct URL."""
        q = Quotation.objects.create(customer=self.customer1, plan=self.plan, status='SENT')

        self.client.login(username='cust_qt2', password='pass123')
        response = self.client.get(f'/quotations/{q.pk}/')
        self.assertEqual(response.status_code, 403)
