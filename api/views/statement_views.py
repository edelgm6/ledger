from datetime import timedelta
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse
from api.statement import IncomeStatement, BalanceSheet, CashFlowStatement
from api.models import Account, JournalEntryItem
from api.forms import FromToDateForm
from api import utils


class StatementMixIn:

    def _clear_closed_accounts(self, balances):
        new_balances = []
        for balance in balances:
            if balance.account.is_closed and balance.amount == 0:
                continue
            new_balances.append(balance)
        return new_balances

    def _get_statement_summary_dict(self, statement):

        type_dict = dict(Account.Type.choices)
        summary = {}
        for account_type in Account.Type.values:
            type_total = 0
            account_balances = []
            for sub_type in Account.SUBTYPE_TO_TYPE_MAP[account_type]:
                balances = [balance for balance in statement.balances if balance.account.sub_type == sub_type]
                sub_type_total = sum([balance.amount for balance in balances])
                account_balances.append(
                    {
                        'name': sub_type.label,
                        'balances': self._clear_closed_accounts(balances),
                        'total': sub_type_total
                    }
                )
                type_total += sub_type_total
            label = type_dict[account_type]
            summary[account_type] = {
                'name': label,
                'balances': account_balances,
                'total': type_total
            }

        return summary

    def get_filter_form_html(self, statement_type, from_date, to_date):
        initial_data = {
            # from_date will be None if submitted from balance sheet, so put in arbitrary value
            'date_from': utils.format_datetime_to_string(from_date) if from_date else '2023-01-01',
            'date_to': utils.format_datetime_to_string(to_date)
        }

        template = 'api/filter_forms/from-to-date-form.html'
        context = {
            'filter_form': FromToDateForm(initial=initial_data),
            'get_url': reverse('statements', args=(statement_type,)),
            'statement_type': statement_type
        }
        return render_to_string(template, context)

    def get_income_statement_html(self, from_date, to_date):
        income_statement = IncomeStatement(
            end_date=to_date,
            start_date=from_date
        )

        summary = self._get_statement_summary_dict(statement=income_statement)
        context = {
            'summary': summary,
            'tax_rate': 0 if not income_statement.get_tax_rate() else income_statement.get_tax_rate(),
            'savings_rate': 0 if not income_statement.get_savings_rate() else income_statement.get_savings_rate(),
            'from_date': from_date,
            'to_date': to_date
        }

        template = 'api/content/income-content.html'
        return render_to_string(template, context)

    def get_balance_sheet_html(self, to_date):
        balance_sheet = BalanceSheet(end_date=to_date)
        summary = self._get_statement_summary_dict(statement=balance_sheet)

        context = {
            'summary': summary,
            'cash_percent_assets': balance_sheet.get_cash_percent_assets(),
            'debt_to_equity_ratio': balance_sheet.get_debt_to_equity(),
            'liquid_percent_assets': balance_sheet.get_liquid_assets_percent()
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
            'operations_flows': self._clear_closed_accounts(cash_statement.cash_from_operations_balances),
            'financing_flows': self._clear_closed_accounts(cash_statement.cash_from_financing_balances),
            'investing_flows': self._clear_closed_accounts(cash_statement.cash_from_investing_balances),
            'cash_from_operations': sum([metric.value for metric in cash_statement.summaries if metric.name == 'Cash Flow From Operations']),
            'cash_from_financing': sum([metric.value for metric in cash_statement.summaries if metric.name == 'Cash Flow From Financing']),
            'cash_from_investing': sum([metric.value for metric in cash_statement.summaries if metric.name == 'Cash Flow From Investing']),
            'net_cash_flow': sum([metric.value for metric in cash_statement.summaries if metric.name == 'Net Cash Flow']),
            'levered_cash_flow': cash_statement.get_levered_after_tax_cash_flow(),
            'levered_cash_flow_post_retirement': cash_statement.get_levered_after_tax_after_retirement_cash_flow()
        }

        template = 'api/content/cash-flow-content.html'
        return render_to_string(template, context)


class StatementDetailView(LoginRequiredMixin, View):
    login_url = '/login/'
    redirect_field_name = 'next'

    def get(self, request, account_id, *args, **kwargs):
        from_date = request.GET.get('from_date')
        to_date = request.GET.get('to_date')
        print(from_date)

        template = 'api/tables/statement-detail-table.html'

        journal_entry_items = JournalEntryItem.objects.filter(
            account__pk=account_id, 
            journal_entry__date__gte=from_date,
            journal_entry__date__lte=to_date
        ).select_related('journal_entry__transaction').order_by('journal_entry__date')

        html = render_to_string(
            template,
            {'journal_entry_items': journal_entry_items}
        )
        return HttpResponse(html)


class StatementView(StatementMixIn, LoginRequiredMixin, View):
    login_url = '/login/'
    redirect_field_name = 'next'

    def get(self, request, statement_type, *args, **kwargs):
        form = FromToDateForm(request.GET)
        if form.is_valid():
            from_date = form.cleaned_data['date_from']
            to_date = form.cleaned_data['date_to']
        else:
            last_month_tuple = utils.get_last_days_of_month_tuples()[0]
            last_day_of_last_month = last_month_tuple[0]
            first_day_of_last_month = utils.get_first_day_of_month_from_date(last_day_of_last_month)
            from_date = first_day_of_last_month
            to_date = last_day_of_last_month

        if statement_type == 'income':
            statement_html = self.get_income_statement_html(from_date=from_date,to_date=to_date)
            title = 'Income Statement'
        elif statement_type == 'balance':
            statement_html = self.get_balance_sheet_html(to_date=to_date)
            title = 'Balance Sheet'
        elif statement_type == 'cash':
            statement_html = self.get_cash_flow_html(from_date=from_date,to_date=to_date)
            title = 'Cash Flow Statement'

        context = {
            'statement': statement_html,
            'filter_form': self.get_filter_form_html(statement_type, from_date=from_date, to_date=to_date),
            'title': title
        }

        template = 'api/views/statement.html'
        return HttpResponse(render_to_string(template, context))