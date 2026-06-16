"""
Shared CRUD helpers for the settings service layer.

Several settings features (accounts, bill rules, loans) expose the same
create/update/delete shape: copy validated form fields onto a model instance and
save it, or delete by pk while turning a ProtectedError into a friendly message.
This module holds that procedure once; each service wraps the returned
``(obj, error)`` into its own domain Result dataclass.
"""

from typing import Any, Callable, Dict, Optional, Sequence, Tuple, Type, TypeVar, Union

from django.db import transaction as db_transaction
from django.db.models import Model, ProtectedError

M = TypeVar("M", bound=Model)


@db_transaction.atomic
def save_model(
    model_cls: Type[M],
    fields: Sequence[str],
    cleaned_data: Dict[str, Any],
    instance: Optional[M] = None,
    post_save: Optional[Callable[[M], None]] = None,
) -> Tuple[Optional[M], Optional[str]]:
    """Creates or updates ``model_cls`` by copying ``fields`` from
    ``cleaned_data`` (the caller's validated ``form.cleaned_data``); ``instance``
    is the object being edited, or None to create. Runs ``post_save(obj)`` inside
    the transaction when given. Returns ``(obj, None)`` on success or
    ``(None, error)`` if the write fails (the transaction rolls back)."""
    try:
        obj = instance or model_cls()
        for field in fields:
            setattr(obj, field, cleaned_data.get(field))
        obj.save()
        if post_save is not None:
            post_save(obj)
        return obj, None
    except Exception as e:  # pragma: no cover - defensive
        return None, str(e)


def delete_model(
    model_cls: Type[M],
    pk: int,
    *,
    not_found: str,
    protected: Union[str, Callable[[M], str]],
) -> Tuple[Optional[M], Optional[str]]:
    """Deletes ``model_cls`` by pk. Returns ``(obj, None)`` on success,
    ``(None, not_found)`` when it doesn't exist, or ``(obj, message)`` when a
    ProtectedError blocks the delete. ``protected`` is that message, or a
    callable taking the object (for messages that mention it, e.g. its name)."""
    try:
        obj = model_cls.objects.get(pk=pk)
    except model_cls.DoesNotExist:
        return None, not_found
    try:
        obj.delete()
        return obj, None
    except ProtectedError:
        message = protected(obj) if callable(protected) else protected
        return obj, message
