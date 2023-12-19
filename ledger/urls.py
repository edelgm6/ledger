from django.contrib import admin
from django.urls import path
from django.contrib.auth.views import LoginView
from api.views.frontend_views import TrendView,  UploadTransactionsView, IndexView
from api.views.transaction_views import JournalEntryView, LinkTransactionsView, JournalEntryFormView, TransactionsTableView
from api.views.tax_views import TaxChargeTableView,TaxChargeFormView, TaxesView
from api.views.reconciliation_views import ReconciliationTableView, ReconciliationView
from api.views.amortization_views import AmortizationFormView, AmortizationView, AmortizeFormView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', IndexView.as_view(), name='index'),
    path('login/', LoginView.as_view(template_name='api/login.html'), name='login'),
    path('trend/', TrendView.as_view(), name='trend'),
    # JE page
    path('transactions/table/', TransactionsTableView.as_view(), name='transactions-table'),
    path('journal-entries/', JournalEntryView.as_view(), name='journal-entries'),
    path('journal-entries/<int:transaction_id>/', JournalEntryView.as_view(), name='journal-entries'),
    path('journal-entries/form/<int:transaction_id>/', JournalEntryFormView.as_view(), name='journal-entry-form'),
    # Link page
    path('transactions-linking/', LinkTransactionsView.as_view(), name='link-transactions'),
    # Taxes page
    path('taxes/', TaxesView.as_view(), name='taxes'),
    path('taxes/<int:pk>/', TaxesView.as_view(), name='edit-tax-charge'),
    path('tax-charge-table/', TaxChargeTableView.as_view(), name='tax-charge-table'),
    path('taxes/form/', TaxChargeFormView.as_view(), name='tax-form'),
    path('taxes/form/<int:pk>/', TaxChargeFormView.as_view(), name='tax-form-bound'),
    # Other
    path('reconciliation/', ReconciliationView.as_view(), name='reconciliation'),
    path('reconciliation-table/', ReconciliationTableView.as_view(), name='reconciliation-table'),
    path('upload-transactions/', UploadTransactionsView.as_view(), name='upload-transactions'),
    path('amortization/', AmortizationView.as_view(), name='amortization'),
    path('amortization/amortization-form/<int:transaction_id>/', AmortizationFormView.as_view(), name='amortization-form'),
    path('amortization/amortize-form/<int:amortization_id>/', AmortizeFormView.as_view(), name='amortize-form'),
]
