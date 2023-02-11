import csv
import io
from datetime import datetime, date
from api.models import Account, Transaction

class CsvHandler:

    def __init__(self, csv_file, account):
        self.csv_file = csv_file
        self.account = account

    def create_transactions(self):
        account = Account.objects.get(name=self.account)

        file = io.StringIO(self.csv_file.read().decode('utf-8'))
        reader = csv.reader(file)
        headers = next(reader)
        transactions_list = []
        for row in reader:
            date_string = row[0]
            date_format = "%m/%d/%Y"
            parsed_date = datetime.strptime(date_string, date_format)
            only_date = parsed_date.date()

            transactions_list.append(Transaction(
                date=only_date,
                account = account,
                amount = row[5],
                description = row[2],
                category = row[3]
            ))
        self.csv_file.close()
        transactions = Transaction.objects.bulk_create(transactions_list)

        return transactions