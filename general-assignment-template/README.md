# Flashcard Scheduler - Coding Challenge for Mantra

This repository outlines a simple 2-method REST API backend for a spaced repetition system (SRS) flashcard application.

## Initial Setup

- uv is recommended for managing virtual environments.

```
uv sync --all-groups

uv run manage.py makemigrations

uv run manage.py migrate
```

### Install and run PostgreSQL

This API uses PostgreSQL for data persistence, falling back to SQLite when not present.
Installing the PostgreSQL engine on your machine is outside the scope of this document.

Run the following commands on the psql shell - the \password command will then prompt you to create a password:
```
CREATE ROLE flashcards_app WITH LOGIN;
\password flashcards_app
CREATE DATABASE flashcards OWNER flashcards_app;
ALTER ROLE flashcards_app CREATEDB;
```
The ALTER ROLE command is necessary for some of the tests to execute, and should not be run in production.

You will also need to create the following environment variables:
```
DB_ENGINE = postgresql
DB_NAME = flashcards
DB_USERNAME = flashcards_app
DB_PASSWORD = {the password you created during the previous step}
```

Confirm postgresql is running and being interacted with correctly:
```
uv run manage.py shell -c "from django.db import connection; print(connection.vendor)"
```

### Run tests

```
uv run poe test
```

### Run server

```
uv run manage.py runserver
```


### Lint and format code

```
uv run poe lint
uv run poe format
```

---------------------------------------------------------------------------------------
## Algorithm Explanation

When the user records a review for a card, data about the user, card, and review score are passed to the backend, as well as an idempotency key to prevent duplicate resolutions of the same review. The idempotency key should be a UUID to all-but-guarantee uniqueness within the system.

The return of the reviews( ) method is the next_review datetime, as we will elaborate further.

The serializer verifies the validity of the data, including the existence of the passed user and card, as well as the review score being in the acceptable range (0-2).

Inside an atomic transaction (for smooth rollback if issues arise), we lock that card object in the database, and then attempt to find the associated Review object for that idempotency key:
* If it exists, and all of the data matches, this is a duplicate call, and we just return the next_review datetime
* If it exists but some of the data doesn't match, it returns a 409_CONFLICT status
* If it doesn't exist, which is expected, we continue

There is also a safeguard against a user editing a card that is not his, although realistically this should also be handled first by the front-end.

Now for the actual review score processing:
* For a review score of 0 ("do not remember at all"), the next review is scheduled for one minute from the current time
* For a review score of 1 ("remembered with effort"), the time for the next review is contingent on the current streak, calculated as (2 ** (streak - 1)). This means that, for example, answering 1 for the first review of a card returns a delay of 1 day (2 ** 0), while answering 1 for the fifth positive review of a streak returns a delay of 16 days (2 ** 4)
* For a review score of 2 ("remembered easily"), the time for the next review is also contingent on the current streak, calculated as (2 ** streak). For example, answering 2 for the first review of a card returns a delay of 2 days (2 ** 1), while answering 2 for the fifth positive review of a streak returns a delay of 32 days (2 ** 5)

This follows the monotonic requirement, since subsequent positive answers will at most match the previous wait duration, never be lower. As a direct example, answering 2 on the sixth consecutive positive review of a card will return a delay of 64 days (2 ** 6), and answering 1 on the next review of the same card will also return a delay of 64 days (2 ** (7-1)). This also complies with rule 2 (spacing logic), since a 2 review will always provide a longer interval than a 1 review.

I also included a hard cap on the exponent used for positive streak calculations. The score 1 delay is capped at 2 ** 10 (1024) days, and the score 2 delay is capped at the same maximum. This ensures a positive review can never schedule a card farther out than 1024 days and prevents a lower streak multiplier from shortening the interval after the cap is reached.

I will suggest resetting the streak on a review score 0, which doesn't strictly comply with the monotonic requirement, but it's logically sound (words you do not know anymore should be relearned from scratch to maximize retention), and it matches what the popular SRS app Anki does as well. There is a commented-out line that resets the streak on the logic for review score 0.

Times are all set in the Asia/Tokyo timezone.

Lastly, the card on the database is updated with the newly calculated information, and a Review object is also created, holding the logical information for this instance of the review, plus the idempotency key used, which is what prevents duplicate calls. There's also a safeguard flow for IntegrityErrors (likely stemming from attempting to save a review twice for the same idempotency key)

---

## API Specification

No authentication is required for the required API endpoints.

All request and response timestamps use ISO-8601 date-time strings. Django stores timestamps in UTC internally and returns aware datetime values using the configured `Asia/Tokyo` timezone.

### POST /reviews

Records a review for a card and returns the card's next review timestamp.

**Request**

```http
POST /reviews
Content-Type: application/json
```

```json
{
  "user": 1,
  "card": 10,
  "review_score": 2,
  "idempotency_key": "b7bb0f24-1c17-4f0d-a3a8-7e8e445a9e12"
}
```

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `user` | integer | Yes | Existing user primary key. |
| `card` | integer | Yes | Existing card primary key. |
| `review_score` | integer | Yes | `0`, `1`, or `2`. |
| `idempotency_key` | string | Yes | Unique key for this review; maximum 64 characters. |

The review scores are:

| Score | Meaning |
| --- | --- |
| `0` | The user does not remember the card. |
| `1` | The user remembers with effort. |
| `2` | The user remembers instantly. |

**Success response**

```http
200 OK
Content-Type: application/json
```

```json
{
  "next_review": "2026-11-25T00:00:00+09:00"
}
```

**Error responses**

Invalid or missing fields, including a review score outside `0–2`, an unknown user, or an unknown card:

```http
400 Bad Request
Content-Type: application/json
```

Attempting to review a card owned by another user:

```http
400 Bad Request
Content-Type: application/json
```

```json
{
  "detail": "Card does not belong to the supplied user"
}
```

### GET /users/{user_id}/due-cards

Returns cards belonging to the specified user whose `next_review` timestamp is less than or equal to `until`.

**Request**

```http
GET /users/1/due-cards?until=2026-11-25T00:00:00%2B09:00
```

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `user_id` | integer | Yes, in path | Existing user primary key. |
| `until` | ISO-8601 date-time | Yes, in query | Upper bound for `next_review`. |

**Success response**

```http
200 OK
Content-Type: application/json
```

```json
[
  {
    "id": 10,
    "user": 1,
    "card_front": "What is spaced repetition?",
    "card_back": "A study method that schedules reviews at increasing intervals.",
    "times_reviewed": 3,
    "positive_streak": 2,
    "last_failure": 1,
    "next_review": "2026-11-24T00:00:00+09:00"
  }
]
```

Cards are ordered by `next_review` ascending and then by card `id` ascending.

**Error responses**

Unknown or missing `until` value:

```http
400 Bad Request
Content-Type: application/json
```

Unknown user:

```http
404 Not Found
```