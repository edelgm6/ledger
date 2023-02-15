from django.contrib import admin
from api.models import Account, Transaction, JournalEntry, JournalEntryItem, AutoTag, CSVProfile

admin.site.register(Account)
admin.site.register(Transaction)
admin.site.register(JournalEntry)
admin.site.register(JournalEntryItem)
admin.site.register(AutoTag)
admin.site.register(CSVProfile)