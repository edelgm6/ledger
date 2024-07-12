import csv
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.views import View
from django.shortcuts import render
from django.contrib.auth.mixins import LoginRequiredMixin
from api.forms import UploadTransactionsForm, WalletForm, DocumentForm
from api.statement import Trend
from api import utils


class UploadTransactionsView(View):

    form = UploadTransactionsForm
    template = 'api/views/upload-transactions.html'
    form_template = 'api/entry_forms/upload-form.html'
    textract_form_template = 'api/entry_forms/textract-form.html'

    def get_textract_form_html(self):
        form = DocumentForm()
        return render_to_string(self.textract_form_template, {'form': form})

    def get(self, request):
        form_html = render_to_string(self.form_template, {'form': self.form()})
        textract_form_html = self.get_textract_form_html()
        return render(request, self.template, {'form': form_html, 'textract_form': textract_form_html})

    def post(self, request):
        form = self.form(request.POST, request.FILES)
        if form.is_valid():
            transactions_count = form.save()
            form_html = render_to_string(
                self.form_template, 
                {
                    'form': form,
                    'count': transactions_count,
                    'account': form.cleaned_data['account']
                }
            )
            return HttpResponse(form_html)

# ------------------Wallet Transactions View-----------------------

class IndexView(LoginRequiredMixin, View):
    login_url = '/login/'
    redirect_field_name = 'next'
    template = 'api/views/index.html'
    form_template = 'api/entry_forms/wallet-form.html'
    form_class = WalletForm

    def get(self, request, *args, **kwargs):
        context = {
            'form': render_to_string(self.form_template, {'form': self.form_class()})
        }
        return render(request, self.template, context)

    def post(self, request, *args, **kwargs):
        form = self.form_class(request.POST)
        if form.is_valid():
            transaction = form.save()
            success_template = 'api/content/wallet-content.html'
            context = {
                'form': render_to_string(self.form_template, {'form': self.form_class()}),
                'created_transaction': transaction
            }
            html = render_to_string(success_template, context)
            return HttpResponse(html)
        print(form.errors)

class TrendView(LoginRequiredMixin, View):
    login_url = '/login/'
    redirect_field_name = 'next'

    def get(self, request, *args, **kwargs):
        start_date = '2022-12-01'
        end_date = utils.get_last_day_of_last_month()

        trends = Trend(start_date,end_date).get_balances()

        trends_csv = [
            ['Date','Account','Type','Amount','Account Type','Account Sub-type']
        ]

        for trend in trends:
            trends_csv.append([
                str(trend.date),
                trend.account,
                trend.type,
                str(trend.amount),
                trend.account.type,
                trend.account.sub_type
            ])

        # Create the HttpResponse object with the appropriate CSV header.
        response = HttpResponse(
            content_type='text/csv',
            headers={'Content-Disposition': 'attachment; filename="balances.csv"'},
        )

        writer = csv.writer(response)
        for row in trends_csv:
            writer.writerow(row)

        return response

