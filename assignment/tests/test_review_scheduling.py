from datetime import timedelta
from uuid import uuid4
from unittest.mock import MagicMock, patch

import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from assignment.models import Card, Review

User = get_user_model()


@pytest.mark.django_db
class TestReviewScheduling:
    def setup_method(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username="review-user")
        self.card = Card.objects.create(
            user=self.user,
            card_front="front",
            card_back="back",
            positive_streak=9,
            next_review=timezone.now(),
        )

    def post_review(self, review_score):
        return self.client.post(
            "/reviews",
            {
                "user": self.user.pk,
                "card": self.card.pk,
                "review_score": review_score,
                "idempotency_key": str(uuid4()),
            },
            format="json",
        )

    def test_score_zero_schedules_one_minute_and_records_failure(self):
        self.card.positive_streak = 4
        self.card.save(update_fields=["positive_streak"])

        response = self.post_review(0)

        assert response.status_code == status.HTTP_200_OK
        card = Card.objects.get(pk=self.card.pk)
        assert card.times_reviewed == 1
        assert card.last_failure == 1
        assert card.positive_streak == 4
        assert card.next_review - timezone.now() < timedelta(minutes=2)
        assert Review.objects.get(card=card).review_score == 0

    def test_first_score_one_review_waits_one_day_at_midnight(self):
        self.card.positive_streak = 0
        self.card.save(update_fields=["positive_streak"])

        response = self.post_review(1)

        card = Card.objects.get(pk=self.card.pk)
        expected = timezone.localtime(timezone.now()).replace(
            hour=0, minute=0, second=0, microsecond=0
        ) + timedelta(days=1)
        assert response.status_code == status.HTTP_200_OK
        assert card.positive_streak == 1
        assert card.times_reviewed == 1
        assert card.next_review == expected

    def test_first_score_two_review_waits_two_days_at_midnight(self):
        self.card.positive_streak = 0
        self.card.save(update_fields=["positive_streak"])

        response = self.post_review(2)

        card = Card.objects.get(pk=self.card.pk)
        expected = timezone.localtime(timezone.now()).replace(
            hour=0, minute=0, second=0, microsecond=0
        ) + timedelta(days=2)
        assert response.status_code == status.HTTP_200_OK
        assert card.positive_streak == 1
        assert card.times_reviewed == 1
        assert card.next_review == expected

    def test_positive_review_interval_remains_monotonic_after_cap(self):
        easy_response = self.post_review(2)
        assert easy_response.status_code == status.HTTP_200_OK
        easy_next_review = self.card.__class__.objects.get(pk=self.card.pk).next_review

        effort_response = self.post_review(1)
        assert effort_response.status_code == status.HTTP_200_OK
        effort_next_review = self.card.__class__.objects.get(pk=self.card.pk).next_review

        assert easy_next_review == effort_next_review
        assert effort_next_review - timezone.now() <= timedelta(days=1024)

    def test_repeated_same_idempotency_key_is_not_applied_twice(self):
        key = str(uuid4())
        payload = {
            "user": self.user.pk,
            "card": self.card.pk,
            "review_score": 2,
            "idempotency_key": key,
        }

        first = self.client.post("/reviews", payload, format="json")
        second = self.client.post("/reviews", payload, format="json")

        card = Card.objects.get(pk=self.card.pk)
        assert first.status_code == status.HTTP_200_OK
        assert second.status_code == status.HTTP_200_OK
        assert second.data == first.data
        assert card.positive_streak == 10
        assert card.times_reviewed == 1
        assert Review.objects.filter(idempotency_key=key).count() == 1

    def test_same_idempotency_key_with_conflicting_data_returns_conflict(self):
        key = str(uuid4())
        payload = {
            "user": self.user.pk,
            "card": self.card.pk,
            "review_score": 2,
            "idempotency_key": key,
        }
        first = self.client.post("/reviews", payload, format="json")

        payload["review_score"] = 1
        conflict = self.client.post("/reviews", payload, format="json")

        assert first.status_code == status.HTTP_200_OK
        assert conflict.status_code == status.HTTP_409_CONFLICT
        assert conflict.data["detail"] == "There is a conflict in the data received."

    def test_card_owned_by_another_user_is_rejected(self):
        other_user = User.objects.create_user(username="other-review-user")
        key = str(uuid4())

        response = self.client.post(
            "/reviews",
            {
                "user": other_user.pk,
                "card": self.card.pk,
                "review_score": 1,
                "idempotency_key": key,
            },
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["detail"] == "Card does not belong to the supplied user"

    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("review_score", -1),
            ("review_score", 3),
            ("idempotency_key", "x" * 65),
        ],
    )
    def test_invalid_review_fields_are_rejected(self, field, value):
        payload = {
            "user": self.user.pk,
            "card": self.card.pk,
            "review_score": 1,
            "idempotency_key": str(uuid4()),
        }
        payload[field] = value

        response = self.client.post("/reviews", payload, format="json")

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_unknown_user_card_and_missing_fields_are_rejected(self):
        unknown_user = self.client.post(
            "/reviews",
            {
                "user": 999999,
                "card": self.card.pk,
                "review_score": 1,
                "idempotency_key": str(uuid4()),
            },
            format="json",
        )
        unknown_card = self.client.post(
            "/reviews",
            {
                "user": self.user.pk,
                "card": 999999,
                "review_score": 1,
                "idempotency_key": str(uuid4()),
            },
            format="json",
        )
        missing_field = self.client.post(
            "/reviews",
            {"user": self.user.pk, "card": self.card.pk, "review_score": 1},
            format="json",
        )

        assert unknown_user.status_code == status.HTTP_400_BAD_REQUEST
        assert unknown_card.status_code == status.HTTP_400_BAD_REQUEST
        assert missing_field.status_code == status.HTTP_400_BAD_REQUEST

    def test_integrity_error_matching_existing_review_returns_saved_result(self):
        key = str(uuid4())
        existing = Review(
            idempotency_key=key,
            card=self.card,
            user=self.user,
            review_score=1,
            next_review=timezone.now() + timedelta(days=1),
        )
        initial_lookup = MagicMock()
        initial_lookup.filter.return_value.first.return_value = None

        catch_lookup = MagicMock()
        catch_lookup.first.return_value = existing

        with (
            patch.object(Review.objects, "select_for_update", return_value=initial_lookup),
            patch.object(Review.objects, "filter", return_value=catch_lookup),
            patch.object(Review.objects, "create", side_effect=IntegrityError),
        ):
            response = self.post_review_with_key(1, key)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["next_review"] == existing.next_review

    def test_integrity_error_conflicting_existing_review_returns_conflict(self):
        key = str(uuid4())
        existing = Review(
            idempotency_key=key,
            card=self.card,
            user=self.user,
            review_score=1,
            next_review=timezone.now() + timedelta(days=1),
        )
        initial_lookup = MagicMock()
        initial_lookup.filter.return_value.first.return_value = None

        catch_lookup = MagicMock()
        catch_lookup.first.return_value = existing

        with (
            patch.object(Review.objects, "select_for_update", return_value=initial_lookup),
            patch.object(Review.objects, "filter", return_value=catch_lookup),
            patch.object(Review.objects, "create", side_effect=IntegrityError),
        ):
            response = self.post_review_with_key(2, key)

        assert response.status_code == status.HTTP_409_CONFLICT
        assert response.data["detail"] == "There is a conflict in the data received."

    def post_review_with_key(self, review_score, key):
        return self.client.post(
            "/reviews",
            {
                "user": self.user.pk,
                "card": self.card.pk,
                "review_score": review_score,
                "idempotency_key": key,
            },
            format="json",
        )
