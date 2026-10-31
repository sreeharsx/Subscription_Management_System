from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from accounts.models import CustomerProfile
from accounts.forms import CustomerUserForm, CustomerUserEditForm, CustomerProfileForm


class CustomerModelAndFormTests(TestCase):
    def setUp(self):
        self.staff_user = User.objects.create_user(
            username='staff_admin',
            email='staff@brightloop.io',
            password='Password123!',
            is_staff=True
        )
        self.existing_user = User.objects.create_user(
            username='acme_user',
            email='contact@acme.com',
            password='Password123!'
        )
        self.existing_profile = CustomerProfile.objects.create(
            user=self.existing_user,
            company_name='Acme Corp',
            phone='+91 98765 43210',
            address='123 Industrial Way, Tech Park',
            gst_number='29ABCDE1234F1Z5'
        )

    def test_case_insensitive_email_uniqueness_on_create(self):
        """Email uniqueness must be case-insensitive across all User records."""
        form = CustomerUserForm(data={
            'username': 'new_acme',
            'first_name': 'New',
            'last_name': 'Acme',
            'email': 'CONTACT@ACME.COM',  # Same as contact@acme.com in uppercase
            'password': 'SecurePassword123',
            'confirm_password': 'SecurePassword123'
        })
        self.assertFalse(form.is_valid())
        self.assertIn('email', form.errors)
        self.assertIn("already exists", form.errors['email'][0].lower())

    def test_password_mismatch_validation(self):
        """Form must reject registration when passwords do not match."""
        form = CustomerUserForm(data={
            'username': 'different_pwd',
            'first_name': 'Test',
            'last_name': 'User',
            'email': 'diff@example.com',
            'password': 'PasswordOne123',
            'confirm_password': 'PasswordTwo123'
        })
        self.assertFalse(form.is_valid())
        self.assertIn("Passwords do not match.", str(form.errors))

    def test_phone_format_validation(self):
        """Phone numbers must contain between 10 and 15 digits."""
        # Valid phone
        valid_form = CustomerProfileForm(data={
            'company_name': 'Alpha Ltd',
            'phone': '+91 98123 45678',
            'address': 'Plot 42',
            'gst_number': ''
        })
        self.assertTrue(valid_form.is_valid(), valid_form.errors)

        # Invalid phone: too short (<10 digits)
        invalid_form = CustomerProfileForm(data={
            'company_name': 'Alpha Ltd',
            'phone': '12345',
            'address': 'Plot 42',
            'gst_number': ''
        })
        self.assertFalse(invalid_form.is_valid())
        self.assertIn('phone', invalid_form.errors)

    def test_gst_format_validation(self):
        """GST numbers must match 15-character Indian GSTIN format."""
        # Valid GSTIN
        valid_gst_form = CustomerProfileForm(data={
            'company_name': 'Beta Corp',
            'phone': '9876543210',
            'gst_number': '29ABCDE1234F1Z5'
        })
        self.assertTrue(valid_gst_form.is_valid())

        # Invalid GSTIN: wrong length / invalid pattern
        invalid_gst_form = CustomerProfileForm(data={
            'company_name': 'Beta Corp',
            'phone': '9876543210',
            'gst_number': 'INVALID_GST'
        })
        self.assertFalse(invalid_gst_form.is_valid())
        self.assertIn('gst_number', invalid_gst_form.errors)

    def test_user_edit_form_allows_own_email_but_rejects_duplicates(self):
        """Editing customer can keep their existing email, but cannot take another user's email."""
        # Keeping existing email (case variation) is valid
        edit_own = CustomerUserEditForm(
            data={'first_name': 'Acme', 'last_name': 'Leader', 'email': 'Contact@acme.com'},
            instance=self.existing_user
        )
        self.assertTrue(edit_own.is_valid(), edit_own.errors)

        # Creating another user first
        other_user = User.objects.create_user(username='other_corp', email='other@example.com', password='Password123!')

        # Attempting to assign other_user's email to self.existing_user
        edit_taken = CustomerUserEditForm(
            data={'first_name': 'Acme', 'last_name': 'Leader', 'email': 'OTHER@EXAMPLE.COM'},
            instance=self.existing_user
        )
        self.assertFalse(edit_taken.is_valid())
        self.assertIn('email', edit_taken.errors)


class CustomerViewAndRBACSecurityTests(TestCase):
    def setUp(self):
        self.client = Client()

        # Staff user
        self.staff_user = User.objects.create_user(
            username='staff_member',
            email='staff@brightloop.com',
            password='StaffPass123!',
            is_staff=True
        )

        # Customer 1
        self.cust1_user = User.objects.create_user(
            username='cust1',
            email='cust1@acme.com',
            first_name='Rajesh',
            last_name='Kumar',
            password='CustPass123!'
        )
        self.cust1_profile = CustomerProfile.objects.create(
            user=self.cust1_user,
            company_name='Acme Systems',
            phone='9876543210',
            gst_number='29ABCDE1234F1Z5'
        )

        # Customer 2
        self.cust2_user = User.objects.create_user(
            username='cust2',
            email='cust2@globex.in',
            first_name='Priya',
            last_name='Nair',
            password='CustPass123!'
        )
        self.cust2_profile = CustomerProfile.objects.create(
            user=self.cust2_user,
            company_name='Globex Freight',
            phone='9811122233'
        )

    def test_customer_creation_view_by_staff(self):
        """Staff can create a customer with User credentials and Profile details."""
        self.client.login(username='staff_member', password='StaffPass123!')
        response = self.client.post(reverse('accounts:customer_create'), {
            'username': 'zenith_tech',
            'first_name': 'Zenith',
            'last_name': 'Enterprises',
            'email': 'billing@zenith.org',
            'password': 'SecurePassword999',
            'confirm_password': 'SecurePassword999',
            'company_name': 'Zenith Cloud Services',
            'phone': '+91 9988776655',
            'address': 'Level 4, Cyber Towers',
            'gst_number': '33AABCG9876D1Z2'
        })
        self.assertEqual(response.status_code, 302)

        # Verify created records
        created_user = User.objects.get(username='zenith_tech')
        self.assertTrue(created_user.check_password('SecurePassword999'))
        self.assertEqual(created_user.customer_profile.company_name, 'Zenith Cloud Services')

    def test_customer_edit_view_by_staff(self):
        """Staff can update both User fields (name, email) and CustomerProfile fields."""
        self.client.login(username='staff_member', password='StaffPass123!')
        response = self.client.post(reverse('accounts:customer_edit', kwargs={'pk': self.cust1_profile.pk}), {
            'first_name': 'Rajesh Kumar',
            'last_name': 'Updated',
            'email': 'rajesh.new@acme.com',
            'company_name': 'Acme Systems International',
            'phone': '9876500000',
            'address': 'New Headquarters',
            'gst_number': '29ABCDE1234F1Z5'
        })
        self.assertEqual(response.status_code, 302)

        self.cust1_user.refresh_from_db()
        self.cust1_profile.refresh_from_db()

        self.assertEqual(self.cust1_user.first_name, 'Rajesh Kumar')
        self.assertEqual(self.cust1_user.email, 'rajesh.new@acme.com')
        self.assertEqual(self.cust1_profile.company_name, 'Acme Systems International')
        self.assertEqual(self.cust1_profile.phone, '9876500000')

    def test_customer_search_filtering(self):
        """Search query filters customers by company, name, email, and phone."""
        self.client.login(username='staff_member', password='StaffPass123!')

        # 1. Search by company name "Globex"
        res1 = self.client.get(reverse('accounts:customer_list') + '?q=Globex')
        self.assertEqual(res1.status_code, 200)
        self.assertContains(res1, 'Globex Freight')
        self.assertNotContains(res1, 'Acme Systems')

        # 2. Search by phone
        res2 = self.client.get(reverse('accounts:customer_list') + '?q=9876543210')
        self.assertEqual(res2.status_code, 200)
        self.assertContains(res2, 'Acme Systems')
        self.assertNotContains(res2, 'Globex Freight')

        # 3. Non-matching query
        res3 = self.client.get(reverse('accounts:customer_list') + '?q=NonExistentKeyword')
        self.assertEqual(res3.status_code, 200)
        self.assertContains(res3, 'No customers match your search')

    def test_customer_data_isolation(self):
        """Customer 1 must receive 403 Forbidden when trying to access Customer 2's profile."""
        self.client.login(username='cust1', password='CustPass123!')

        # Customer 1 accesses their own profile -> 200 OK
        res_own = self.client.get(reverse('accounts:customer_detail', kwargs={'pk': self.cust1_profile.pk}))
        self.assertEqual(res_own.status_code, 200)

        # Customer 1 accesses Customer 2's profile -> 403 Forbidden
        res_other = self.client.get(reverse('accounts:customer_detail', kwargs={'pk': self.cust2_profile.pk}))
        self.assertEqual(res_other.status_code, 403)

    def test_staff_required_permission_enforcement(self):
        """Customer users cannot access staff-only views (list, create, edit)."""
        self.client.login(username='cust1', password='CustPass123!')

        # Cannot access customer list
        self.assertEqual(self.client.get(reverse('accounts:customer_list')).status_code, 403)

        # Cannot access customer create
        self.assertEqual(self.client.get(reverse('accounts:customer_create')).status_code, 403)

        # Cannot access customer edit
        self.assertEqual(
            self.client.get(reverse('accounts:customer_edit', kwargs={'pk': self.cust1_profile.pk})).status_code,
            403
        )
