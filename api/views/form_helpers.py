"""
Shared value-resolution for hand-rendered Settings forms.

The Settings sections (Accounts, Bill Rules, Loans, Entities, Prefills, Doc
Searches) render their add/edit forms as raw ``<input>``/``<select>`` markup so
they can carry the design-system CSS classes and Alpine bindings — rather than
relying on Django's ``{{ form.field }}`` widget rendering. That means each
template needs a plain ``values`` dict giving the string to display in every
field.

The value for a field comes from one of three sources, in priority order:

1. a bound (re-submitted, usually invalid) ``form`` — echo what the user typed,
   so a validation error doesn't wipe their input;
2. an ``instance`` being edited — its stored values;
3. neither — blank-create defaults.

Each section used to hand-roll this three-branch resolution per field, listing
every field name three times. :func:`resolve_form_values` does it once, driven
by a per-kind field list, so the field names live in a single place.
"""

from typing import Any, Dict, Optional, Sequence


def resolve_form_values(
    instance: Optional[Any],
    form: Optional[Any],
    *,
    text: Sequence[str] = (),
    booleans: Sequence[str] = (),
    fks: Sequence[str] = (),
    dates: Sequence[str] = (),
    defaults: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Resolve the display value for each field of a hand-rendered form.

    Field kinds differ in how each source is read:

    - ``text``: plain scalar (CharField, choice, number). ``None`` renders "".
    - ``booleans``: checkbox; presence of the name in POST means checked.
    - ``fks``: foreign key, rendered as its string id for ``<select>`` compare.
    - ``dates``: date, rendered ISO (``YYYY-MM-DD``) for ``<input type="date">``.

    ``defaults`` supplies non-empty defaults for specific fields; they apply to
    the blank-create branch and as the fallback for a missing key on the bound
    branch (text/date/boolean only — an FK always defaults to "").
    """
    defaults = defaults or {}

    if form is not None and form.is_bound:
        data = form.data
        values: Dict[str, Any] = {}
        for name in (*text, *dates):
            values[name] = data.get(name, defaults.get(name, ""))
        for name in fks:
            values[name] = data.get(name, "")
        for name in booleans:
            values[name] = name in data
        return values

    if instance is not None:
        values = {}
        for name in text:
            value = getattr(instance, name)
            values[name] = "" if value is None else value
        for name in dates:
            value = getattr(instance, name)
            values[name] = value.isoformat() if value else ""
        for name in fks:
            values[name] = str(getattr(instance, f"{name}_id") or "")
        for name in booleans:
            values[name] = getattr(instance, name)
        return values

    values = {}
    for name in (*text, *dates):
        values[name] = defaults.get(name, "")
    for name in fks:
        values[name] = ""
    for name in booleans:
        values[name] = defaults.get(name, False)
    return values
