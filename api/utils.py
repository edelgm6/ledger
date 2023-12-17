import calendar
from datetime import date, datetime, timedelta

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
    last_day_of_month = (date.replace(day=1) + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    return date == last_day_of_month