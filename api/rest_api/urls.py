from django.urls import path

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
]
