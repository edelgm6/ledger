from django.urls import path

from api.rest_api.report_views import (
    AccountDetailReportView,
    BalanceSheetReportView,
    CashFlowReportView,
    EntityDetailReportView,
    IncomeReportView,
    SpendingByEntityReportView,
    TrendReportView,
)
from api.rest_api.views import (
    AccountListView,
    EntityListView,
    JournalEntryCreateView,
    TransactionListView,
)

app_name = "rest_api"

urlpatterns = [
    path("transactions/", TransactionListView.as_view(), name="transactions"),
    path("accounts/", AccountListView.as_view(), name="accounts"),
    path("entities/", EntityListView.as_view(), name="entities"),
    path("journal-entries/", JournalEntryCreateView.as_view(), name="journal-entries"),
    # Read-only reporting endpoints (wrap the statement engine).
    path("reports/income/", IncomeReportView.as_view(), name="reports-income"),
    path(
        "reports/balance-sheet/",
        BalanceSheetReportView.as_view(),
        name="reports-balance-sheet",
    ),
    path("reports/cash-flow/", CashFlowReportView.as_view(), name="reports-cash-flow"),
    path(
        "reports/spending-by-entity/",
        SpendingByEntityReportView.as_view(),
        name="reports-spending-by-entity",
    ),
    path("reports/trend/", TrendReportView.as_view(), name="reports-trend"),
    path(
        "reports/account-detail/",
        AccountDetailReportView.as_view(),
        name="reports-account-detail",
    ),
    path(
        "reports/entity-detail/",
        EntityDetailReportView.as_view(),
        name="reports-entity-detail",
    ),
]
