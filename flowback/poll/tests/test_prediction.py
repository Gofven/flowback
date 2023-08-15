import json
import random

from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate, APITransactionTestCase

from flowback.group.models import GroupUser
from flowback.group.tests.factories import GroupFactory, GroupUserFactory
from flowback.poll.models import Poll, PollPredictionStatement, PollPredictionStatementSegment, PollPrediction
from flowback.poll.tests.factories import PollFactory, PollPredictionFactory, PollProposalFactory, \
    PollPredictionStatementFactory, PollPredictionStatementSegmentFactory
from flowback.poll.tests.utils import generate_poll_phase_kwargs
from flowback.poll.views import PollPredictionStatementCreateAPI, PollPredictionStatementDeleteAPI, \
    PollPredictionCreateAPI, PollPredictionUpdateAPI, PollPredictionDeleteAPI
from flowback.user.models import User


class PollPredictionStatementTest(APITransactionTestCase):
    reset_sequences = True

    def setUp(self):
        # Group Preparation
        self.group = GroupFactory.create()
        self.user_group_creator = GroupUserFactory(group=self.group, user=self.group.created_by)

        (self.user_prediction_creator,
         self.user_prediction_caster_one,
         self.user_prediction_caster_two,
         self.user_prediction_caster_three) = [GroupUserFactory(group=self.group) for x in range(4)]

        # Poll Preparation
        self.poll = PollFactory(created_by=self.user_group_creator, **generate_poll_phase_kwargs('vote_start_date'))
        (self.proposal_one,
         self.proposal_two,
         self.proposal_three) = [PollProposalFactory(created_by=self.user_group_creator,
                                                     poll=self.poll) for x in range(3)]
        # Predictions Preparation
        self.prediction_statement = PollPredictionStatementFactory(created_by=self.user_prediction_creator,
                                                                   poll=self.poll)

        (self.prediction_statement_segment_one,
         self.prediction_statement_segment_two
         ) = [PollPredictionStatementSegmentFactory(prediction_statement=self.prediction_statement,
                                                    proposal=proposal) for proposal in [self.proposal_one,
                                                                                        self.proposal_three]]

        (self.prediction_one,
         self.prediction_two,
         self.prediction_three) = [PollPredictionFactory(prediction_statement=self.prediction_statement,
                                                         created_by=group_user
                                                         ) for group_user in [self.user_prediction_caster_one,
                                                                              self.user_prediction_caster_two,
                                                                              self.user_prediction_caster_three]]

    # Prediction Statements
    def test_create_prediction_statement(self):
        factory = APIRequestFactory()
        user = self.user_prediction_creator.user
        view = PollPredictionStatementCreateAPI.as_view()

        data = dict(description="A Test Prediction",
                    end_date=timezone.now() + timezone.timedelta(hours=2),
                    segments=[dict(proposal_id=self.proposal_one.id, is_true=True),
                              dict(proposal_id=self.proposal_two.id, is_true=False)])

        request = factory.post('', data, format='json')
        force_authenticate(request, user=user)
        response = view(request, poll_id=self.poll.id)

        prediction_statement = PollPredictionStatement.objects.get(id=int(response.rendered_content))

        total_segments = PollPredictionStatementSegment.objects.filter(prediction_statement=prediction_statement
                                                                       ).count()
        self.assertEqual(total_segments, 2,
                         f"Segment(s) not created, 2 expected, {total_segments} created.")

    @staticmethod
    def generate_delete_prediction_request(group_user: GroupUser, prediction_statement: PollPredictionStatement):
        factory = APIRequestFactory()
        view = PollPredictionStatementDeleteAPI.as_view()

        request = factory.post('')
        force_authenticate(request, user=group_user.user)
        return view(request, prediction_statement_id=prediction_statement.id)

    def test_delete_prediction_statement(self):
        response = self.generate_delete_prediction_request(group_user=self.user_prediction_creator,
                                                           prediction_statement=self.prediction_statement)
        self.assertEqual(PollPredictionStatement.objects.filter(id=self.prediction_statement.id).count(),
                         0, 'Deletion failed.')

    def test_delete_prediction_statement_unpermitted(self):
        response = self.generate_delete_prediction_request(group_user=self.user_prediction_caster_one,
                                                           prediction_statement=self.prediction_statement)
        data = json.loads(response.rendered_content)

        self.assertEqual(PollPredictionStatement.objects.filter(id=self.prediction_statement.id).count(),
                         1, 'Possibly passed with unpermitted user.')

    # Predictions
    def test_create_prediction(self):
        factory = APIRequestFactory()
        view = PollPredictionCreateAPI.as_view()

        data = dict(score=5)

        request = factory.post('', data)
        force_authenticate(request, user=self.user_prediction_caster_one.user)
        response = view(request, prediction_statement_id=self.prediction_statement.id)

        self.assertEqual(PollPrediction.objects.filter(id=int(response.rendered_content)).count(), 1,
                         "Prediction not created")

        self.assertEqual(PollPrediction.objects.get(id=int(response.rendered_content)).score, 5,
                         "Prediction not matching input score")

    def test_update_prediction(self):
        factory = APIRequestFactory()
        view = PollPredictionUpdateAPI.as_view()

        new_score = self.prediction_one.score
        new_score = random.choice([x for x in range(6) if x != new_score])

        data = dict(score=new_score)

        request = factory.post('', data)
        force_authenticate(request, user=self.user_prediction_caster_one.user)
        view(request, prediction_id=self.prediction_one.id)

        score = PollPrediction.objects.get(id=self.prediction_one.id).score
        self.assertEqual(score, new_score, f"Score '{score}' is not matching the new score {new_score}.")

    def test_delete_prediction(self):
        factory = APIRequestFactory()
        view = PollPredictionDeleteAPI.as_view()

        request = factory.post('')
        force_authenticate(request, user=self.user_prediction_caster_one.user)
        view(request, prediction_id=self.prediction_one.id)

        with self.assertRaises(PollPrediction.DoesNotExist, msg='Prediction not removed.'):
            PollPrediction.objects.get(id=self.prediction_one.id)