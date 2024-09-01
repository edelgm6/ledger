import calendar
from datetime import date, datetime, timedelta


def format_datetime_to_string(form_date):
    return form_date.strftime("%Y-%m-%d")


def get_first_day_of_month_from_date(original_date):
    return original_date.replace(day=1)


def get_last_days_of_month_tuples():
    # Get the current year and month
    current_date = datetime.today()
    current_year = current_date.year
    current_month = current_date.month

    # Adjust for the previous month
    # If the current month is January, set to December of the previous year
    if current_month == 1:
        current_year -= 1
        current_month = 12
    else:
        current_month -= 1

    # Create a list of year-month tuples
    # For the current year, include months up to the previous month.
    # For previous years, include all months.
    year_range = range(2023, current_year + 1)
    year_month_tuples = [
        (year, month)
        for year in year_range
        for month in range(1, current_month + 1 if year == current_year else 13)
    ]

    final_days_of_month = []
    for year, month in year_month_tuples:
        # Calculate the first day of the next month
        next_month = month % 12 + 1
        next_month_year = year if month != 12 else year + 1

        # Calculate the last day of the current month
        last_day = date(next_month_year, next_month, 1) - timedelta(days=1)
        final_days_of_month.append((last_day, last_day.strftime("%B %d, %Y")))

    final_days_of_month.reverse()
    return final_days_of_month


def get_last_day_of_last_month():
    current_date = datetime.now()

    # Calculate the year and month for the previous month
    year = current_date.year
    month = current_date.month - 1

    # If it's currently January, adjust to December of the previous year
    if month == 0:
        month = 12
        year -= 1

    # Get the last day of the previous month
    _, last_day = calendar.monthrange(year, month)
    last_day_date = date(year, month, last_day)

    return last_day_date


def is_last_day_of_month(date):
    some_day_next_month = date.replace(day=1) + timedelta(days=32)
    first_of_next_month = some_day_next_month.replace(day=1)
    last_day_of_month = first_of_next_month - timedelta(days=1)
    return date == last_day_of_month
