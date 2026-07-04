from django.test import TestCase
from api.models import CSVColumnValuePair, Transaction, AutoTag
from api.tests.testing_factories import CSVProfileFactory, AccountFactory, PrefillFactory

csv_data = [
    ["Account Number", "Investment Name", "Symbol", "Shares", "Share Price", "Total Value"],
    ["21281793", "VANGUARD FTSE DEVELOPED MKTS ETF", "VEA", "903.1210", "47.9000", "43259.50"],
    ["21281793", "VANGUARD FTSE EMERGING MARKETS ETF", "VWO", "18.0000", "41.1000", "739.80"],
    ["21281793", "VANGUARD TOTAL STOCK MARKET INDEX ADMIRAL CL", "VTSAX", "4304.0750", "115.49", "497077.62"],
    ["21281793", "VANGUARD TOTAL INTL STOCK INDEX ADMIRAL CL", "VTIAX", "3190.0150", "31.13", "99305.17"],
    ["21281793", "SCHWAB S&P 500 INDEX", "SWPPX", "3420.8070", "73.1000", "250060.99"],
    ["21281793", "VANGUARD TOTAL INTL STOCK INDEX FUND ETF", "VXUS", "866.1690", "57.9600", "50203.16"],
    ["21281793", "SCHWAB INTL INDEX", "SWISX", "589.0900", "22.5600", "13289.87"],
    ["21281793", "VANGUARD DIVIDEND APPRECIATION ETF", "VIG", "62.1780", "170.4000", "10595.13"],
    ["21281793", "SCHWAB U S BROAD MARKET ETF", "SCHB", "5317.1670", "55.6700", "296006.69"],
    ["21281793", "SCHWAB U S DIVIDEND EQUITY ETF", "SCHD", "43.0000", "76.1300", "3273.59"],
    ["21281793", "VANGUARD TOTAL STOCK MARKET ETF", "VTI", "371.6756", "237.2200", "88168.89"],
    ["21281793", "SCHWAB U S SMALL CAP ETF", "SCHA", "1905.9640", "47.2400", "90037.74"],
    [],
    [],
    [],
    [],
    ['Account Number', 'Trade Date', 'Settlement Date', 'Transaction Type', 'Transaction Description', 'Investment Name', 'Symbol', 'Shares', 'Share Price', 'Principal Amount', 'Commissions and Fees', 'Net Amount', 'Inflow', 'Outflow', 'Accrued Interest', 'Account Type',''],
    ['21281793', '2023-12-01', '2023-12-01', 'Sweep in', 'Sweep Into Settlement Fund', 'VANGUARD FEDERAL MONEY MARKET INVESTOR CL', 'VMFXX', '0', '1', '-4000', '0', '-4000', '', '-4000', '0', 'CASH',''],
    ['21281793', '2023-12-11', '2023-12-11', 'Sweep out', 'Sweep Into Settlement Fund', 'VANGUARD FEDERAL MONEY MARKET INVESTOR CL', 'VMFXX', '0', '1', '-7772.83', '0', '-7772.83', '', '-7772.83', '0', 'CASH',''],
    ['21281793', '2023-12-18', '2023-12-18', 'Reinvestment', 'Sweep Into Settlement Fund', 'VANGUARD FEDERAL MONEY MARKET INVESTOR CL', 'VMFXX', '0', '1', '-1883.59', '0', '-1883.59', '', '-1883.59', '0', 'CASH',''],
    ['21281793', '2023-12-21', '2023-12-21', 'Buy', 'Sweep Into Settlement Fund', 'VANGUARD FEDERAL MONEY MARKET INVESTOR CL', 'VMFXX', '0', '1', '-3386.98', '0', '-3386.98', '', '-3386.98', '0', 'CASH',''],
    ['21281793', '2023-12-22', '2023-12-22', 'Sweep in', 'Sweep Into Settlement Fund', 'VANGUARD FEDERAL MONEY MARKET INVESTOR CL', 'VMFXX', '0', '1', '-57.32', '0', '-57.32', '', '-57.32', '0', 'CASH',''],
    ['21281793', '2023-12-27', '2023-12-27', 'Sweep in', 'Sweep Into Settlement Fund', 'VANGUARD FEDERAL MONEY MARKET INVESTOR CL', 'VMFXX', '0', '1', '-964.38', '0', '-964.38', '', '-964.38', '0', 'CASH',''],
    ['21281793', '2023-12-29', '2023-12-29', 'Dividend Received', 'Dividends', 'VANGUARD FEDERAL MONEY MARKET INVESTOR CL', 'VMFXX', '0', '0', '-51.84', '0', '-51.84', '', '51.84', '0', 'CASH',''],
    ['21281793', '2023-12-29', '2023-12-29', 'Funds Received', 'Transfer', 'VANGUARD FEDERAL MONEY MARKET INVESTOR CL', 'VMFXX', '0', '0', '-51.84', '0', '-51.84', '', '4000', '0', 'CASH',''],
    ['21281793', '2023-12-29', '2023-12-29', 'Funds Withdrawn', 'Brokerage Fee', 'VANGUARD FEDERAL MONEY MARKET INVESTOR CL', 'VMFXX', '0', '0', '-51.84', '0', '-51.84', '', '-1000', '0', 'CASH',''],
]

class CSVProfileModelTest(TestCase):

    def setUp(self):
        # Assuming CSVColumnValuePairFactory creates CSVColumnValuePair instances
        self.csv_profile = CSVProfileFactory(
            name="Vanguard",
            date="Trade Date",
            description="Transaction Description",
            category="Transaction Type",
            clear_prepended_until_value="Settlement Date",
            inflow="Inflow",
            outflow="Outflow",
            # date_format="%d-%Y-%m"
            date_format="%Y-%m-%d"
        )
        pair = CSVColumnValuePair.objects.create(
            column="Transaction Type",
            value="Buy"
        )
        self.csv_profile.clear_values_column_pairs.add(pair)
        pair = CSVColumnValuePair.objects.create(
            column="Transaction Type",
            value="Sweep out"
        )
        self.csv_profile.clear_values_column_pairs.add(pair)
        pair = CSVColumnValuePair.objects.create(
            column="Transaction Type",
            value="Sweep in"
        )
        self.csv_profile.clear_values_column_pairs.add(pair)
        pair = CSVColumnValuePair.objects.create(
            column="Transaction Type",
            value="Reinvestment"
        )
        self.csv_profile.clear_values_column_pairs.add(pair)
        pair = CSVColumnValuePair.objects.create(
            column="Keyerror test",
            value="Reinvestment"
        )
        self.csv_profile.clear_values_column_pairs.add(pair)

    def test_csv_profile_creation(self):
        """Test the creation of a CSVProfile instance."""
        self.assertIsNotNone(self.csv_profile.pk, "Should create a CSVProfile instance")

    def test_csv_profile_str_representation(self):
        """Test the string representation of the CSVProfile model."""
        self.assertEqual(str(self.csv_profile), "Vanguard", "String representation should be the name of the CSVProfile")

    def test_clear_prepended_rows(self):
        copied_list = list(csv_data)

        cleared_csv = self.csv_profile._clear_prepended_rows(copied_list)
        self.assertEqual(len(cleared_csv),10)
        self.assertTrue('Total Value' not in cleared_csv[0])
        self.assertTrue('Trade Date' in cleared_csv[0])

        copied_list = list(csv_data)
        self.csv_profile.clear_prepended_until_value = ''
        self.csv_profile.save()
        cleared_csv = self.csv_profile._clear_prepended_rows(copied_list)
        self.assertEqual(len(cleared_csv),27)
        self.assertTrue('Total Value' in cleared_csv[0])
        self.assertTrue('Trade Date' not in cleared_csv[0])

    def test_lists_turned_into_dicts(self):
        copied_list = list(csv_data)

        cleared_csv = self.csv_profile._clear_prepended_rows(copied_list)
        list_of_dicts = self.csv_profile._list_of_lists_to_list_of_dicts(cleared_csv)
        self.assertEqual(len(list_of_dicts),9)
        for row in list_of_dicts:
            self.assertTrue(isinstance(row, dict))

    def test_clear_extraneous_rows(self):
        copied_list = list(csv_data)

        cleared_csv = self.csv_profile._clear_prepended_rows(copied_list)
        list_of_dicts = self.csv_profile._list_of_lists_to_list_of_dicts(cleared_csv)
        cleared_list = self.csv_profile._clear_extraneous_rows(list_of_dicts)
        self.assertEqual(len(cleared_list),3)

    def test_get_coalesced_amount(self):
        test_row = {
            'Inflow': 1000,
            'Outflow': '',
        }
        value = self.csv_profile._get_coalesced_amount(test_row)
        self.assertEqual(value, 1000)
        test_row = {
            'Inflow': '',
            'Outflow': 500
        }
        value = self.csv_profile._get_coalesced_amount(test_row)
        self.assertEqual(value, 500)

    def test_date_string_formatted(self):
        test_date = '31-2023-03'
        self.csv_profile.date_format = "%d-%Y-%m"
        self.csv_profile.save()
        formatted_date = self.csv_profile._get_formatted_date(test_date)
        self.assertEqual(formatted_date, '2023-03-31')

    def test_autotags_applied_to_transactions(self):
        copied_list = list(csv_data)
        copied_list.append({})
        account = AccountFactory()

        fee_account = AccountFactory()
        prefill = PrefillFactory()
        AutoTag.objects.create(
            search_string='fee',
            account=fee_account,
            prefill=prefill
        )
        AutoTag.objects.create(
            search_string='dividends',
            account=AccountFactory(),
            transaction_type=Transaction.TransactionType.INCOME
        )

        self.csv_profile.create_transactions_from_csv(copied_list, account)
        transaction = Transaction.objects.get(description='Brokerage Fee')
        self.assertEqual(transaction.prefill, prefill)
        self.assertEqual(transaction.suggested_account, fee_account)
        self.assertEqual(transaction.type, Transaction.TransactionType.PURCHASE)
        transaction = Transaction.objects.get(description='Dividends')
        self.assertEqual(transaction.type, Transaction.TransactionType.INCOME)


    # search_string = models.CharField(max_length=20)
    # account = models.ForeignKey('Account',on_delete=models.CASCADE,null=True,blank=True)
    # transaction_type = models.CharField(max_length=25,choices=Transaction.TransactionType.choices,blank=True)
    # prefill = models.ForeignKey('Prefill',on_delete=models.CASCADE,null=True,blank=True)