from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from assignment.models import Card

User = get_user_model()


@pytest.mark.django_db
class TestDueCards:
    def setup_method(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username="due-user")
        self.other_user = User.objects.create_user(username="other-due-user")
        self.now = timezone.now()

    def test_due_cards_returns_only_owned_cards_due_at_or_before_cutoff(self):
        first = Card.objects.create(
            user=self.user,
            card_front="first",
            card_back="back",
            next_review=self.now,
        )
        second = Card.objects.create(
            user=self.user,
            card_front="second",
            card_back="back",
            next_review=self.now + timedelta(hours=1),
        )
        Card.objects.create(
            user=self.user,
            card_front="future",
            card_back="back",
            next_review=self.now + timedelta(days=2),
        )
        Card.objects.create(
            user=self.other_user,
            card_front="other",
            card_back="back",
            next_review=self.now,
        )

        response = self.client.get(
            f"/users/{self.user.pk}/due-cards",
            {"until": (self.now + timedelta(hours=1)).isoformat()},
        )

        assert response.status_code == status.HTTP_200_OK
        assert [card["id"] for card in response.data] == [first.pk, second.pk]

    def test_due_cards_orders_equal_due_dates_by_card_id(self):
        later_id = Card.objects.create(
            user=self.user,
            card_front="later",
            card_back="back",
            next_review=self.now,
        )
        earlier_id = Card.objects.create(
            user=self.user,
            card_front="earlier",
            card_back="back",
            next_review=self.now,
        )

        response = self.client.get(
            f"/users/{self.user.pk}/due-cards",
            {"until": self.now.isoformat()},
        )

        assert response.status_code == status.HTTP_200_OK
        assert [card["id"] for card in response.data] == [
            min(later_id.pk, earlier_id.pk),
            max(later_id.pk, earlier_id.pk),
        ]

    def test_due_cards_rejects_missing_or_invalid_until(self):
        missing = self.client.get(f"/users/{self.user.pk}/due-cards")
        invalid = self.client.get(
            f"/users/{self.user.pk}/due-cards",
            {"until": "not-a-datetime"},
        )

        assert missing.status_code == status.HTTP_400_BAD_REQUEST
        assert invalid.status_code == status.HTTP_400_BAD_REQUEST

    def test_due_cards_returns_not_found_for_unknown_user(self):
        response = self.client.get(
            "/users/999999/due-cards",
            {"until": self.now.isoformat()},
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND
