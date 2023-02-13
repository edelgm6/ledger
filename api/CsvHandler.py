import csv
import io
from datetime import datetime, date
from api.models import Account, Transaction, AutoTag

class CsvHandler:

    def __init__(self, csv_file, account):
        self.csv_file = csv_file
        self.account = account

    def create_transactions(self):
        account = Account.objects.get(name=self.account)
        # TODO: Eventually this auto-tags will need to filter by CSV handler
        auto_tags = AutoTag.objects.all()

        file = io.StringIO(self.csv_file.read().decode('utf-8'))
        reader = csv.reader(file)
        headers = next(reader)
        transactions_list = []
        for row in reader:
            date_string = row[0]
            date_format = "%m/%d/%Y"
            parsed_date = datetime.strptime(date_string, date_format)
            only_date = parsed_date.date()

            suggested_account = None
            suggested_type = ''
            # TODO: pre-tag the rows instead of referring literally here
            for tag in auto_tags:
                if tag.search_string in row[2].lower():
                    suggested_account = tag.account
                    if tag.transaction_type:
                        suggested_type = tag.transaction_type
                    break

            transactions_list.append(Transaction(
                date=only_date,
                account = account,
                amount = row[5],
                description = row[2],
                category = row[3],
                suggested_account = suggested_account,
                suggested_type = suggested_type
            ))
        self.csv_file.close()
        transactions = Transaction.objects.bulk_create(transactions_list)

        return transactions