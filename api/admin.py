from django.contrib import admin
from api.models import Account, Transaction, JournalEntry, JournalEntryItem, AutoTag, CSVProfile



class AccountAdmin(admin.ModelAdmin):
    list_display = ('name','type', 'sub_type', 'csv_profile')

class AutoTagAdmin(admin.ModelAdmin):
    list_display = ('account','search_string','transaction_type')


class CSVProfileAdmin(admin.ModelAdmin):
    list_display = ('name','date','amount','description','category')

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

class JournalEntryAdmin(admin.ModelAdmin):
    list_display = ('pk', 'date', 'description', 'transaction', journal_entries)
    inlines = [
        JournalEntryItemInline,
    ]

class TransactionAdmin(admin.ModelAdmin):
    list_display = ('date', 'account', 'amount', 'description', 'category', 'is_closed')



admin.site.register(Account, AccountAdmin)
admin.site.register(AutoTag, AutoTagAdmin)
admin.site.register(CSVProfile, CSVProfileAdmin)
admin.site.register(Transaction, TransactionAdmin)
admin.site.register(JournalEntry, JournalEntryAdmin)
admin.site.register(JournalEntryItem, JournalEntryItemAdmin)