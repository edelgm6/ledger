from django.conf import settings
from django.contrib import admin
from django.contrib.auth.views import LoginView
from django.urls import include, path

from api.views.amortization_views import (
    AmortizationFormView,
    AmortizationView,
    AmortizeFormView,
)
from api.views.entity_settings_views import EntityFormView, EntitySettingsView
from api.views.entity_views import (
    EntityGroupedBalancesView,
    EntityHistoryTable,
    TagEntitiesForm,
    TagEntitiesView,
    UntagJournalEntryView,
)
from api.views.frontend_views import IndexView, TrendView, UploadTransactionsView
from api.views.journal_entry_views import (
    JournalEntryFormView,
    JournalEntryTableView,
    JournalEntryView,
    PaystubDetailView,
    PaystubRetryView,
    PaystubTableView,
    TriggerAutoTagView,
)
from api.views.reconciliation_views import ReconciliationTableView, ReconciliationView
from api.views.recharacterize_views import (
    RecharacterizeApplyView,
    RecharacterizeEditAgentView,
    RecharacterizeEditView,
    RecharacterizeExportView,
    RecharacterizeManualView,
    RecharacterizeMessageView,
    RecharacterizePageView,
    RecharacterizeResetView,
    RecharacterizeRetryView,
    RecharacterizeRevertView,
    RecharacterizeView,
)
from api.views.bill_settings_views import (
    BillRuleFormView,
    BillRulesView,
    BillsView,
)
from api.views.loan_views import (
    LoanFormView,
    LoanScheduleView,
    LoanSettingsView,
)
from api.views.prefill_settings_views import (
    DocSearchFormView,
    DocSearchView,
    PrefillFormView,
    PrefillSettingsView,
)
from api.views.settings_views import AccountFormView, SettingsView
from api.views.statement_views import (
    StatementDetailView,
    StatementEntityDetailView,
    StatementView,
)
from api.views.tax_views import (
    ApplyTaxRecommendationView,
    TaxChargeFormView,
    TaxChargeTableView,
    TaxesView,
)
from api.views.transaction_views import (
    LinkTransactionsContentView,
    LinkTransactionsView,
    TransactionContentView,
    TransactionFormView,
    TransactionsView,
)

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/", include("api.rest_api.urls", namespace="rest_api")),
    path("", IndexView.as_view(), name="index"),
    path("login/", LoginView.as_view(template_name="api/login.html"), name="login"),
    path("trend/", TrendView.as_view(), name="trend"),
    path(
        "upload-transactions/",
        UploadTransactionsView.as_view(),
        name="upload-transactions",
    ),
    # Statements
    path(
        "statements/<str:statement_type>/", StatementView.as_view(), name="statements"
    ),
    path(
        "statements/detail/entity/",
        StatementEntityDetailView.as_view(),
        name="statement-entity-detail",
    ),
    path(
        "statements/detail/<int:account_id>",
        StatementDetailView.as_view(),
        name="statement-detail",
    ),
    # JE page
    path("journal-entries/", JournalEntryView.as_view(), name="journal-entries"),
    path(
        "journal-entries/<int:transaction_id>/",
        JournalEntryView.as_view(),
        name="journal-entries",
    ),
    path(
        "journal-entries/form/<int:transaction_id>/",
        JournalEntryFormView.as_view(),
        name="journal-entry-form",
    ),
    path(
        "journal-entries/table/",
        JournalEntryTableView.as_view(),
        name="journal-entries-table",
    ),
    path("paystubs/", PaystubTableView.as_view(), name="paystub-table"),
    path(
        "paystubs/<int:s3file_id>/retry/",
        PaystubRetryView.as_view(),
        name="paystub-retry",
    ),
    path(
        "paystubs/<int:paystub_id>/", PaystubDetailView.as_view(), name="paystub-detail"
    ),
    path("trigger-autotag/", TriggerAutoTagView.as_view(), name="trigger-autotag"),
    # Link page
    path(
        "transactions-linking/",
        LinkTransactionsView.as_view(),
        name="link-transactions",
    ),
    path(
        "transactions-linking/content",
        LinkTransactionsContentView.as_view(),
        name="link-transactions-content",
    ),
    # Transactions page
    path("transactions/", TransactionsView.as_view(), name="transactions"),
    path(
        "transactions/<int:transaction_id>/",
        TransactionsView.as_view(),
        name="update-transaction",
    ),
    path(
        "transactions/form/<int:transaction_id>/",
        TransactionFormView.as_view(),
        name="transaction-form",
    ),
    path(
        "transactions/content/",
        TransactionContentView.as_view(),
        name="transactions-content",
    ),
    # Taxes page
    path("taxes/", TaxesView.as_view(), name="taxes"),
    path("taxes/<int:pk>/", TaxesView.as_view(), name="edit-tax-charge"),
    path(
        "taxes/apply/<int:account_pk>/<str:end_date>/",
        ApplyTaxRecommendationView.as_view(),
        name="apply-tax-recommendation",
    ),
    path("tax-charge-table/", TaxChargeTableView.as_view(), name="tax-charge-table"),
    path("taxes/form/", TaxChargeFormView.as_view(), name="tax-form"),
    path("taxes/form/<int:pk>/", TaxChargeFormView.as_view(), name="tax-form-bound"),
    # Reconciliations
    path("reconciliation/", ReconciliationView.as_view(), name="reconciliation"),
    path(
        "reconciliation-table/",
        ReconciliationTableView.as_view(),
        name="reconciliation-table",
    ),
    # Amortizations
    path("amortization/", AmortizationView.as_view(), name="amortization"),
    path(
        "amortization/amortization-form/<int:journal_entry_item_id>/",
        AmortizationFormView.as_view(),
        name="amortization-form",
    ),
    path(
        "amortization/amortize-form/<int:amortization_id>/",
        AmortizeFormView.as_view(),
        name="amortize-form",
    ),
    # Recharacterize (agentic bulk edit)
    path("recharacterize/", RecharacterizeView.as_view(), name="recharacterize"),
    path(
        "recharacterize/message/",
        RecharacterizeMessageView.as_view(),
        name="recharacterize-message",
    ),
    path(
        "recharacterize/manual/",
        RecharacterizeManualView.as_view(),
        name="recharacterize-manual",
    ),
    path(
        "recharacterize/edit/",
        RecharacterizeEditView.as_view(),
        name="recharacterize-edit",
    ),
    path(
        "recharacterize/edit-agent/",
        RecharacterizeEditAgentView.as_view(),
        name="recharacterize-edit-agent",
    ),
    path(
        "recharacterize/apply/",
        RecharacterizeApplyView.as_view(),
        name="recharacterize-apply",
    ),
    path(
        "recharacterize/revert/",
        RecharacterizeRevertView.as_view(),
        name="recharacterize-revert",
    ),
    path(
        "recharacterize/retry/",
        RecharacterizeRetryView.as_view(),
        name="recharacterize-retry",
    ),
    path(
        "recharacterize/reset/",
        RecharacterizeResetView.as_view(),
        name="recharacterize-reset",
    ),
    path(
        "recharacterize/export/",
        RecharacterizeExportView.as_view(),
        name="recharacterize-export",
    ),
    path(
        "recharacterize/page/",
        RecharacterizePageView.as_view(),
        name="recharacterize-page",
    ),
    # Tagging balances
    path(
        "tag/journal-entry-item/<int:journal_entry_item_id>/",
        UntagJournalEntryView.as_view(),
        name="untag-journal-entry",
    ),
    # Settings (user-facing CRUD for config models)
    path("settings/", SettingsView.as_view(), name="settings"),
    path(
        "settings/accounts/new/form/",
        AccountFormView.as_view(),
        name="settings-account-new-form",
    ),
    path(
        "settings/accounts/<int:account_id>/",
        SettingsView.as_view(),
        name="settings-account",
    ),
    path(
        "settings/accounts/<int:account_id>/form/",
        AccountFormView.as_view(),
        name="settings-account-form",
    ),
    # Settings — utility-bill rules (config CRUD) and bills monitor
    path(
        "settings/bill-rules/",
        BillRulesView.as_view(),
        name="settings-bill-rules",
    ),
    path(
        "settings/bill-rules/new/form/",
        BillRuleFormView.as_view(),
        name="settings-bill-rule-new-form",
    ),
    path(
        "settings/bill-rules/<int:rule_id>/",
        BillRulesView.as_view(),
        name="settings-bill-rule",
    ),
    path(
        "settings/bill-rules/<int:rule_id>/form/",
        BillRuleFormView.as_view(),
        name="settings-bill-rule-form",
    ),
    path("settings/bills/", BillsView.as_view(), name="settings-bills"),
    # Settings — entities (config CRUD)
    path(
        "settings/entities/",
        EntitySettingsView.as_view(),
        name="settings-entities",
    ),
    path(
        "settings/entities/new/form/",
        EntityFormView.as_view(),
        name="settings-entity-new-form",
    ),
    path(
        "settings/entities/<int:entity_id>/",
        EntitySettingsView.as_view(),
        name="settings-entity",
    ),
    path(
        "settings/entities/<int:entity_id>/form/",
        EntityFormView.as_view(),
        name="settings-entity-form",
    ),
    # Settings — loans (amortization-schedule config CRUD + schedule view)
    path(
        "settings/loans/",
        LoanSettingsView.as_view(),
        name="settings-loans",
    ),
    path(
        "settings/loans/new/form/",
        LoanFormView.as_view(),
        name="settings-loan-new-form",
    ),
    path(
        "settings/loans/<int:loan_id>/",
        LoanSettingsView.as_view(),
        name="settings-loan",
    ),
    path(
        "settings/loans/<int:loan_id>/form/",
        LoanFormView.as_view(),
        name="settings-loan-form",
    ),
    path(
        "settings/loans/<int:loan_id>/schedule/",
        LoanScheduleView.as_view(),
        name="settings-loan-schedule",
    ),
    path(
        "settings/loans/schedule-row/<int:row_id>/",
        LoanScheduleView.as_view(),
        name="settings-loan-schedule-row",
    ),
    # Settings — prefills (config CRUD) and their doc searches
    path(
        "settings/prefills/",
        PrefillSettingsView.as_view(),
        name="settings-prefills",
    ),
    path(
        "settings/prefills/new/form/",
        PrefillFormView.as_view(),
        name="settings-prefill-new-form",
    ),
    path(
        "settings/prefills/<int:prefill_id>/",
        PrefillSettingsView.as_view(),
        name="settings-prefill",
    ),
    path(
        "settings/prefills/<int:prefill_id>/form/",
        PrefillFormView.as_view(),
        name="settings-prefill-form",
    ),
    path(
        "settings/prefills/<int:prefill_id>/docsearches/",
        DocSearchView.as_view(),
        name="settings-prefill-docsearches",
    ),
    path(
        "settings/prefills/<int:prefill_id>/docsearches/new/form/",
        DocSearchFormView.as_view(),
        name="settings-docsearch-new-form",
    ),
    path(
        "settings/prefills/<int:prefill_id>/docsearches/<int:docsearch_id>/",
        DocSearchView.as_view(),
        name="settings-docsearch",
    ),
    path(
        "settings/prefills/<int:prefill_id>/docsearches/<int:docsearch_id>/form/",
        DocSearchFormView.as_view(),
        name="settings-docsearch-form",
    ),
    path("tag/", TagEntitiesView.as_view(), name="tag-entities"),
    path("tag/balances/", EntityGroupedBalancesView.as_view(), name="entity-balances"),
    path(
        "tag/form/<int:journal_entry_item_id>/",
        TagEntitiesForm.as_view(),
        name="tag-entities-form",
    ),
    path(
        "tag/entity-history/<int:entity_id>/",
        EntityHistoryTable.as_view(),
        name="entity-history",
    ),
]

if settings.DEBUG:
    import debug_toolbar
    urlpatterns = [
        path("__debug__/", include(debug_toolbar.urls)),
    ] + urlpatterns
