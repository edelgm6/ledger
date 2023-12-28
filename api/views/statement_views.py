from datetime import timedelta
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin
from api.statement import IncomeStatement, BalanceSheet, CashFlowStatement
from api.models import Account
from api import utils

class CashFlowView(LoginRequiredMixin, View):
    login_url = '/login/'
    redirect_field_name = 'next'

    def get(self, request, *args, **kwargs):
        last_month_tuple = utils.get_last_days_of_month_tuples()[0]
        last_day_of_last_month = last_month_tuple[0]
        first_day_of_last_month = utils.get_first_day_of_month_from_date(last_day_of_last_month)
        income_statement = IncomeStatement(
            end_date=last_day_of_last_month,
            start_date=first_day_of_last_month
        )
        end_balance_sheet = BalanceSheet(end_date=last_day_of_last_month)
        start_balance_sheet = BalanceSheet(end_date=first_day_of_last_month + timedelta(days=-1))
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

        template = 'api/views/cash-flow-statement.html'
        return HttpResponse(render_to_string(template, context))

class BalanceSheetView(LoginRequiredMixin, View):
    login_url = '/login/'
    redirect_field_name = 'next'

    def get(self, request, *args, **kwargs):
        last_month_tuple = utils.get_last_days_of_month_tuples()[0]
        last_day_of_last_month = last_month_tuple[0]
        balance_sheet = BalanceSheet(end_date=last_day_of_last_month)

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

        template = 'api/views/balance-sheet.html'
        return HttpResponse(render_to_string(template, context))


class IncomeStatementView(LoginRequiredMixin, View):
    login_url = '/login/'
    redirect_field_name = 'next'

    def get(self, request, *args, **kwargs):
        last_month_tuple = utils.get_last_days_of_month_tuples()[0]
        last_day_of_last_month = last_month_tuple[0]
        first_day_of_last_month = utils.get_first_day_of_month_from_date(last_day_of_last_month)
        income_statement = IncomeStatement(
            end_date=last_day_of_last_month,
            start_date=first_day_of_last_month
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

        template = 'api/views/income-statement.html'
        return HttpResponse(render_to_string(template, context))