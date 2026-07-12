from django.core.management.base import BaseCommand, CommandError
from django.db import transaction as db_transaction

from api.models import Account

# Old 4-digit account-number prefix -> new prefix. The command rewrites only the
# numeric prefix in each Account.name and preserves the label after the first
# "-", so account labels are deliberately kept out of this file. Grouped by the
# target band. Every account's current prefix must appear here, so the identity
# entries (e.g. "5000": "5000") are intentional: they assert that the whole
# chart is accounted for and let the command abort on any unmapped account.
PREFIX_MAP = {
    # --- Assets ---
    # Cash (1000-1099): shift +10 to open 1000 for the first cash account
    "0000": "1000",
    "1000": "1010",
    "1010": "1020",
    "1020": "1030",
    "1030": "1040",
    "1031": "1050",
    # Accounts Receivable (1100-1199): pull in the mis-banded receivables
    "1100": "1100",
    "1110": "1110",
    "1001": "1120",  # was typed cash
    "1420": "1130",  # was in securities band
    "1430": "1140",
    "1535": "1150",
    "1536": "1160",
    # Prepaid Expenses (1200-1249)
    "1150": "1200",
    # Securities - Unrestricted (1300-1399)
    "1300": "1300",
    "1310": "1310",
    "1400": "1320",
    "1410": "1330",
    "1320": "1340",
    # Securities - Retirement (1400-1599): 401k -> HSA -> IRA -> 529 -> stock comp
    "1500": "1400",
    "1501": "1410",
    "1502": "1420",
    "1520": "1430",
    "1540": "1440",
    "1510": "1450",
    "1511": "1460",
    "1530": "1470",
    "1550": "1500",
    "1560": "1510",
    "1570": "1520",
    "1580": "1530",
    "1590": "1550",
    "1311": "1560",  # was in unrestricted band
    # Real Estate (1600-1699)
    "1600": "1600",
    "1610": "1610",
    # Vehicles (1700-1799)
    "1710": "1700",
    # --- Liabilities ---
    # Short-term Debt (2000-2099)
    "2000": "2000",
    "2010": "2010",
    "2020": "2020",
    # Taxes Payable (2100-2199)
    "2100": "2100",
    "2110": "2110",
    "2120": "2120",
    "2121": "2121",
    "2130": "2130",
    # Long-term Debt (2500-2599)
    "2500": "2500",
    "2505": "2510",
    "2510": "2520",
    "2515": "2530",
    # --- Equity ---
    "3000": "3000",
    # --- Income ---
    # Salary (4000-4099)
    "4000": "4000",
    "4010": "4010",
    # Dividends & Interest (4100-4199)
    "4020": "4100",
    "4030": "4110",
    # Other Income (4200-4299)
    "4040": "4200",
    "4045": "4210",
    # Realized Investment Gains (4300-4399)
    "4050": "4300",
    # Unrealized Investment Gains (4400-4499)
    "4100": "4400",
    # --- Expenses ---
    # Operating (5000-5899) + fees (5900-5989) - unchanged
    "5000": "5000",
    "5100": "5100",
    "5200": "5200",
    "5300": "5300",
    "5301": "5301",
    "5302": "5302",
    "5400": "5400",
    "5401": "5401",
    "5410": "5410",
    "5420": "5420",
    "5500": "5500",
    "5510": "5510",
    "5520": "5520",
    "5530": "5530",
    "5600": "5600",
    "5601": "5601",
    "5610": "5610",
    "5620": "5620",
    "5700": "5700",
    "5710": "5710",
    "5800": "5800",
    "5810": "5810",
    "5820": "5820",
    "5830": "5830",
    "5840": "5840",
    "5850": "5850",
    "5900": "5900",
    "5910": "5910",
    "5920": "5920",
    "5930": "5930",
    # Depreciation (5990-5999)
    "7000": "5990",
    # Interest (6000-6099)
    "6000": "6000",
    "6005": "6010",
    "6010": "6020",
    "6015": "6030",
    # Tax (6100-6199) - unchanged
    "6100": "6100",
    "6110": "6110",
    "6120": "6120",
    "6121": "6121",
    "6130": "6130",
    "6131": "6131",
    "6140": "6140",
}


class Command(BaseCommand):
    help = (
        "Renumber the chart of accounts by rewriting the NNNN- prefix in each "
        "account name. Labels are preserved; only the numeric prefix changes."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print the old -> new mapping and write nothing.",
        )

    def handle(self, *args, **options):
        # Plan the rename; every account must have a known prefix or we abort so
        # a partial run against the wrong database is impossible.
        planned = []  # list of (account, new_name)
        unmapped = []
        for account in Account.objects.all():
            prefix, sep, label = account.name.partition("-")
            if not sep or prefix not in PREFIX_MAP:
                unmapped.append(account.name)
                continue
            planned.append((account, f"{PREFIX_MAP[prefix]}-{label}"))

        if unmapped:
            raise CommandError(
                "Aborting without changes: these accounts have no prefix mapping, "
                "so this is the wrong database or the chart has drifted:\n  "
                + "\n  ".join(sorted(unmapped))
            )

        changed = [
            (account, new_name)
            for account, new_name in planned
            if account.name != new_name
        ]
        for account, new_name in sorted(changed, key=lambda p: p[1]):
            self.stdout.write(f"  {account.name}  ->  {new_name}")

        if options["dry_run"]:
            self.stdout.write(
                self.style.WARNING(
                    f"Dry run: {len(changed)} of {len(planned)} accounts would "
                    "change. No changes written."
                )
            )
            return

        # Two-phase rename inside one transaction. A new number can collide with
        # an existing one mid-flight (e.g. 4020->4100 while 4100->4400), and name
        # is unique, so first park each on a unique sentinel, then set final names.
        accounts = [account for account, _new_name in changed]
        with db_transaction.atomic():
            for account, _new_name in changed:
                account.name = f"TMP{account.id}"
            Account.objects.bulk_update(accounts, ["name"])

            for account, new_name in changed:
                account.name = new_name
            Account.objects.bulk_update(accounts, ["name"])

        self.stdout.write(
            self.style.SUCCESS(
                f"Renumbered {len(changed)} of {len(planned)} accounts."
            )
        )
