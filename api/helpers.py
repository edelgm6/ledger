import datetime

def is_last_day_of_month(date):
    last_day_of_month = (date.replace(day=1) + datetime.timedelta(days=32)).replace(day=1) - datetime.timedelta(days=1)
    return date == last_day_of_month