from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db.models import Prefetch, Q

from api.models import Account, JournalEntry, JournalEntryItem
from api.statement import BalanceSheet, CashFlowStatement, IncomeStatement

# The discrepancy flag is an all-time reconciliation, so mirror the global window
# that calculate_cash_flow_metrics() uses (api/services/statement_services.py).
GLOBAL_START = "1900-01-01"
GLOBAL_END = "2500-01-01"

# The sub_types that feed the investing section (get_cash_from_investing_balances).
INVESTING_SUB_TYPES = [
    Account.SubType.SECURITIES_RETIREMENT,
    Account.SubType.SECURITIES_UNRESTRICTED,
    Account.SubType.REAL_ESTATE,
    Account.SubType.VEHICLES,
]


class Command(BaseCommand):
    help = (
        "Read-only. Reproduce the global cash-flow discrepancy and localize it. "
        "Investing is the only bucket built from raw journal-entry items with a "
        "whole-JE exclusion, so it is the only place the reconstruction can drift "
        "from the balance-sheet identity. This reports (1) JEs whose real cash leg "
        "is dropped because the same entry also carries an unrealized-gain or "
        "depreciation leg, and (2) any investing account whose JEI-based flow "
        "diverges from its balance-sheet delta."
    )

    def handle(self, *args, **options):
        cash_flow = CashFlowStatement(
            income_statement=IncomeStatement(
                end_date=GLOBAL_END, start_date=GLOBAL_START
            ),
            end_balance_sheet=BalanceSheet(end_date=GLOBAL_END),
            start_balance_sheet=BalanceSheet(end_date=GLOBAL_START),
        )

        try:
            discrepancy = cash_flow.get_cash_flow_discrepancy()
        except IndexError:
            self.stdout.write(
                self.style.ERROR(
                    "No account has special_type=STARTING_EQUITY, so the "
                    "discrepancy cannot be computed. This is a separate, more "
                    "serious problem than a bucketing residual."
                )
            )
            return

        if discrepancy is None:
            self.stdout.write(
                self.style.SUCCESS("No discrepancy: the cash flow reconciles.")
            )
            return

        self.stdout.write(
            self.style.WARNING(f"Cash-flow discrepancy: {discrepancy}")
        )
        self.stdout.write(f"net_cash_flow: {cash_flow.net_cash_flow}\n")

        dropped = self._report_dropped_cash_legs()
        self._report_account_gaps(cash_flow)

        if dropped != 0:
            if dropped == discrepancy:
                self.stdout.write(
                    self.style.SUCCESS(
                        "\nThe dropped cash legs above fully explain the "
                        f"discrepancy ({dropped}). Fix: stop excluding whole JEs "
                        "in get_cash_from_investing_balances."
                    )
                )
            else:
                self.stdout.write(
                    self.style.WARNING(
                        f"\nDropped cash legs ({dropped}) do not fully match the "
                        f"discrepancy ({discrepancy}); see the per-account gaps "
                        "above."
                    )
                )

    def _report_dropped_cash_legs(self) -> Decimal:
        """JEs the investing query excludes wholesale that also move real cash.

        get_cash_from_investing_balances excludes any securities/RE/vehicle leg
        whose JE contains an unrealized-gain or depreciation leg. When such a JE
        *also* has a cash leg, that real cash movement is silently dropped from
        investing, leaving a permanent residual.
        """
        suspects = (
            JournalEntry.objects.filter(
                Q(
                    journal_entry_items__account__sub_type=(
                        Account.SubType.UNREALIZED_INVESTMENT_GAINS
                    )
                )
                | Q(journal_entry_items__account__is_depreciation=True)
            )
            .filter(journal_entry_items__account__sub_type__in=INVESTING_SUB_TYPES)
            .distinct()
            .prefetch_related(
                Prefetch(
                    "journal_entry_items",
                    queryset=JournalEntryItem.objects.select_related("account"),
                )
            )
        )

        self.stdout.write("Suspect JEs (real cash leg dropped by whole-JE exclusion):")
        net_dropped = Decimal("0")
        lines = []
        for journal_entry in suspects:
            legs = list(journal_entry.journal_entry_items.all())
            cash_legs = [
                leg for leg in legs if leg.account.sub_type == Account.SubType.CASH
            ]
            if not cash_legs:
                continue
            lines.append(
                f"  JE {journal_entry.id} {journal_entry.date} "
                f"{journal_entry.description}"
            )
            lines.extend(
                f"      {leg.type:6} {leg.account.name:38} {leg.amount:>12} "
                f"deprec={leg.account.is_depreciation} sub={leg.account.sub_type}"
                for leg in legs
            )
            net_dropped += sum(
                (leg.get_signed_amount() for leg in cash_legs), Decimal("0")
            )

        for line in lines or ["  (none)"]:
            self.stdout.write(line)
        self.stdout.write(f"  net cash dropped: {net_dropped}\n")
        return net_dropped

    def _report_account_gaps(self, cash_flow: CashFlowStatement) -> None:
        """Per investing account, JEI-based flow vs its balance-sheet delta.

        Both figures are already carried on the cash_flow object (keyed by the
        Account instances), so derive the account set from them rather than
        issuing another query.
        """
        bs_delta = {
            b.account: b.amount
            for b in cash_flow.balance_sheet_deltas
            if b.account.sub_type in INVESTING_SUB_TYPES
        }
        jei_flow = {b.account: b.amount for b in cash_flow.cash_from_investing_balances}

        self.stdout.write("Per-account gaps (JEI investing flow vs balance-sheet delta):")
        rows = []
        for account in sorted(bs_delta.keys() | jei_flow.keys(), key=lambda a: a.name):
            jei = jei_flow.get(account, Decimal("0"))
            bs = bs_delta.get(account, Decimal("0"))
            gap = jei - bs
            if abs(gap) > Decimal("0.005"):
                rows.append(f"  {account.name:38} jei={jei} bs_delta={bs} gap={gap}")
        for row in rows or ["  (none)"]:
            self.stdout.write(row)
