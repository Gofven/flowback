from django.db.models import Q, OuterRef, Subquery, Case, When, F
import django_filters
from rest_framework.exceptions import PermissionDenied

from .models import MessageChannel, Message, MessageChannelParticipant, MessageChannelTopic
from flowback.user.models import User
from ..common.filters import NumberInFilter, ExistsFilter
from ..common.services import get_object


class BaseMessageFilter(django_filters.FilterSet):
    order_by = django_filters.OrderingFilter(fields=(('created_at', 'created_at_asc'),
                                                     ('-created_at', 'created_at_desc')))
    topic_name = django_filters.CharFilter(lookup_expr='exact', field_name='topic__name')
    user_ids = NumberInFilter()
    has_attachments = ExistsFilter(field_name='attachments')

    class Meta:
        model = Message
        fields = dict(id=['exact'],
                      message=['icontains'],
                      topic_id=['exact'],
                      parent_id=['exact'],
                      created_at=['gte', 'lte'])


def message_list(*, user: User, channel_id: int, filters=None):
    filters = filters or {}
    participant = get_object(MessageChannelParticipant, channel_id=channel_id, user=user)

    qs = Message.objects.filter(channel=participant.channel).all()

    return BaseMessageFilter(filters, qs).qs


class BaseTopicFilter(django_filters.FilterSet):
    class Meta:
        model = MessageChannelTopic
        fields = dict(id=['exact'],
                      name=['exact', 'icontains'])


def message_channel_topic_list(*, user: User, channel_id: int, filters=None):
    filters = filters or {}
    participant = get_object(MessageChannelParticipant, channel_id=channel_id, user=user)

    qs = MessageChannelTopic.objects.filter(channel=participant.channel).all()
    return BaseTopicFilter(filters, qs).qs


class BaseMessageChannelPreviewFilter(django_filters.FilterSet):
    order_by = django_filters.OrderingFilter(fields=(('created_at', 'created_at_asc'),
                                                     ('-created_at', 'created_at_desc')))

    username__icontains = django_filters.CharFilter(field_name='target__username', lookup_expr='icontains')
    origin_name = django_filters.CharFilter(field_name='channel__origin_name', lookup_expr='exact')
    topic_name = django_filters.CharFilter(field_name='topic__name', lookup_expr='exact')

    class Meta:
        model = Message
        fields = dict(id=['exact'],
                      user_id=['exact'],
                      created_at=['gte', 'lte'],
                      channel_id=['exact'],
                      topic_id=['exact'])


def message_channel_preview_list_(*, user: User, filters=None):
    filters = filters or {}

    timestamp = MessageChannelParticipant.objects.filter(user=user, channel=OuterRef('channel_id')).values('timestamp')
    qs = Message.objects.filter(Q(Q(channel__messagechannelparticipant__closed_at__isnull=True)
                                  | Q(channel__messagechannelparticipant__closed_at__gt=F('created_at'))),
                                Q(Q(topic__isnull=True)
                                  | Q(topic__hidden=False)),
                                channel__messagechannelparticipant__user=user,
                                active=True).annotate(timestamp=Subquery(timestamp)
                                                      ).distinct('channel').all()

    return BaseMessageChannelPreviewFilter(filters, qs).qs


def message_channel_preview_list(*, user: User, filters=None):
    filters = filters or {}

    timestamp = MessageChannelParticipant.objects.filter(user=user, channel=OuterRef('channel_id')).values('timestamp')

    message_qs = Message.objects.filter(Q(Q(channel__messagechannelparticipant__closed_at__isnull=True)
                                          | Q(channel__messagechannelparticipant__closed_at__gt=F('created_at'))),
                                        Q(Q(topic__isnull=True)
                                          | Q(topic__hidden=False)),
                                        channel__messagechannelparticipant__user=user,
                                        active=True).annotate(timestamp=Subquery(timestamp)
                                                              ).distinct('channel').all()

    qs = Message.objects.filter(id__in=message_qs)

    return BaseMessageChannelPreviewFilter(filters, qs).qs


class MessageChannelParticipantFilter(django_filters.FilterSet):
    username__icontains = django_filters.CharFilter(lookup_expr='icontains', field_name='user__username')

    class Meta:
        model = MessageChannelParticipant
        fields = dict(id=['exact'],
                      user_id=['exact'])


def message_channel_participant_list(*, user: User, channel_id: int, filters=None):
    filters = filters or {}

    try:
        participant = MessageChannelParticipant.objects.get(user=user, channel_id=channel_id, active=True)

    except MessageChannelParticipant.DoesNotExist:
        raise PermissionDenied("User is not a participant of this channel")

    qs = MessageChannelParticipant.objects.filter(channel=participant.channel, active=True).all()

    return BaseMessageChannelPreviewFilter(filters, qs).qs
