from django.core.exceptions import ValidationError


def non_zero(value):
    if value == 0:
        raise ValidationError("Amount cannot be zero.")
