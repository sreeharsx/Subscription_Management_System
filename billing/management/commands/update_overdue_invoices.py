from django.core.management.base import BaseCommand
from django.db.models import F
from django.utils import timezone

from billing.models import Invoice


class Command(BaseCommand):
    help = "Mark past-due invoices with outstanding balances as overdue."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report eligible invoices without saving changes.",
        )

    def handle(self, *args, **options):
        today = timezone.localdate()
        dry_run = options["dry_run"]
        eligible_invoices = Invoice.objects.filter(
            due_date__lt=today,
            total_amount__gt=F("amount_paid"),
        ).exclude(status="VOID").order_by("pk")

        eligible_count = eligible_invoices.count()
        updated_count = 0
        already_overdue_count = 0

        for invoice in eligible_invoices:
            outstanding_balance = invoice.outstanding_balance
            if invoice.status == "OVERDUE":
                already_overdue_count += 1
            else:
                updated_count += 1
                if not dry_run:
                    invoice.status = "OVERDUE"
                    invoice.save(update_fields=["status"])

            if dry_run:
                self.stdout.write(
                    f"{invoice.invoice_number}: {invoice.status} -> "
                    f"OVERDUE; outstanding {outstanding_balance}"
                )

        action = "would be updated" if dry_run else "updated"
        self.stdout.write(
            self.style.SUCCESS(
                f"Eligible invoices: {eligible_count}; "
                f"{action}: {updated_count}; "
                f"already overdue: {already_overdue_count}."
            )
        )
