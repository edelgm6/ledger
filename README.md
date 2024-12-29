# Ledger

Ledger is a personal accounting tool to generate the three accounting statements (income statement, balance sheet, statement of cash flows).

## General setup

Once you've hosted Ledger, you'll need to do the following:
* Create an admin user via Django's `python manage.py createsuperuser`
* Log into the Admin page to generate some accounts. At the very least, you'll need one of each `Special type`

```
# local_settings.py


from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = 'WHATEVER'

# AWS credentials
AWS_ACCESS_KEY_ID = '[YOUR_KEY]'
AWS_SECRET_ACCESS_KEY = '[YOUR SECRET KEY]'
AWS_STORAGE_BUCKET_NAME = '[BUCKET NAME]'

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

CORS_ALLOWED_ORIGINS = [
    "http://localhost:8000",
]

```


