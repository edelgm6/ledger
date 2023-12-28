from datetime import timedelta
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin
from api.statement import IncomeStatement, BalanceSheet, CashFlowStatement
from api.models import Account
from api.forms import FromToDateForm
from api import utils

class FilterFormMixIn:

    def get_filter_form_html(self, statement_type):
        template = 'api/filter_forms/from-to-date-form.html'
        context = {'filter_form': FromToDateForm()}
        return render_to_string(template, context)

    def get_income_statement_html(self, from_date, to_date):
        income_statement = IncomeStatement(
            end_date=to_date,
            start_date=from_date
        )

        income_balances = [balance for balance in income_statement.balances if balance.account_type == Account.Type.INCOME]
        expense_balances = [balance for balance in income_statement.balances if balance.account_type == Account.Type.EXPENSE]
        net_income = sum([balance.amount for balance in income_statement.balances if balance.account_sub_type == Account.SubType.RETAINED_EARNINGS])
        net_income = sum([balance.amount for balance in income_statement.balances if balance.account_sub_type == Account.SubType.RETAINED_EARNINGS])
        total_income = sum([metric.value for metric in income_statement.summaries if metric.name == 'Income'])
        total_expense = sum([metric.value for metric in income_statement.summaries if metric.name == 'Expense'])

        context = {
            'income_balances': income_balances,
            'expense_balances': expense_balances,
            'net_income': net_income,
            'income_statement': income_statement,
            'total_income': total_income,
            'total_expense': total_expense
        }

        template = 'api/content/income-content.html'
        return render_to_string(template, context)

    def get_balance_sheet_html(self, to_date):
        balance_sheet = BalanceSheet(end_date=to_date)

        assets_balances = [balance for balance in balance_sheet.balances if balance.account_type == Account.Type.INCOME]
        liabilities_balances = [balance for balance in balance_sheet.balances if balance.account_type == Account.Type.EXPENSE]
        equity_balances = [balance for balance in balance_sheet.balances if balance.account_sub_type == Account.SubType.RETAINED_EARNINGS]
        total_assets = sum([metric.value for metric in balance_sheet.summaries if metric.name == 'Asset'])
        total_liabilities = sum([metric.value for metric in balance_sheet.summaries if metric.name == 'Liability'])
        total_equity = sum([metric.value for metric in balance_sheet.summaries if metric.name == 'Equity'])
        for metric in balance_sheet.summaries:
            print(metric.name)

        context = {
            'assets_balances': assets_balances,
            'liabilities_balances': liabilities_balances,
            'equity_balances': equity_balances,
            'total_assets': total_assets,
            'total_liabilities': total_liabilities,
            'total_equity': total_equity
        }

        template = 'api/content/balance-sheet-content.html'
        return render_to_string(template, context)

    def get_cash_flow_html(self, from_date, to_date):
        income_statement = IncomeStatement(end_date=to_date, start_date=from_date)
        end_balance_sheet = BalanceSheet(end_date=to_date)
        start_balance_sheet = BalanceSheet(end_date=from_date + timedelta(days=-1))
        cash_statement = CashFlowStatement(
            income_statement=income_statement,
            start_balance_sheet=start_balance_sheet,
            end_balance_sheet=end_balance_sheet
        )

        context = {
            'operations_flows': cash_statement.cash_from_operations_balances,
            'financing_flows': cash_statement.cash_from_financing_balances,
            'investing_flows': cash_statement.cash_from_investing_balances,
            'cash_from_operations': sum([metric.value for metric in cash_statement.summaries if metric.name == 'Cash Flow From Operations']),
            'cash_from_financing': sum([metric.value for metric in cash_statement.summaries if metric.name == 'Cash Flow From Investing']),
            'cash_from_investing': sum([metric.value for metric in cash_statement.summaries if metric.name == 'Cash Flow From Financing']),
            'net_cash_flow': sum([metric.value for metric in cash_statement.summaries if metric.name == 'Net Cash Flow'])
        }

        template = 'api/content/cash-flow-content.html'
        return render_to_string(template, context)

class StatementFilterView(FilterFormMixIn, LoginRequiredMixin, View):
    login_url = '/login/'
    redirect_field_name = 'next'

    def get(self, request, statement_type):
        form = FromToDateForm(request.GET)
        from_date = form.cleaned_data['from_date']
        to_date = form.cleaned_data['to_date']

        if form.is_valid():
            if statement_type == 'income':
                html = self.get_income_statement_html(from_date=from_date,to_date=to_date)
            elif statement_type == 'balance':
                html = self.get_balance_sheet_html(to_date=to_date)
            elif statement_type == 'cash':
                html = self.get_cash_flow_html(from_date=from_date,to_date=to_date)

        return HttpResponse(html)

class StatementView(LoginRequiredMixin, FilterFormMixIn, View):
    login_url = '/login/'
    redirect_field_name = 'next'

    def get(self, request, statement_type, *args, **kwargs):

        last_month_tuple = utils.get_last_days_of_month_tuples()[0]
        last_day_of_last_month = last_month_tuple[0]
        first_day_of_last_month = utils.get_first_day_of_month_from_date(last_day_of_last_month)

        if statement_type == 'income':
            statement_html = self.get_income_statement_html(from_date=first_day_of_last_month,to_date=last_day_of_last_month)
            title = 'Income Statement'
        elif statement_type == 'balance':
            statement_html = self.get_balance_sheet_html(to_date=last_day_of_last_month)
            title = 'Balance Sheet'
        elif statement_type == 'cash':
            statement_html = self.get_cash_flow_html(from_date=first_day_of_last_month,to_date=last_day_of_last_month)
            title = 'Cash Flow Statement'

        context = {
            'statement': statement_html,
            'filter_form': self.get_filter_form_html(statement_type),
            'title': title
        }

        template = 'api/views/statement.html'
        return HttpResponse(render_to_string(template, context))

# class BalanceSheetView(LoginRequiredMixin, View):
#     login_url = '/login/'
#     redirect_field_name = 'next'

#     def get(self, request, *args, **kwargs):
#         pass


# class IncomeStatementView(LoginRequiredMixin, View):
#     login_url = '/login/'
#     redirect_field_name = 'next'

#     def get(self, request, *args, **kwargs):
#         pass