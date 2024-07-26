from django.http import HttpResponse
from django.template.loader import render_to_string
from django.views import View
from django.shortcuts import get_object_or_404
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse
from api.models import Transaction


class TagEntitiesView(LoginRequiredMixin, View):
    login_url = '/login/'
    redirect_field_name = 'next'

    def get(self, request):
        return HttpResponse('new view')