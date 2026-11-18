# from django.db import models
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.conf import settings


class User(AbstractUser):
    """
    Custom User model that extends the default Django User model.
    This can be used to add additional fields or methods in the future.
    """

    pass

class Card(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="cards"
    )
    card_front = models.TextField()
    card_back = models.TextField()
    times_reviewed = models.PositiveIntegerField(default=0)
    positive_streak = models.PositiveIntegerField(default=0)
    next_review = models.DateTimeField()
