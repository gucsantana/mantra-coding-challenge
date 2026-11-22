from rest_framework import serializers
from .models import User, Card

# used for serializing found card output into a request response
class CardSerializer(serializers.ModelSerializer):
    class Meta:
        model = Card
        fields = '__all__'

# used to serialize and verify the "until" parameter from the due-cards query
class DueCardsQuerySerializer(serializers.Serializer):
    until = serializers.DateTimeField()

# used to serialize and verify the parameters passed on the "reviews" query
class ReviewQuerySerializer(serializers.Serializer):
    user = serializers.PrimaryKeyRelatedField( queryset = User.objects.all() )
    card = serializers.PrimaryKeyRelatedField( queryset = Card.objects.all() )
    review_score = serializers.IntegerField(min_value=0,max_value=2)
