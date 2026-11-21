from rest_framework import status, viewsets
from rest_framework.decorators import api_view, action
from rest_framework.response import Response
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.shortcuts import get_object_or_404

from assignment.models import Card
from assignment.serializers import CardSerializer, DueCardsQuerySerializer


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

class CardViewSet(viewsets.ViewSet):
    """
    ViewSet for card-related operations.
    """

    @action(detail=False, methods=["POST"])
    def reviews(self,request):
        # Records one review result, returns timestamp for next due period
        # actual spaced repetition logic will go in here
        return True