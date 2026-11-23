import os

from django.core.exceptions import ImproperlyConfigured

if os.environ.get("DB_ENGINE") != "postgresql":
    raise ImproperlyConfigured(
        "Tests require PostgreSQL. Set DB_ENGINE=postgresql and configure the DB_* variables."
    )

from .settings import *  # noqa: F403
