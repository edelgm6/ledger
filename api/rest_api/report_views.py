"""
Read-only reporting endpoints for the /api/v1/ REST API.

These GET endpoints expose the statement engine (``api/statement.py`` +
``api/services/statement_services.py``) as JSON so an agent can answer
questions about spending, build dashboards, and write summaries. They wrap the
same services the login-gated HTML statement views use (``StatementView``), add
no business logic, and never write. They ride the global DRF API-key auth
(``APIKeyAuthentication`` + ``IsAuthenticated``), so callers need ``LEDGER_API_KEY``.
"""

from datetime import date, datetime
from typing import Optional, Tuple

from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from api import utils
from api.rest_api import report_serializers
from api.services import statement_services
from api.statement import BalanceSheet, IncomeStatement, Trend

DATE_FORMAT = "%Y-%m-%d"


def _parse_date(value: Optional[str], field: str) -> Optional[date]:
    """Parse a YYYY-MM-DD query param.

    Returns None when the param is absent (so the caller can default it), but
    raises a 400 when it's present-but-unparseable — better for an agent client
    than silently returning data for a different (defaulted) period.
    """
    if not value:
        return None
    try:
        return datetime.strptime(value, DATE_FORMAT).date()
    except ValueError:
        raise ValidationError(
            {field: f"Invalid date '{value}'; expected YYYY-MM-DD."}
        )


def _date_range(request) -> Tuple[date, date]:
    """Resolve ``from_date``/``to_date`` params, defaulting to last month."""
    default_from, default_to = utils.get_default_statement_date_range()
    from_param = request.query_params.get("from_date")
    to_param = request.query_params.get("to_date")
    from_date = _parse_date(from_param, "from_date") or default_from
    to_date = _parse_date(to_param, "to_date") or default_to
    return from_date, to_date


class IncomeReportView(APIView):
    """GET /api/v1/reports/income/ — income statement for a date range.

    ``?group_by=entity`` returns the by-entity breakdown instead of by-account.
    """

    def get(self, request):
        from_date, to_date = _date_range(request)
        income_statement = IncomeStatement(end_date=to_date, start_date=from_date)

        payload = {
            "from_date": from_date,
            "to_date": to_date,
            "net_income": income_statement.net_income,
            "tax_rate": income_statement.get_tax_rate(),
            "savings_rate": income_statement.get_savings_rate(),
        }

        if request.query_params.get("group_by") == "entity":
            summary = statement_services.build_entity_income_summary(income_statement)
            payload["group_by"] = "entity"
            payload["summary"] = report_serializers.serialize_entity_income_summary(
                summary
            )
        else:
            summary = statement_services.build_statement_summary(income_statement)
            payload["group_by"] = "account"
            payload["summary"] = report_serializers.serialize_statement_summary(
                summary
            )

        return Response(payload)


class BalanceSheetReportView(APIView):
    """GET /api/v1/reports/balance-sheet/ — point-in-time position at to_date."""

    def get(self, request):
        _, to_date = _date_range(request)
        balance_sheet = BalanceSheet(end_date=to_date)
        summary = statement_services.build_statement_summary(balance_sheet)

        return Response(
            {
                "as_of": to_date,
                "summary": report_serializers.serialize_statement_summary(summary),
                "metrics": {
                    metric.name: metric.value for metric in balance_sheet.metrics
                },
            }
        )


class CashFlowReportView(APIView):
    """GET /api/v1/reports/cash-flow/ — cash flow metrics for a date range."""

    def get(self, request):
        from_date, to_date = _date_range(request)
        metrics = statement_services.calculate_cash_flow_metrics(from_date, to_date)

        return Response(
            {
                "from_date": from_date,
                "to_date": to_date,
                **report_serializers.serialize_cash_flow_metrics(metrics),
            }
        )


class SpendingByEntityReportView(APIView):
    """GET /api/v1/reports/spending-by-entity/ — income/expense by entity."""

    def get(self, request):
        from_date, to_date = _date_range(request)
        income_statement = IncomeStatement(end_date=to_date, start_date=from_date)
        summary = statement_services.build_entity_income_summary(income_statement)

        return Response(
            {
                "from_date": from_date,
                "to_date": to_date,
                **report_serializers.serialize_entity_income_summary(summary),
            }
        )


class TrendReportView(APIView):
    """GET /api/v1/reports/trend/ — month-by-month balances for a date range."""

    def get(self, request):
        from_date, to_date = _date_range(request)
        # Trend takes start_date as a string and end_date as a date object.
        trend = Trend(
            start_date=utils.format_datetime_to_string(from_date), end_date=to_date
        )
        return Response(
            {
                "from_date": from_date,
                "to_date": to_date,
                "balances": report_serializers.serialize_trend_balances(
                    trend.get_balances()
                ),
            }
        )


class AccountDetailReportView(APIView):
    """GET /api/v1/reports/account-detail/ — signed line items for one account.

    Requires ``account_id``, ``from_date``, ``to_date``.
    """

    def get(self, request):
        account_id = request.query_params.get("account_id")
        if not account_id:
            return Response({"error": "account_id is required."}, status=400)

        from_date, to_date = _date_range(request)
        detail = statement_services.get_statement_detail_items(
            account_id=account_id,
            from_date=utils.format_datetime_to_string(from_date),
            to_date=utils.format_datetime_to_string(to_date),
        )
        return Response(report_serializers.serialize_detail(detail))


class EntityDetailReportView(APIView):
    """GET /api/v1/reports/entity-detail/ — signed line items for an entity section.

    Requires ``sub_type``, ``from_date``, ``to_date``. ``entity_id`` is optional;
    omit it (or pass empty) to get the Unassigned bucket.
    """

    def get(self, request):
        sub_type = request.query_params.get("sub_type")
        if not sub_type:
            return Response({"error": "sub_type is required."}, status=400)

        entity_id = request.query_params.get("entity_id") or None
        from_date, to_date = _date_range(request)
        detail = statement_services.get_statement_detail_items_by_entity(
            entity_id=entity_id,
            sub_type=sub_type,
            from_date=utils.format_datetime_to_string(from_date),
            to_date=utils.format_datetime_to_string(to_date),
        )
        return Response(report_serializers.serialize_detail(detail))
