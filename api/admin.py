from django.contrib import admin
from api.models import PrefillItem, Prefill, Amortization, TaxCharge, Account, Transaction, JournalEntry, JournalEntryItem, AutoTag, CSVProfile, Reconciliation, CSVColumnValuePair

class AccountAdmin(admin.ModelAdmin):
    list_display = ('name','type', 'sub_type', 'csv_profile')

class AutoTagAdmin(admin.ModelAdmin):
    list_display = ('account','search_string','transaction_type')

class CSVProfileAdmin(admin.ModelAdmin):
    list_display = ('name','date','description','category')

class JournalEntryItemAdmin(admin.ModelAdmin):
    list_display = ('journal_entry','type','amount','account')

# TODO: Possible to get this to show up on each individual line?
@admin.display(description='Journal Entries')
def journal_entries(journal_entry):
    journal_entry_items = JournalEntryItem.objects.filter(journal_entry=journal_entry).order_by('type','-amount')
    entries_list = ''
    for journal_entry_item in journal_entry_items:
        entries_list += journal_entry_item.type + ' ' + str(journal_entry_item.amount) + '\n\n'

    return entries_list

class JournalEntryItemInline(admin.TabularInline):
    model = JournalEntryItem
    extra = 1

class JournalEntryAdmin(admin.ModelAdmin):
    list_display = ('pk', 'date', 'description', 'transaction', journal_entries)
    inlines = [
        JournalEntryItemInline,
    ]

class JournalEntryInline(admin.StackedInline):
    model = JournalEntry
    extra = 1
    inlines = [
        JournalEntryItemInline,
    ]

class TransactionAdmin(admin.ModelAdmin):
    list_display = ('date', 'account', 'amount', 'description', 'category', 'is_closed','linked_transaction')
    list_filter = ('account__name','date','is_closed')
    inlines = [
        JournalEntryInline,
    ]

class JournalEntryAdmin(admin.ModelAdmin):
    list_display = ('pk', 'date', 'description', 'transaction', journal_entries)
    inlines = [
        JournalEntryItemInline,
    ]

class PrefillItemInline(admin.TabularInline):
    model = PrefillItem
    extra = 8  # Number of empty forms to display

class PrefillAdmin(admin.ModelAdmin):
    inlines = [PrefillItemInline]
    list_display = ('description',)

    def description(self, obj):
        return obj.name

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