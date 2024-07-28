from django.contrib import admin
from import_export.admin import ImportExportModelAdmin
from .resources import AccountResource, JournalEntryResource, JournalEntryItemResource, TransactionResource
from .models import (
    PrefillItem, Prefill, Amortization, TaxCharge, Account, Transaction,
    JournalEntry, JournalEntryItem, AutoTag, CSVProfile, Reconciliation,
    CSVColumnValuePair, S3File, DocSearch, Paystub, PaystubValue,
    Entity
)


# Admin definitions
class AccountAdmin(ImportExportModelAdmin):
    list_display = ('name', 'type', 'sub_type', 'csv_profile', 'is_closed')
    resource_class = AccountResource


class AutoTagAdmin(admin.ModelAdmin):
    list_display = ('account', 'search_string', 'transaction_type')


class CSVProfileAdmin(admin.ModelAdmin):
    list_display = ('name', 'date', 'description', 'category')


class JournalEntryItemAdmin(ImportExportModelAdmin):
    resource_class = JournalEntryItemResource
    list_display = ('journal_entry', 'type', 'amount', 'account')


class JournalEntryItemInline(admin.TabularInline):
    model = JournalEntryItem
    extra = 1


class JournalEntryAdmin(ImportExportModelAdmin):
    resource_class = JournalEntryResource
    list_display = ('pk', 'date', 'description', 'transaction')
    inlines = [JournalEntryItemInline]


class JournalEntryInline(admin.StackedInline):
    model = JournalEntry
    extra = 1
    inlines = [JournalEntryItemInline]


class TransactionAdmin(ImportExportModelAdmin):
    resource_class = TransactionResource
    list_display = ('date', 'account', 'amount', 'description', 'category', 'is_closed', 'linked_transaction')
    list_filter = ('account__name', 'date', 'is_closed')
    inlines = [JournalEntryInline]


class PrefillItemInline(admin.TabularInline):
    model = PrefillItem
    extra = 8


class DocSearchInline(admin.TabularInline):
    model = DocSearch
    extra = 8


class PrefillAdmin(admin.ModelAdmin):
    inlines = [PrefillItemInline, DocSearchInline]
    list_display = ('description',)

    def description(self, obj):
        return obj.name

class PaystubAdmin(admin.ModelAdmin):
    list_display = ('title', 'journal_entry')

# Register your models here
admin.site.register(Prefill, PrefillAdmin)
admin.site.register(Account, AccountAdmin)
admin.site.register(AutoTag, AutoTagAdmin)
admin.site.register(CSVProfile, CSVProfileAdmin)
admin.site.register(Transaction, TransactionAdmin)
admin.site.register(JournalEntry, JournalEntryAdmin)
admin.site.register(JournalEntryItem, JournalEntryItemAdmin)
admin.site.register(Reconciliation)
admin.site.register(TaxCharge)
admin.site.register(CSVColumnValuePair)
admin.site.register(Amortization)
admin.site.register(PrefillItem)
admin.site.register(S3File)
admin.site.register(DocSearch)
admin.site.register(Paystub, PaystubAdmin)
admin.site.register(PaystubValue)
admin.site.register(Entity)
