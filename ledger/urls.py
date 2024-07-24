import debug_toolbar
from django.contrib import admin
from django.urls import path, include
from django.contrib.auth.views import LoginView
from django.conf import settings
from api.views.frontend_views import TrendView,  UploadTransactionsView, IndexView
from api.views.transaction_views import LinkTransactionsContentView, TransactionContentView, TransactionFormView, LinkTransactionsView,  TransactionsView
from api.views.journal_entry_views import JournalEntryView, JournalEntryFormView, JournalEntryTableView, PaystubDetailView
from api.views.tax_views import TaxChargeTableView,TaxChargeFormView, TaxesView
from api.views.reconciliation_views import ReconciliationTableView, ReconciliationView
from api.views.amortization_views import AmortizationFormView, AmortizationView, AmortizeFormView
from api.views.statement_views import StatementView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', IndexView.as_view(), name='index'),
    path('login/', LoginView.as_view(template_name='api/login.html'), name='login'),
    path('trend/', TrendView.as_view(), name='trend'),
    path('upload-transactions/', UploadTransactionsView.as_view(), name='upload-transactions'),

    # Statements
    path('statements/<str:statement_type>/', StatementView.as_view(), name='statements'),

    # JE page
    path('journal-entries/', JournalEntryView.as_view(), name='journal-entries'),
    path('journal-entries/<int:transaction_id>/', JournalEntryView.as_view(), name='journal-entries'),
    path('journal-entries/form/<int:transaction_id>/', JournalEntryFormView.as_view(), name='journal-entry-form'),
    path('journal-entries/table/', JournalEntryTableView.as_view(), name='journal-entries-table'),
    path('paystubs/<int:paystub_id>/', PaystubDetailView.as_view(), name='paystub-detail'),

    # Link page
    path('transactions-linking/', LinkTransactionsView.as_view(), name='link-transactions'),
    path('transactions-linking/content', LinkTransactionsContentView.as_view(), name='link-transactions-content'),

    # Transactions page
    path('transactions/', TransactionsView.as_view(), name='transactions'),
    path('transactions/<int:transaction_id>/', TransactionsView.as_view(), name='update-transaction'),
    path('transactions/form/<int:transaction_id>/', TransactionFormView.as_view(), name='transaction-form'),
    path('transactions/content/', TransactionContentView.as_view(), name='transactions-content'),

    # Taxes page
    path('taxes/', TaxesView.as_view(), name='taxes'),
    path('taxes/<int:pk>/', TaxesView.as_view(), name='edit-tax-charge'),
    path('tax-charge-table/', TaxChargeTableView.as_view(), name='tax-charge-table'),
    path('taxes/form/', TaxChargeFormView.as_view(), name='tax-form'),
    path('taxes/form/<int:pk>/', TaxChargeFormView.as_view(), name='tax-form-bound'),

    # Reconciliations
    path('reconciliation/', ReconciliationView.as_view(), name='reconciliation'),
    path('reconciliation-table/', ReconciliationTableView.as_view(), name='reconciliation-table'),

    # Amortizations
    path('amortization/', AmortizationView.as_view(), name='amortization'),
    path('amortization/amortization-form/<int:transaction_id>/', AmortizationFormView.as_view(), name='amortization-form'),
    path('amortization/amortize-form/<int:amortization_id>/', AmortizeFormView.as_view(), name='amortize-form'),
]

if settings.DEBUG:

    urlpatterns = [
        path('__debug__/', include(debug_toolbar.urls)),
    ] + urlpatterns
