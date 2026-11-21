from rest_framework import serializers
from .models import Card

class CardSerializer(serializers.ModelSerializer):
    class Meta:
        model = Card
        fields = '__all__'

class DueCardsQuerySerializer(serializers.Serializer):
    until = serializers.DateTimeField()