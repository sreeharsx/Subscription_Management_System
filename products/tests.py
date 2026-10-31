from decimal import Decimal
from django.test import TestCase
from products.models import Product, SubscriptionPlan, TaxConfiguration, DiscountConfiguration


class ProductsPricingTestCase(TestCase):
    def setUp(self):
        self.product = Product.objects.create(
            name="BrightCloud Suite",
            description="Enterprise Cloud System"
        )
        self.monthly_plan = SubscriptionPlan.objects.create(
            product=self.product,
            name="Monthly Starter",
            billing_cycle="MONTHLY",
            base_price=Decimal("1200.00")
        )
        self.annual_plan = SubscriptionPlan.objects.create(
            product=self.product,
            name="Annual Enterprise",
            billing_cycle="ANNUALLY",
            base_price=Decimal("12000.00")
        )
        self.tax_18 = TaxConfiguration.objects.create(
            name="GST 18%",
            rate=Decimal("18.00")
        )
        self.pct_discount = DiscountConfiguration.objects.create(
            name="10% Off",
            code="SAVE10",
            discount_type="PERCENTAGE",
            value=Decimal("10.00")
        )
        self.fixed_discount = DiscountConfiguration.objects.create(
            name="Flat 200 Off",
            code="FLAT200",
            discount_type="FIXED",
            value=Decimal("200.00")
        )

    def test_plan_cycle_months(self):
        """Verify cycle months calculation."""
        self.assertEqual(self.monthly_plan.get_cycle_months(), 1)
        self.assertEqual(self.annual_plan.get_cycle_months(), 12)

    def test_percentage_discount_calculation(self):
        """10% of 1200.00 should be 120.00."""
        calc = self.pct_discount.calculate_discount(Decimal("1200.00"))
        self.assertEqual(calc, Decimal("120.00"))

    def test_fixed_discount_calculation(self):
        """Flat 200 discount on 1200.00 should be 200.00."""
        calc = self.fixed_discount.calculate_discount(Decimal("1200.00"))
        self.assertEqual(calc, Decimal("200.00"))

    def test_fixed_discount_capped_at_base_price(self):
        """Fixed discount of 200 on base price of 150 should be capped at 150.00."""
        calc = self.fixed_discount.calculate_discount(Decimal("150.00"))
        self.assertEqual(calc, Decimal("150.00"))
