from django.contrib import admin
from import_export import resources, fields
from import_export.widgets import ForeignKeyWidget
from import_export.admin import ImportExportModelAdmin
from .models import (
    PrefillItem, Prefill, Amortization, TaxCharge, Account, Transaction,
    JournalEntry, JournalEntryItem, AutoTag, CSVProfile, Reconciliation,
    CSVColumnValuePair
)

# Resource definitions for django-import-export
class JournalEntryItemResource(resources.ModelResource):
    journal_entry = fields.Field(
        column_name='journal_entry',
        attribute='journal_entry',
        widget=ForeignKeyWidget(JournalEntry, 'id'))

    class Meta:
        model = JournalEntryItem
        fields = ('journal_entry', 'type', 'amount', 'account')

class JournalEntryResource(resources.ModelResource):
    transaction = fields.Field(
        column_name='transaction',
        attribute='transaction',
        widget=ForeignKeyWidget(Transaction, 'id'))

    class Meta:
        model = JournalEntry
        fields = ('id', 'date', 'description', 'transaction')
        export_order = ('id', 'date', 'description', 'transaction')

class TransactionResource(resources.ModelResource):
    class Meta:
        model = Transaction
        fields = ('id', 'date', 'account', 'amount', 'description', 'category', 'is_closed', 'linked_transaction')

# Admin definitions
class AccountAdmin(admin.ModelAdmin):
    list_display = ('name', 'type', 'sub_type', 'csv_profile')

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

class PrefillAdmin(admin.ModelAdmin):
    inlines = [PrefillItemInline]
    list_display = ('description',)

    def description(self, obj):
        return obj.name

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