from django.test import TestCase, Client
from django.contrib.auth.models import User
from accounts.models import CustomerProfile, AuditLog
from accounts.services import log_activity


class AccountsAuthTestCase(TestCase):
    def setUp(self):
        self.client = Client()
        self.staff_user = User.objects.create_user('staff1', 'staff1@brightloop.com', 'staffpass123', is_staff=True)
        self.cust_user1 = User.objects.create_user('cust1', 'cust1@brightloop.com', 'custpass123')
        self.cust_profile1 = CustomerProfile.objects.create(
            user=self.cust_user1, company_name="Alpha Corp", phone="1234567890", gst_number="GST01"
        )
        self.cust_user2 = User.objects.create_user('cust2', 'cust2@brightloop.com', 'custpass123')
        self.cust_profile2 = CustomerProfile.objects.create(
            user=self.cust_user2, company_name="Beta Corp", phone="0987654321"
        )

    def test_login_logout_flow(self):
        """Verify login redirects to dashboard and POST logout redirects to login."""
        # 1. Login
        login_success = self.client.login(username='staff1', password='staffpass123')
        self.assertTrue(login_success)
        response = self.client.get('/dashboard/')
        self.assertEqual(response.status_code, 200)

        # 2. Logout POST
        logout_response = self.client.post('/accounts/logout/')
        self.assertEqual(logout_response.status_code, 302)
        self.assertIn('/accounts/login/', logout_response.url)

    def test_staff_required_for_customer_creation(self):
        """Only staff can create customers; normal customer is denied with 403."""
        # Customer attempts to view customer_create
        self.client.login(username='cust1', password='custpass123')
        response = self.client.get('/accounts/customers/create/')
        self.assertEqual(response.status_code, 403)

        # Staff can view customer_create
        self.client.login(username='staff1', password='staffpass123')
        response = self.client.get('/accounts/customers/create/')
        self.assertEqual(response.status_code, 200)

    def test_customer_isolation_on_detail_view(self):
        """Customer 1 cannot access Customer 2's profile detail view."""
        self.client.login(username='cust1', password='custpass123')

        # Cust 1 accesses their own profile -> 200 OK
        resp1 = self.client.get(f'/accounts/customers/{self.cust_profile1.pk}/')
        self.assertEqual(resp1.status_code, 200)

        # Cust 1 accesses Cust 2's profile -> 403 Forbidden
        resp2 = self.client.get(f'/accounts/customers/{self.cust_profile2.pk}/')
        self.assertEqual(resp2.status_code, 403)

    def test_audit_log_creation_and_access_control(self):
        """Verify audit log creation and staff-only access."""
        log = log_activity(self.staff_user, 'TEST_ACTION', self.cust_profile1, "Test details")
        self.assertIsNotNone(log)
        self.assertEqual(log.action, 'TEST_ACTION')
        self.assertEqual(log.model_name, 'CustomerProfile')

        # Staff can view activity log -> 200 OK
        self.client.login(username='staff1', password='staffpass123')
        resp_staff = self.client.get('/accounts/activity/')
        self.assertEqual(resp_staff.status_code, 200)

        # Customer cannot view activity log -> 403 Forbidden
        self.client.login(username='cust1', password='custpass123')
        resp_cust = self.client.get('/accounts/activity/')
        self.assertEqual(resp_cust.status_code, 403)

