from decimal import Decimal
from datetime import date, timedelta
from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from accounts.models import CustomerProfile
from products.models import Product, SubscriptionPlan, TaxConfiguration, DiscountConfiguration
from quotations.models import Quotation
from quotations.forms import QuotationForm
from subscriptions.models import Subscription


class QuotationPricingAndSnapshotImmutabilityTests(TestCase):
    def setUp(self):
        self.client = Client()

        # Staff user
        self.staff_user = User.objects.create_user(
            username='staff_sales',
            email='sales@brightloop.com',
            password='StaffPassword123!',
            is_staff=True
        )

        # Customer
        self.cust_user = User.objects.create_user(
            username='acme_user',
            email='acme@example.com',
            password='Password123!'
        )
        self.cust_profile = CustomerProfile.objects.create(
            user=self.cust_user,
            company_name='Acme Corporation'
        )

        # Products & Plans
        self.product = Product.objects.create(name='Cloud Suite')
        self.plan1 = SubscriptionPlan.objects.create(
            product=self.product,
            name='Pro Monthly',
            billing_cycle='MONTHLY',
            base_price=Decimal('1000.00'),
            is_active=True
        )
        self.plan2 = SubscriptionPlan.objects.create(
            product=self.product,
            name='Enterprise Monthly',
            billing_cycle='MONTHLY',
            base_price=Decimal('2000.00'),
            is_active=True
        )

        # Taxes
        self.tax_18 = TaxConfiguration.objects.create(name='GST 18%', rate=Decimal('18.00'), is_active=True)
        self.tax_5 = TaxConfiguration.objects.create(name='GST 5%', rate=Decimal('5.00'), is_active=True)

        # Discounts
        self.disc_10 = DiscountConfiguration.objects.create(
            name='Promo 10%',
            code='PROMO10',
            discount_type='PERCENTAGE',
            value=Decimal('10.00'),
            is_active=True
        )
        self.disc_fixed_200 = DiscountConfiguration.objects.create(
            name='Flat 200',
            code='FLAT200',
            discount_type='FIXED',
            value=Decimal('200.00'),
            is_active=True
        )

        self.client.login(username='staff_sales', password='StaffPassword123!')

    def _create_initial_quotation(self):
        """Helper: create and price an initial draft quotation."""
        q = Quotation.objects.create(
            customer=self.cust_profile,
            plan=self.plan1,
            tax=self.tax_18,
            discount=self.disc_10,
            status='DRAFT',
            notes='Initial notes',
            valid_until=date.today() + timedelta(days=7),
            created_by=self.staff_user
        )
        q.calculate_totals()
        q.save()
        return q

    def test_initial_calculation_order(self):
        """Quotation calculation order: base -> discount -> tax on taxable -> final total."""
        q = self._create_initial_quotation()
        self.assertEqual(q.base_price, Decimal('1000.00'))
        self.assertEqual(q.discount_amount, Decimal('100.00'))  # 10% of 1000
        self.assertEqual(q.tax_amount, Decimal('162.00'))       # 18% of 900
        self.assertEqual(q.total_amount, Decimal('1062.00'))    # 900 + 162

    def test_changing_plan_recalculates_all_pricing_snapshots(self):
        """Changing the plan re-evaluates base_price and recalculates all snapshot amounts."""
        q = self._create_initial_quotation()
        url = reverse('quotations:quotation_edit', kwargs={'pk': q.pk})

        response = self.client.post(url, {
            'customer': self.cust_profile.pk,
            'plan': self.plan2.pk,  # Changed to plan2 (2000.00)
            'tax': self.tax_18.pk,
            'discount': self.disc_10.pk,
            'valid_until': q.valid_until.isoformat(),
            'notes': q.notes,
        })
        self.assertEqual(response.status_code, 302)

        q.refresh_from_db()
        self.assertEqual(q.base_price, Decimal('2000.00'))
        self.assertEqual(q.discount_amount, Decimal('200.00'))  # 10% of 2000
        self.assertEqual(q.tax_amount, Decimal('324.00'))       # 18% of 1800
        self.assertEqual(q.total_amount, Decimal('2124.00'))

    def test_changing_only_tax_preserves_original_base_price_even_if_catalogue_changed(self):
        """Changing only tax preserves the quotation's base_price snapshot even if catalogue plan price changed."""
        q = self._create_initial_quotation()

        # Simulate Member 2 changing the catalogue plan price from 1000 to 1500
        self.plan1.base_price = Decimal('1500.00')
        self.plan1.save()

        url = reverse('quotations:quotation_edit', kwargs={'pk': q.pk})
        response = self.client.post(url, {
            'customer': self.cust_profile.pk,
            'plan': self.plan1.pk,  # Plan unchanged
            'tax': self.tax_5.pk,   # Tax changed to 5%
            'discount': self.disc_10.pk,
            'valid_until': q.valid_until.isoformat(),
            'notes': q.notes,
        })
        self.assertEqual(response.status_code, 302)

        q.refresh_from_db()
        # base_price must remain 1000.00, NOT updated to 1500.00!
        self.assertEqual(q.base_price, Decimal('1000.00'))
        self.assertEqual(q.discount_amount, Decimal('100.00'))
        self.assertEqual(q.tax_amount, Decimal('45.00'))     # 5% of 900
        self.assertEqual(q.total_amount, Decimal('945.00'))  # 900 + 45

    def test_changing_only_discount_preserves_original_base_price_even_if_catalogue_changed(self):
        """Changing only discount preserves the quotation's base_price snapshot."""
        q = self._create_initial_quotation()

        # Catalogue price changed
        self.plan1.base_price = Decimal('1500.00')
        self.plan1.save()

        url = reverse('quotations:quotation_edit', kwargs={'pk': q.pk})
        response = self.client.post(url, {
            'customer': self.cust_profile.pk,
            'plan': self.plan1.pk,
            'tax': self.tax_18.pk,
            'discount': self.disc_fixed_200.pk,  # Discount changed to flat 200
            'valid_until': q.valid_until.isoformat(),
            'notes': q.notes,
        })
        self.assertEqual(response.status_code, 302)

        q.refresh_from_db()
        # base_price must remain 1000.00!
        self.assertEqual(q.base_price, Decimal('1000.00'))
        self.assertEqual(q.discount_amount, Decimal('200.00'))
        self.assertEqual(q.tax_amount, Decimal('144.00'))     # 18% of 800
        self.assertEqual(q.total_amount, Decimal('944.00'))   # 800 + 144

    def test_changing_only_notes_preserves_every_pricing_snapshot(self):
        """Editing only notes preserves every pricing snapshot without recalculating against new catalogue prices."""
        q = self._create_initial_quotation()

        # Catalogue prices and rates change drastically
        self.plan1.base_price = Decimal('9999.00')
        self.plan1.save()
        self.tax_18.rate = Decimal('28.00')
        self.tax_18.save()

        url = reverse('quotations:quotation_edit', kwargs={'pk': q.pk})
        response = self.client.post(url, {
            'customer': self.cust_profile.pk,
            'plan': self.plan1.pk,
            'tax': self.tax_18.pk,
            'discount': self.disc_10.pk,
            'valid_until': q.valid_until.isoformat(),
            'notes': 'Commercial notes revised after negotiation meeting.',
        })
        self.assertEqual(response.status_code, 302)

        q.refresh_from_db()
        self.assertEqual(q.notes, 'Commercial notes revised after negotiation meeting.')
        # Every single monetary snapshot must be completely identical to original
        self.assertEqual(q.base_price, Decimal('1000.00'))
        self.assertEqual(q.discount_amount, Decimal('100.00'))
        self.assertEqual(q.tax_amount, Decimal('162.00'))
        self.assertEqual(q.total_amount, Decimal('1062.00'))

    def test_changing_only_valid_until_preserves_every_pricing_snapshot(self):
        """Editing only validity date preserves all pricing snapshots."""
        q = self._create_initial_quotation()
        new_validity = date.today() + timedelta(days=30)

        # Catalogue price changed
        self.plan1.base_price = Decimal('5555.00')
        self.plan1.save()

        url = reverse('quotations:quotation_edit', kwargs={'pk': q.pk})
        response = self.client.post(url, {
            'customer': self.cust_profile.pk,
            'plan': self.plan1.pk,
            'tax': self.tax_18.pk,
            'discount': self.disc_10.pk,
            'valid_until': new_validity.isoformat(),
            'notes': q.notes,
        })
        self.assertEqual(response.status_code, 302)

        q.refresh_from_db()
        self.assertEqual(q.valid_until, new_validity)
        self.assertEqual(q.base_price, Decimal('1000.00'))
        self.assertEqual(q.total_amount, Decimal('1062.00'))

    def test_final_status_quotations_retain_immutable_snapshots(self):
        """Accepted and Rejected quotations reject recalculation and editing."""
        q = self._create_initial_quotation()
        q.status = 'ACCEPTED'
        q.save()

        # Attempt to recalculate accepted quotation
        self.plan1.base_price = Decimal('7777.00')
        self.plan1.save()
        q.calculate_totals()
        q.save()

        q.refresh_from_db()
        self.assertEqual(q.base_price, Decimal('1000.00'))
        self.assertEqual(q.total_amount, Decimal('1062.00'))

        # Attempt to edit accepted quotation via view
        url = reverse('quotations:quotation_edit', kwargs={'pk': q.pk})
        res = self.client.get(url)
        self.assertEqual(res.status_code, 302)  # Redirects with error message

    def test_past_valid_until_rejected_in_form(self):
        """QuotationForm rejects validity dates in the past."""
        past_date = date.today() - timedelta(days=1)
        form = QuotationForm(data={
            'customer': self.cust_profile.pk,
            'plan': self.plan1.pk,
            'valid_until': past_date.isoformat(),
        })
        self.assertFalse(form.is_valid())
        self.assertIn('valid_until', form.errors)
        self.assertIn('cannot be in the past', form.errors['valid_until'][0])

    def test_inactive_catalogue_handling_new_vs_edit(self):
        """New form shows only active catalogue items; editing retains existing inactive items."""
        # Deactivate plan2
        self.plan2.is_active = False
        self.plan2.save()

        # 1. New quotation form: plan2 should NOT be available
        new_form = QuotationForm()
        self.assertNotIn(self.plan2, new_form.fields['plan'].queryset)

        # 2. Existing quotation with plan2: plan2 MUST remain available
        q_inactive = Quotation.objects.create(
            customer=self.cust_profile,
            plan=self.plan2,
            status='DRAFT'
        )
        edit_form = QuotationForm(instance=q_inactive)
        self.assertIn(self.plan2, edit_form.fields['plan'].queryset)


class QuotationLifecycleAndSecurityTests(TestCase):
    def setUp(self):
        self.client = Client()

        # Staff user
        self.staff_user = User.objects.create_user(
            username='staff_user',
            email='staff@brightloop.com',
            password='StaffPassword123!',
            is_staff=True
        )

        # Customer 1
        self.cust_user1 = User.objects.create_user(
            username='cust1',
            email='cust1@example.com',
            password='Password123!'
        )
        self.cust_profile1 = CustomerProfile.objects.create(
            user=self.cust_user1,
            company_name='Alpha Corp'
        )

        # Customer 2
        self.cust_user2 = User.objects.create_user(
            username='cust2',
            email='cust2@example.com',
            password='Password123!'
        )
        self.cust_profile2 = CustomerProfile.objects.create(
            user=self.cust_user2,
            company_name='Beta Corp'
        )

        # Product, Plan, Tax
        self.product = Product.objects.create(name='Test Suite')
        self.plan = SubscriptionPlan.objects.create(
            product=self.product,
            name='Standard Plan',
            billing_cycle='MONTHLY',
            base_price=Decimal('500.00'),
            is_active=True
        )
        self.tax = TaxConfiguration.objects.create(name='GST 10%', rate=Decimal('10.00'), is_active=True)

    def _create_quotation(self, customer, status='DRAFT', expired=False):
        valid_until = date.today() - timedelta(days=1) if expired else date.today() + timedelta(days=10)
        q = Quotation.objects.create(
            customer=customer,
            plan=self.plan,
            tax=self.tax,
            status=status,
            valid_until=valid_until,
            created_by=self.staff_user
        )
        q.calculate_totals()
        q.save()
        return q

    # --- Staff Lifecycle Tests ---
    def test_staff_can_send_draft_quotation(self):
        self.client.login(username='staff_user', password='StaffPassword123!')
        q = self._create_quotation(self.cust_profile1, status='DRAFT')
        response = self.client.post(reverse('quotations:quotation_send', kwargs={'pk': q.pk}))
        self.assertEqual(response.status_code, 302)
        q.refresh_from_db()
        self.assertEqual(q.status, 'SENT')

    def test_staff_cannot_send_expired_quotation(self):
        self.client.login(username='staff_user', password='StaffPassword123!')
        q = self._create_quotation(self.cust_profile1, status='DRAFT', expired=True)
        response = self.client.post(reverse('quotations:quotation_send', kwargs={'pk': q.pk}))
        self.assertEqual(response.status_code, 302)
        q.refresh_from_db()
        self.assertEqual(q.status, 'DRAFT')

    def test_staff_cannot_send_non_draft_quotation(self):
        self.client.login(username='staff_user', password='StaffPassword123!')
        q = self._create_quotation(self.cust_profile1, status='SENT')
        response = self.client.post(reverse('quotations:quotation_send', kwargs={'pk': q.pk}))
        self.assertEqual(response.status_code, 302)
        q.refresh_from_db()
        self.assertEqual(q.status, 'SENT')

    def test_staff_can_accept_sent_quotation_and_create_subscription(self):
        self.client.login(username='staff_user', password='StaffPassword123!')
        q = self._create_quotation(self.cust_profile1, status='SENT')
        response = self.client.post(reverse('quotations:quotation_accept', kwargs={'pk': q.pk}))
        self.assertEqual(response.status_code, 302)
        q.refresh_from_db()
        self.assertEqual(q.status, 'ACCEPTED')
        self.assertTrue(hasattr(q, 'subscription'))
        sub = q.subscription
        self.assertEqual(sub.status, 'ACTIVE')
        self.assertEqual(sub.plan_price, q.base_price)

    def test_staff_repeated_acceptance_does_not_create_duplicate_subscription(self):
        self.client.login(username='staff_user', password='StaffPassword123!')
        q = self._create_quotation(self.cust_profile1, status='SENT')
        # First accept
        self.client.post(reverse('quotations:quotation_accept', kwargs={'pk': q.pk}))
        self.assertEqual(Subscription.objects.filter(quotation=q).count(), 1)
        # Second accept attempt
        response = self.client.post(reverse('quotations:quotation_accept', kwargs={'pk': q.pk}))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Subscription.objects.filter(quotation=q).count(), 1)

    def test_staff_can_reject_draft_and_sent_quotations(self):
        self.client.login(username='staff_user', password='StaffPassword123!')
        q_draft = self._create_quotation(self.cust_profile1, status='DRAFT')
        self.client.post(reverse('quotations:quotation_reject', kwargs={'pk': q_draft.pk}))
        q_draft.refresh_from_db()
        self.assertEqual(q_draft.status, 'REJECTED')

        q_sent = self._create_quotation(self.cust_profile2, status='SENT')
        self.client.post(reverse('quotations:quotation_reject', kwargs={'pk': q_sent.pk}))
        q_sent.refresh_from_db()
        self.assertEqual(q_sent.status, 'REJECTED')

    def test_staff_cannot_reject_accepted_quotation(self):
        self.client.login(username='staff_user', password='StaffPassword123!')
        q = self._create_quotation(self.cust_profile1, status='ACCEPTED')
        self.client.post(reverse('quotations:quotation_reject', kwargs={'pk': q.pk}))
        q.refresh_from_db()
        self.assertEqual(q.status, 'ACCEPTED')

    # --- Customer Lifecycle & Permission Tests ---
    def test_customer_can_accept_own_sent_quotation(self):
        self.client.login(username='cust1', password='Password123!')
        q = self._create_quotation(self.cust_profile1, status='SENT')
        response = self.client.post(reverse('quotations:quotation_customer_accept', kwargs={'pk': q.pk}))
        self.assertEqual(response.status_code, 302)
        q.refresh_from_db()
        self.assertEqual(q.status, 'ACCEPTED')
        self.assertTrue(hasattr(q, 'subscription'))
        sub = q.subscription
        self.assertEqual(sub.customer, self.cust_profile1)
        self.assertEqual(sub.plan_price, Decimal('500.00'))

    def test_customer_can_reject_own_sent_quotation(self):
        self.client.login(username='cust1', password='Password123!')
        q = self._create_quotation(self.cust_profile1, status='SENT')
        response = self.client.post(reverse('quotations:quotation_customer_reject', kwargs={'pk': q.pk}))
        self.assertEqual(response.status_code, 302)
        q.refresh_from_db()
        self.assertEqual(q.status, 'REJECTED')
        self.assertFalse(hasattr(q, 'subscription'))

    def test_customer_cannot_accept_expired_quotation(self):
        self.client.login(username='cust1', password='Password123!')
        q = self._create_quotation(self.cust_profile1, status='SENT', expired=True)
        response = self.client.post(reverse('quotations:quotation_customer_accept', kwargs={'pk': q.pk}))
        self.assertEqual(response.status_code, 302)
        q.refresh_from_db()
        self.assertEqual(q.status, 'SENT')
        self.assertFalse(hasattr(q, 'subscription'))

    def test_customer_cannot_accept_other_customers_quotation(self):
        self.client.login(username='cust1', password='Password123!')
        # Quotation belongs to customer 2
        q = self._create_quotation(self.cust_profile2, status='SENT')
        response = self.client.post(reverse('quotations:quotation_customer_accept', kwargs={'pk': q.pk}))
        self.assertEqual(response.status_code, 403)
        q.refresh_from_db()
        self.assertEqual(q.status, 'SENT')

    def test_customer_cannot_reject_other_customers_quotation(self):
        self.client.login(username='cust1', password='Password123!')
        q = self._create_quotation(self.cust_profile2, status='SENT')
        response = self.client.post(reverse('quotations:quotation_customer_reject', kwargs={'pk': q.pk}))
        self.assertEqual(response.status_code, 403)
        q.refresh_from_db()
        self.assertEqual(q.status, 'SENT')

    def test_customer_cannot_reject_draft_or_accepted_quotations(self):
        self.client.login(username='cust1', password='Password123!')
        q_draft = self._create_quotation(self.cust_profile1, status='DRAFT')
        response = self.client.post(reverse('quotations:quotation_customer_reject', kwargs={'pk': q_draft.pk}))
        self.assertEqual(response.status_code, 302)
        q_draft.refresh_from_db()
        self.assertEqual(q_draft.status, 'DRAFT')

    def test_customer_cannot_create_edit_or_send_quotations(self):
        self.client.login(username='cust1', password='Password123!')
        # Cannot access create view
        res_create = self.client.get(reverse('quotations:quotation_create'))
        self.assertEqual(res_create.status_code, 403)

        q = self._create_quotation(self.cust_profile1, status='DRAFT')
        # Cannot access edit view
        res_edit = self.client.get(reverse('quotations:quotation_edit', kwargs={'pk': q.pk}))
        self.assertEqual(res_edit.status_code, 403)

        # Cannot send
        res_send = self.client.post(reverse('quotations:quotation_send', kwargs={'pk': q.pk}))
        self.assertEqual(res_send.status_code, 403)

    # --- HTTP Method Enforcement & Security Tests ---
    def test_get_requests_to_state_changing_actions_return_405(self):
        self.client.login(username='staff_user', password='StaffPassword123!')
        q = self._create_quotation(self.cust_profile1, status='SENT')

        self.assertEqual(self.client.get(reverse('quotations:quotation_send', kwargs={'pk': q.pk})).status_code, 405)
        self.assertEqual(self.client.get(reverse('quotations:quotation_accept', kwargs={'pk': q.pk})).status_code, 405)
        self.assertEqual(self.client.get(reverse('quotations:quotation_reject', kwargs={'pk': q.pk})).status_code, 405)

        self.client.login(username='cust1', password='Password123!')
        self.assertEqual(self.client.get(reverse('quotations:quotation_customer_accept', kwargs={'pk': q.pk})).status_code, 405)
        self.assertEqual(self.client.get(reverse('quotations:quotation_customer_reject', kwargs={'pk': q.pk})).status_code, 405)

    def test_unauthenticated_users_redirected_to_login(self):
        q = self._create_quotation(self.cust_profile1, status='SENT')
        urls = [
            reverse('quotations:quotation_list'),
            reverse('quotations:quotation_detail', kwargs={'pk': q.pk}),
            reverse('quotations:quotation_create'),
            reverse('quotations:quotation_edit', kwargs={'pk': q.pk}),
            reverse('quotations:quotation_send', kwargs={'pk': q.pk}),
            reverse('quotations:quotation_accept', kwargs={'pk': q.pk}),
            reverse('quotations:quotation_reject', kwargs={'pk': q.pk}),
            reverse('quotations:quotation_customer_accept', kwargs={'pk': q.pk}),
            reverse('quotations:quotation_customer_reject', kwargs={'pk': q.pk}),
        ]
        for url in urls:
            res = self.client.get(url)
            self.assertEqual(res.status_code, 302)
            self.assertIn('login', res.url)

    def test_data_isolation_between_customers(self):
        q2 = self._create_quotation(self.cust_profile2, status='SENT')
        self.client.login(username='cust1', password='Password123!')

        # Detail view for other customer's quotation returns 403
        res = self.client.get(reverse('quotations:quotation_detail', kwargs={'pk': q2.pk}))
        self.assertEqual(res.status_code, 403)

    # --- Search and Filter Tests ---
    def test_quotation_list_staff_and_customer_visibility(self):
        q1 = self._create_quotation(self.cust_profile1, status='DRAFT')
        q2 = self._create_quotation(self.cust_profile2, status='SENT')

        # Staff sees all
        self.client.login(username='staff_user', password='StaffPassword123!')
        res_staff = self.client.get(reverse('quotations:quotation_list'))
        self.assertEqual(res_staff.status_code, 200)
        self.assertContains(res_staff, f"QT-{q1.pk:04d}")
        self.assertContains(res_staff, f"QT-{q2.pk:04d}")

        # Customer 1 sees only own
        self.client.login(username='cust1', password='Password123!')
        res_cust = self.client.get(reverse('quotations:quotation_list'))
        self.assertEqual(res_cust.status_code, 200)
        self.assertContains(res_cust, f"QT-{q1.pk:04d}")
        self.assertNotContains(res_cust, f"QT-{q2.pk:04d}")

    def test_quotation_search_and_status_filter(self):
        self.client.login(username='staff_user', password='StaffPassword123!')
        q1 = self._create_quotation(self.cust_profile1, status='DRAFT')
        q2 = self._create_quotation(self.cust_profile2, status='SENT')

        # Status filter
        res_sent = self.client.get(reverse('quotations:quotation_list') + '?status=SENT')
        self.assertContains(res_sent, f"QT-{q2.pk:04d}")
        self.assertNotContains(res_sent, f"QT-{q1.pk:04d}")

        # Search by company name
        res_search = self.client.get(reverse('quotations:quotation_list') + '?q=Alpha')
        self.assertContains(res_search, f"QT-{q1.pk:04d}")
        self.assertNotContains(res_search, f"QT-{q2.pk:04d}")

        # Search by ID
        res_id = self.client.get(reverse('quotations:quotation_list') + f'?q=QT-{q2.pk:04d}')
        self.assertContains(res_id, f"QT-{q2.pk:04d}")
        self.assertNotContains(res_id, f"QT-{q1.pk:04d}")

    def test_customer_preselection_in_quotation_create(self):
        self.client.login(username='staff_user', password='StaffPassword123!')
        url = reverse('quotations:quotation_create') + f'?customer={self.cust_profile1.pk}'
        res = self.client.get(url)
        self.assertEqual(res.status_code, 200)
        form = res.context['form']
        self.assertEqual(form.initial.get('customer'), self.cust_profile1)

    def test_acceptance_preserves_quotation_pricing_snapshots(self):
        """Customer acceptance creates subscription without recalculating or modifying snapshots."""
        self.client.login(username='cust1', password='Password123!')
        q = self._create_quotation(self.cust_profile1, status='SENT')
        orig_base = q.base_price
        orig_tax = q.tax_amount
        orig_total = q.total_amount

        # Modify plan catalogue base price
        self.plan.base_price = Decimal('9999.00')
        self.plan.save()

        # Customer accepts
        self.client.post(reverse('quotations:quotation_customer_accept', kwargs={'pk': q.pk}))
        q.refresh_from_db()
        self.assertEqual(q.base_price, orig_base)
        self.assertEqual(q.tax_amount, orig_tax)
        self.assertEqual(q.total_amount, orig_total)

        # Subscription has original snapshot values
        sub = q.subscription
        self.assertEqual(sub.plan_price, orig_base)
