from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import api_view, action
from rest_framework.response import Response

from assignment.models import Card
from assignment.serializers import CardSerializer, DueCardsQuerySerializer, ReviewQuerySerializer


@api_view(["POST"])
def initialize_data(request):
    try:
        file_name = request.data.get("file", "MOCK_DATA.json")
        print(f"Initializing data from {file_name}")
        call_command("init_data", file=file_name)
        return Response(
            {"message": f"Data initialized successfully from {file_name}"},
            status=status.HTTP_200_OK,
        )
    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

# returns all cards from user 'user_id' that are due to review until date 'until' (inside request params)
@api_view(["GET"])
def due_cards(request, user_id):
    # create a query serializer for the "until" param, which is validated and then floated back as "until_date"
    query_serializer = DueCardsQuerySerializer(data=request.query_params)
    query_serializer.is_valid(raise_exception=True)

    until_date = query_serializer.validated_data["until"]

    # get_user_model uses the django-defined AUTH_USER_MODEL to get the User model
    User = get_user_model()
    # then the method below fetches the user with primary key "user_id" as passed in the API url
    user_data = get_object_or_404(User, pk=user_id)

    # filters through the cards list of the targeted user (via reverse relationship)
    cards = user_data.cards.filter(
        next_review__lte = until_date,
    ).order_by("next_review","pk")

    # serializes the found cards using a plain serializer
    card_serializer = CardSerializer(cards, many=True)

    return Response(
        card_serializer.data,
        status=status.HTTP_200_OK
    )

# Records one review result, returns timestamp for next due period
# fields required: user  ("user"), card id ("card"), review score ("review_score")
@api_view(["POST"])
def reviews(request):
    # the query serializer validates the necessary inputs and fetches the associated data
    query_serializer = ReviewQuerySerializer(data=request.data)
    query_serializer.is_valid(raise_exception=True)

    # full algorithm logic can be found at README.md
    STANDARD_DELAY = 2 # base value, in days, used for next review time calculations
    user = query_serializer.validated_data["user"]
    card = query_serializer.validated_data["card"]
    review_score = query_serializer.validated_data["review_score"]

    # prohibit a user from reviewing a card from another; just a safeguard, since the front-end is the one that should ensure this scenario
    if card.user != user:
        return Response( 
            {"detail": "Card does not belong to the supplied user"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if review_score == 0:
        # review 0 is the failure state - "don't know"
        card.positive_streak = 0
        card.times_reviewed += 1
        card.last_failure = card.times_reviewed
        card.next_review = timezone.now() + timedelta(minutes=1)
    else:
        card.positive_streak += 1
        card.times_reviewed += 1
        if review_score == 1: # review 1 is "remembered with some effort"
            next_days = pow(STANDARD_DELAY,card.positive_streak) - pow(STANDARD_DELAY,card.positive_streak - 1)
        elif review_score == 2: # review 2 is "remembered easily"
            next_days = pow(STANDARD_DELAY,card.positive_streak)
        else: # safeguard over an incorrect value slipping in this far
            return Response( 
                {"detail": "Review score was outside of the accepted range (0-2)"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # date of the next review is assigned as midnight X days from now, defined by next_days
        card.next_review = timezone.localtime(timezone.now()).replace(
            hour=0,minute=0,second=0,microsecond=0
        ) + timedelta(days=next_days)

    # after calculations are done, persist the values
    card.save(update_fields=["positive_streak","times_reviewed","last_failure","next_review"])

    return Response(
        card.next_review,
        status=status.HTTP_200_OK
    )

class UserViewSet(viewsets.ViewSet):
    """
    ViewSet for user-related operations.
    """

    @action(detail=False, methods=["GET"])
    def me(self, request):
        """
        Returns the username of the logged-in user.
        """
        if request.user.is_authenticated:
            return Response(
                {"username": request.user.username}, status=status.HTTP_200_OK
            )
        else:
            return Response(
                {"error": "User not authenticated"}, status=status.HTTP_401_UNAUTHORIZED
            )
