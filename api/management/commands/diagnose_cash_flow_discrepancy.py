import calendar
import datetime
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

# Residuals below this are floating-point / rounding noise, not a real gap.
THRESHOLD = Decimal("0.005")


class Command(BaseCommand):
    help = (
        "Read-only. Reproduce the global cash-flow discrepancy and localize it. "
        "First checks the specific whole-JE-exclusion hypothesis (a real cash leg "
        "dropped from investing because its entry also carries an unrealized-gain "
        "or depreciation leg). If that does not explain it, bisect the residual in "
        "time (year -> month -> day) and dump the entries on the offending day. "
        "The period residual is cash_delta - net_cash_flow - change in starting "
        "equity, which telescopes to the global discrepancy."
    )

    def handle(self, *args, **options):
        cash_flow = self._statement(GLOBAL_START, GLOBAL_END)

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
        if dropped == discrepancy:
            self.stdout.write(
                self.style.SUCCESS(
                    "\nThe dropped cash legs above fully explain the discrepancy "
                    f"({dropped}). Fix: stop excluding whole JEs in "
                    "get_cash_from_investing_balances."
                )
            )
            return

        self._localize_in_time()

    # -- statement / residual helpers ------------------------------------

    def _statement(self, start, end) -> CashFlowStatement:
        """A CashFlowStatement covering [start, end] (dates or ISO strings)."""
        prior_day = _to_date(start) - datetime.timedelta(days=1)
        return CashFlowStatement(
            income_statement=IncomeStatement(end_date=end, start_date=start),
            end_balance_sheet=BalanceSheet(end_date=end),
            start_balance_sheet=BalanceSheet(end_date=prior_day),
        )

    @staticmethod
    def _starting_equity(balance_sheet) -> Decimal:
        return sum(
            (
                balance.amount
                for balance in balance_sheet.balances
                if balance.account.special_type == Account.SpecialType.STARTING_EQUITY
            ),
            Decimal("0"),
        )

    def _period_residual(self, start, end) -> Decimal:
        """Unexplained cash for [start, end].

        cash_delta - net_cash_flow - change in starting equity. Operations and
        financing telescope by construction, so a nonzero value points at a JE
        in this window whose cash effect the reconstruction fails to mirror.
        """
        cash_flow = self._statement(start, end)
        cash_delta = cash_flow.get_cash_balance(
            cash_flow.end_balance_sheet
        ) - cash_flow.get_cash_balance(cash_flow.start_balance_sheet)
        starting_equity_delta = self._starting_equity(
            cash_flow.end_balance_sheet
        ) - self._starting_equity(cash_flow.start_balance_sheet)
        return cash_delta - cash_flow.net_cash_flow - starting_equity_delta

    def _flagged(self, periods):
        """(start, end, residual) for periods whose residual clears THRESHOLD."""
        found = []
        for start, end in periods:
            residual = self._period_residual(start, end)
            if abs(residual) > THRESHOLD:
                found.append((start, end, residual))
        return found

    # -- reports ---------------------------------------------------------

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
            lines.append(self._describe(journal_entry))
            lines.extend(self._describe_leg(leg) for leg in legs)
            net_dropped += sum(
                (leg.get_signed_amount() for leg in cash_legs), Decimal("0")
            )

        for line in lines or ["  (none)"]:
            self.stdout.write(line)
        self.stdout.write(f"  net cash dropped: {net_dropped}\n")
        return net_dropped

    def _localize_in_time(self) -> None:
        """Bisect the residual year -> month -> day and dump the offending day."""
        first = JournalEntry.objects.order_by("date").values_list(
            "date", flat=True
        ).first()
        last = JournalEntry.objects.order_by("-date").values_list(
            "date", flat=True
        ).first()
        if first is None:
            self.stdout.write("No journal entries to scan.")
            return

        self.stdout.write(
            "Localizing residual (cash_delta - net_cash_flow - change in starting "
            "equity):"
        )
        for y_start, y_end, y_res in self._flagged(_year_bounds(first, last)):
            self.stdout.write(f"  {y_start.year}: {y_res}")
            for m_start, m_end, m_res in self._flagged(_month_bounds(y_start, y_end)):
                self.stdout.write(f"    {m_start:%Y-%m}: {m_res}")
                for d_start, _d_end, d_res in self._flagged(
                    _day_bounds(m_start, m_end)
                ):
                    self.stdout.write(f"      {d_start}: {d_res}")
                    self._dump_day(d_start)

    def _dump_day(self, day: datetime.date) -> None:
        entries = (
            JournalEntry.objects.filter(date=day)
            .order_by("id")
            .prefetch_related(
                Prefetch(
                    "journal_entry_items",
                    queryset=JournalEntryItem.objects.select_related("account"),
                )
            )
        )
        for journal_entry in entries:
            self.stdout.write("        " + self._describe(journal_entry).strip())
            for leg in journal_entry.journal_entry_items.all():
                self.stdout.write("    " + self._describe_leg(leg))

    # -- formatting ------------------------------------------------------

    @staticmethod
    def _describe(journal_entry) -> str:
        return (
            f"  JE {journal_entry.id} {journal_entry.date} "
            f"{journal_entry.description}"
        )

    @staticmethod
    def _describe_leg(leg) -> str:
        return (
            f"      {leg.type:6} {leg.account.name:38} {leg.amount:>12} "
            f"deprec={leg.account.is_depreciation} sub={leg.account.sub_type}"
        )


def _to_date(value) -> datetime.date:
    if isinstance(value, datetime.date):
        return value
    return datetime.date.fromisoformat(value)


def _year_bounds(first: datetime.date, last: datetime.date):
    for year in range(first.year, last.year + 1):
        yield datetime.date(year, 1, 1), datetime.date(year, 12, 31)


def _month_bounds(first: datetime.date, last: datetime.date):
    year, month = first.year, first.month
    while (year, month) <= (last.year, last.month):
        last_day = calendar.monthrange(year, month)[1]
        yield datetime.date(year, month, 1), datetime.date(year, month, last_day)
        month += 1
        if month > 12:
            month, year = 1, year + 1


def _day_bounds(first: datetime.date, last: datetime.date):
    day = first
    while day <= last:
        yield day, day
        day += datetime.timedelta(days=1)
