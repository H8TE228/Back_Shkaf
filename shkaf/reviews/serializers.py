from django.db import IntegrityError, transaction
from django.db.models import Q
from rest_framework import serializers

from chat.serializers import ParticipantSerializer
from exchanges.models import Exchange
from items.exceptions import StateConflict
from items.serializers import ItemBriefSerializer

from .models import MAX_COMMENT_LENGTH, Review


class ReviewSerializer(serializers.ModelSerializer):
    exchange_id = serializers.PrimaryKeyRelatedField(
        queryset=Exchange.objects.all(), source='exchange', write_only=True,
        help_text='Завершённая передача, в которой участвовал автор',
    )
    item = ItemBriefSerializer(source='exchange.item', read_only=True)
    author = ParticipantSerializer(read_only=True)
    target_user_id = serializers.IntegerField(read_only=True)
    rating = serializers.IntegerField(min_value=1, max_value=5)
    comment = serializers.CharField(max_length=MAX_COMMENT_LENGTH, required=False, allow_blank=True)

    class Meta:
        model = Review
        fields = ('id', 'exchange_id', 'item', 'author', 'target_user_id', 'rating', 'comment', 'created_at')
        read_only_fields = ('id', 'created_at')

    def get_fields(self):
        fields = super().get_fields()
        request = self.context.get('request')
        if request is not None and request.user.is_authenticated:
            user = request.user
            fields['exchange_id'].queryset = Exchange.objects.filter(Q(giver=user) | Q(receiver=user))
        if self.instance is not None:
            # Передачу у существующего отзыва не меняют
            fields['exchange_id'].read_only = True
        return fields

    def validate_exchange_id(self, exchange):
        if exchange.status != Exchange.Status.COMPLETED:
            raise StateConflict('A review can be left only after the exchange is completed.')
        return exchange

    def create(self, validated_data):
        exchange = validated_data['exchange']
        author = self.context['request'].user
        target_user_id = exchange.receiver_id if author.pk == exchange.giver_id else exchange.giver_id
        try:
            with transaction.atomic():
                return Review.objects.create(author=author, target_user_id=target_user_id, **validated_data)
        except IntegrityError:
            raise StateConflict('You have already reviewed this exchange.') from None


class RatingSerializer(serializers.Serializer):
    user_id = serializers.IntegerField()
    average = serializers.FloatField(allow_null=True, help_text='Средняя оценка с одним знаком после запятой')
    count = serializers.IntegerField()
