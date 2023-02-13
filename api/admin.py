from django.contrib import admin
from api.models import Account, Transaction, JournalEntry, JournalEntryItem, AutoTag

admin.site.register(Account)
admin.site.register(Transaction)
admin.site.register(JournalEntry)
admin.site.register(JournalEntryItem)
admin.site.register(AutoTag)