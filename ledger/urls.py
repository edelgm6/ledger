"""ledger URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/3.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path
from api.views import TaxChargeView, JournalEntryView, TransactionView, AccountView, UploadTransactionsView, AccountBalanceView, TransactionTypeView, CSVProfileView, GenerateReconciliationsView, ReconciliationView, PlugReconciliationView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('journal-entries/', JournalEntryView.as_view(), name='journal-entries'),
    # path('journal-entry-items/', JournalEntryItemView.as_view(), name='journal-entry-items'),
    path('transactions/<int:pk>', TransactionView.as_view(), name='update-transaction'),
    path('transactions/', TransactionView.as_view(), name='transactions'),
    path('transaction-types/', TransactionTypeView.as_view(), name='transaction-types'),
    path('upload-transactions/', UploadTransactionsView.as_view(), name='upload-transactions'),
    path('account-balances/', AccountBalanceView.as_view(), name='account-balances'),
    path('accounts/', AccountView.as_view(), name='accounts'),
    path('csv-profiles/', CSVProfileView.as_view(), name='csv-profiles'),
    path('reconciliations/<int:pk>/plug/', PlugReconciliationView.as_view(), name='plug-reconciliation'),
    path('reconciliations/generate/', GenerateReconciliationsView.as_view(), name='generate-reconciliations'),
    path('reconciliations/', ReconciliationView.as_view(), name='reconciliations'),
    path('tax-charges/<int:pk>', TaxChargeView.as_view(), name='update-tax-charge'),
    path('tax-charges/', TaxChargeView.as_view(), name='tax-charges'),
]
