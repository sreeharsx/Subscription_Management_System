from django.core.management.base import BaseCommand
from billing.services import update_overdue_invoices


class Command(BaseCommand):
    help = "Mark past-due invoices with outstanding balances as overdue."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report eligible invoices without saving changes.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        result = update_overdue_invoices(dry_run=dry_run)

        if dry_run:
            for item in result["details"]:
                self.stdout.write(
                    f"{item['invoice_number']}: {item['previous_status']} -> "
                    f"OVERDUE; outstanding {item['outstanding_balance']}"
                )

        action = "would be updated" if dry_run else "updated"
        self.stdout.write(
            self.style.SUCCESS(
                f"Eligible invoices: {result['eligible_count']}; "
                f"{action}: {result['updated_count']}; "
                f"already overdue: {result['already_overdue_count']}."
            )
        )
