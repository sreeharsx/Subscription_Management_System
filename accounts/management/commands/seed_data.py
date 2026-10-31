from decimal import Decimal
from datetime import date, timedelta
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from accounts.models import CustomerProfile
from products.models import Product, SubscriptionPlan, TaxConfiguration, DiscountConfiguration
from quotations.models import Quotation
from subscriptions.models import Subscription
from subscriptions.services import create_subscription_from_quotation
from billing.models import Invoice, Payment
from billing.services import generate_invoice_for_subscription, record_payment


class Command(BaseCommand):
    help = "Seed database with realistic demo data for hackathon presentation"

    def handle(self, *args, **options):
        self.stdout.write("Starting database seeding...")

        # 1. Admin & Staff
        admin_user, _ = User.objects.get_or_create(
            username='admin',
            defaults={
                'email': 'admin@brightloop.com',
                'first_name': 'System',
                'last_name': 'Administrator',
                'is_staff': True,
                'is_superuser': True,
            }
        )
        admin_user.set_password('admin123')
        admin_user.save()

        staff_user, _ = User.objects.get_or_create(
            username='staff',
            defaults={
                'email': 'staff@brightloop.com',
                'first_name': 'Aarav',
                'last_name': 'Sharma',
                'is_staff': True,
            }
        )
        staff_user.set_password('staff123')
        staff_user.save()

        # 2. Customers
        customers_data = [
            ('acme', 'acme123', 'Rajesh', 'Kumar', 'rajesh@acme.com', 'Acme Technologies Pvt Ltd', '+91 98765 43210', '29ABCDE1234F1Z5'),
            ('globex', 'globex123', 'Priya', 'Nair', 'priya@globex.in', 'Globex Logistics LLP', '+91 98111 22334', '33AABCG9876D1Z2'),
            ('initech', 'initech123', 'Vikram', 'Mehta', 'vikram@initech.io', 'Initech Innovations', '+91 99000 55443', '27AAACI5566K1Z9'),
        ]

        cust_profiles = {}
        for uname, pwd, fname, lname, email, company, phone, gst in customers_data:
            user, _ = User.objects.get_or_create(
                username=uname,
                defaults={'first_name': fname, 'last_name': lname, 'email': email}
            )
            user.set_password(pwd)
            user.save()
            profile, _ = CustomerProfile.objects.get_or_create(
                user=user,
                defaults={'company_name': company, 'phone': phone, 'gst_number': gst}
            )
            cust_profiles[uname] = profile

        # 3. Products & Plans
        p_erp, _ = Product.objects.get_or_create(
            name="BrightCore ERP",
            defaults={'description': 'Comprehensive cloud ERP with financial, inventory, and supply chain modules.'}
        )
        plan_starter, _ = SubscriptionPlan.objects.get_or_create(
            product=p_erp,
            name="Starter Monthly",
            defaults={'billing_cycle': 'MONTHLY', 'base_price': Decimal('2500.00'), 'description': 'Up to 5 users'}
        )
        plan_annual, _ = SubscriptionPlan.objects.get_or_create(
            product=p_erp,
            name="Enterprise Annual",
            defaults={'billing_cycle': 'ANNUALLY', 'base_price': Decimal('25000.00'), 'description': 'Unlimited users'}
        )

        p_desk, _ = Product.objects.get_or_create(
            name="BrightDesk Support",
            defaults={'description': 'Omnichannel ticketing, live chat, and customer satisfaction tracking.'}
        )
        plan_desk_pro, _ = SubscriptionPlan.objects.get_or_create(
            product=p_desk,
            name="Growth Monthly",
            defaults={'billing_cycle': 'MONTHLY', 'base_price': Decimal('1500.00'), 'description': 'Up to 10 agents'}
        )

        # 4. Tax & Discount Configurations
        tax_18, _ = TaxConfiguration.objects.get_or_create(
            name="GST 18%",
            defaults={'rate': Decimal('18.00'), 'is_active': True}
        )
        tax_5, _ = TaxConfiguration.objects.get_or_create(
            name="GST 5%",
            defaults={'rate': Decimal('5.00'), 'is_active': True}
        )

        disc_festive, _ = DiscountConfiguration.objects.get_or_create(
            code="FESTIVE15",
            defaults={
                'name': 'Festive Offer 15%',
                'discount_type': 'PERCENTAGE',
                'value': Decimal('15.00'),
                'is_active': True
            }
        )
        disc_flat, _ = DiscountConfiguration.objects.get_or_create(
            code="LAUNCH500",
            defaults={
                'name': 'Launch Special ₹500 Off',
                'discount_type': 'FIXED',
                'value': Decimal('500.00'),
                'is_active': True
            }
        )

        # 5. Quotations
        # Quotation 1: Acme -> Accepted
        q1, created = Quotation.objects.get_or_create(
            customer=cust_profiles['acme'],
            plan=plan_starter,
            defaults={
                'tax': tax_18,
                'discount': disc_festive,
                'status': 'ACCEPTED',
                'created_by': staff_user,
                'notes': 'Special inaugural festive pricing for Acme.'
            }
        )
        if created:
            q1.calculate_totals()
            q1.save()

        # Quotation 2: Globex -> Sent
        q2, created = Quotation.objects.get_or_create(
            customer=cust_profiles['globex'],
            plan=plan_desk_pro,
            defaults={
                'tax': tax_18,
                'discount': disc_flat,
                'status': 'SENT',
                'created_by': staff_user,
                'valid_until': date.today() + timedelta(days=14),
                'notes': 'Awaiting customer approval.'
            }
        )
        if created:
            q2.calculate_totals()
            q2.save()

        # Quotation 3: Initech -> Draft
        q3, created = Quotation.objects.get_or_create(
            customer=cust_profiles['initech'],
            plan=plan_annual,
            defaults={
                'tax': tax_18,
                'status': 'DRAFT',
                'created_by': staff_user,
                'notes': 'Draft proposal for annual enterprise rollout.'
            }
        )
        if created:
            q3.calculate_totals()
            q3.save()

        # 6. Subscriptions
        if not hasattr(q1, 'subscription'):
            sub1 = create_subscription_from_quotation(q1)
            self.stdout.write(f"Created Subscription {sub1}")
        else:
            sub1 = q1.subscription

        # 7. Invoices & Payments for sub1
        # Invoice 1: Past month (Paid)
        inv_sep, created = Invoice.objects.get_or_create(
            subscription=sub1,
            billing_period_key='2026-09',
            defaults={
                'invoice_number': f'INV-{sub1.pk:05d}-2026-09',
                'status': 'PAID',
                'base_amount': sub1.plan_price,
                'discount_amount': sub1.discount_amount,
                'tax_amount': (sub1.plan_price - sub1.discount_amount) * Decimal('0.18'),
                'total_amount': (sub1.plan_price - sub1.discount_amount) * Decimal('1.18'),
                'amount_paid': (sub1.plan_price - sub1.discount_amount) * Decimal('1.18'),
                'issue_date': date(2026, 9, 1),
                'due_date': date(2026, 9, 16),
                'paid_date': date(2026, 9, 10),
            }
        )
        if created:
            Payment.objects.create(
                invoice=inv_sep,
                amount=inv_sep.total_amount,
                payment_date=date(2026, 9, 10),
                payment_method='BANK_TRANSFER',
                reference_number='HDFC-NEFT-991204',
                status='COMPLETED',
                recorded_by=staff_user,
                notes='Full payment received via NEFT.'
            )

        # Invoice 2: Current month (Partially Paid)
        inv_oct, created = generate_invoice_for_subscription(sub1, billing_date=date(2026, 10, 1))
        if created or inv_oct.amount_paid == Decimal('0.00'):
            partial_amount = Decimal('1500.00')
            record_payment(
                invoice=inv_oct,
                amount=partial_amount,
                payment_method='UPI',
                payment_date=date(2026, 10, 5),
                recorded_by=staff_user,
                reference_number='UPI/20261005/112233',
                notes='First partial installment.'
            )

        self.stdout.write(self.style.SUCCESS("Demo database successfully seeded!"))
        self.stdout.write(self.style.SUCCESS("--- Credentials ---"))
        self.stdout.write("Admin:    username='admin'   password='admin123'")
        self.stdout.write("Staff:    username='staff'   password='staff123'")
        self.stdout.write("Customer: username='acme'    password='acme123'")
        self.stdout.write("Customer: username='globex'  password='globex123'")
        self.stdout.write("Customer: username='initech' password='initech123'")
