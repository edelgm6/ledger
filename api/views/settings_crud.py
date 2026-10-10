"""Shared POST handling for the Settings sections' create/update/delete.

Six Settings sections -- Accounts, Entities, Auto Tags, CSV Profiles, Prefills
and Bill Rules -- had POST handlers that were identical apart from four names:
the model, the form, the pair of service functions, and the noun used for both
the service Result's object attribute and the ``_render_content`` keyword.

The service layer below them was already deduplicated for the same reason (see
``api/services/crud.py``). This does the same for the view layer: the handler
lives here once and each section declares its four names.

Deliberately *not* absorbed: the Doc Searches handler. It is scoped to a parent
prefill, so its ``post()`` takes an extra id and threads that parent through
every render. Forcing it in would mean teaching this class about parent
scoping for one caller.
"""

from typing import Any, Optional, Type

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Model
from django.forms import Form
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.views import View


class SettingsCrudView(LoginRequiredMixin, View):
    """Create/update/delete for one Settings section.

    ``LoginRequiredMixin`` is applied here rather than on each subclass, so a
    section cannot lose authentication by forgetting to repeat it.

    Subclasses declare:
        noun           the field name used by both the service Result and the
                       ``_render_content`` keyword (e.g. "entity")
        model          for looking up the instance being edited
        form_class     the bound form
        pk_url_kwarg   the URL capture holding the pk (e.g. "entity_id")

    and implement ``save``, ``delete`` and ``_render_content``.
    """

    login_url = "/login/"
    redirect_field_name = "next"

    noun: str = ""
    model: Optional[Type[Model]] = None
    form_class: Optional[Type[Form]] = None
    pk_url_kwarg: str = "pk"

    # --- subclass hooks ---------------------------------------------------

    def save(self, cleaned_data: dict, instance: Optional[Model]) -> Any:
        """Calls the section's save service. Returns its Result dataclass."""
        raise NotImplementedError

    def delete(self, pk: Optional[int]) -> Any:
        """Calls the section's delete service. Returns its Result dataclass."""
        raise NotImplementedError

    def _render_content(self, **kwargs) -> str:
        """Renders the section's swappable fragment."""
        raise NotImplementedError

    # --- shared handler --------------------------------------------------

    def _content(self, obj: Optional[Model] = None, **kwargs) -> str:
        """Renders the fragment, passing `obj` under the section's own keyword
        so each ``_render_content`` keeps a readable, typed signature."""
        return self._render_content(**{self.noun: obj}, **kwargs)

    def _result_obj(self, result: Any) -> Optional[Model]:
        """The object off a Result dataclass, whose attribute is noun-named."""
        return getattr(result, self.noun, None)

    def post(self, request, **kwargs) -> HttpResponse:
        pk = kwargs.get(self.pk_url_kwarg)

        if request.POST.get("action") == "delete":
            result = self.delete(pk)
            if result.success:
                return HttpResponse(self._content(change="delete"))
            obj = self._result_obj(result)
            return HttpResponse(
                self._content(
                    obj=obj,
                    error=result.error,
                    selected_id=obj.id if obj else None,
                )
            )

        if pk:
            instance = get_object_or_404(self.model, pk=pk)
            form = self.form_class(request.POST, instance=instance)
            change = "update"
        else:
            instance = None
            form = self.form_class(request.POST)
            change = "create"

        if not form.is_valid():
            return HttpResponse(
                self._content(
                    obj=instance,
                    form=form,
                    selected_id=instance.id if instance else None,
                )
            )

        result = self.save(form.cleaned_data, instance=instance)
        if not result.success:
            return HttpResponse(
                self._content(
                    obj=instance,
                    form=form,
                    error=result.error,
                    selected_id=instance.id if instance else None,
                )
            )

        saved = self._result_obj(result)
        return HttpResponse(
            self._content(
                obj=saved,
                change=change,
                selected_id=saved.id if saved else None,
            )
        )
