import numpy as np
from rest_framework.test import APITestCase
from django.test import override_settings

from flowback.common.tests import generate_request
from flowback.group.models import GroupKPI, GroupUser, Group
from flowback.group.tests.factories import GroupFactory, GroupUserFactory, GroupKPIFactory, GroupKPIValueFactory
from flowback.poll.models import Poll
from flowback.poll.phases import PollProposal, PollProposalKPI, PollProposalKPIBet, PollProposalKPIVote
from flowback.poll.tasks import poll_kpi_count
from flowback.poll.tasks_new_kpi import (
    bet_outcome_matrix,
)
from flowback.poll.tests.factories import PollFactory, PollProposalFactory, PollProposalKPIBetFactory, \
    PollProposalKPIVoteFactory
from flowback.poll.tests.utils import generate_poll_phase_kwargs
from flowback.poll.views.prediction import PollProposalKPIBetAPI, PollProposalKPIVoteAPI, PollProposalKPIBetListAPI, \
    PollProposalKPIVoteListAPI, PollProposalKPIListAPI
from flowback.poll.views.proposal import PollProposalCreateAPI


class TestPollProposalKPI(APITestCase):
    def setUp(self):
        self.group = GroupFactory()
        self.group_user_creator = self.group.group_user_creator
        self.group_kpi_one, self.group_kpi_two, self.group_kpi_three = GroupKPIFactory.create_batch(3, group=self.group)
        [GroupKPIValueFactory(kpi=self.group_kpi_one, value=i) for i in [12, 22, 29]]
        [GroupKPIValueFactory(kpi=self.group_kpi_two, value=i) for i in [19, 99, 218, 227, 310, 827]]
        [GroupKPIValueFactory(kpi=self.group_kpi_three, value=i) for i in [12, 127, 198]]

        self.group_user_one, self.group_user_two = GroupUserFactory.create_batch(2, group=self.group)
        self.poll = PollFactory(created_by=self.group_user_creator,
                                poll_type=Poll.PollType.SCORE,
                                version=2,
                                **generate_poll_phase_kwargs('prediction_bet'))

        self.proposal_one, self.proposal_two, self.proposal_three = PollProposalFactory.create_batch(3,
                                                                                                     poll=self.poll,
                                                                                                     created_by=self.group_user_one)

    def test_proposal_create_kpi(self):
        Poll.objects.filter(id=self.poll.id).update(**generate_poll_phase_kwargs('proposal'))
        self.assertEqual(PollProposalKPI.objects.all().count(), 36)

        response = generate_request(api=PollProposalCreateAPI,
                                    user=self.group_user_one.user,
                                    url_params=dict(poll=self.poll.id),
                                    data=dict(title="hi", description="there"))

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(PollProposalKPI.objects.all().count(), 48)

    def test_kpi_bet(self):
        values = [12, 22, 29]
        weights = [19, 79, 2]

        response = generate_request(api=PollProposalKPIBetAPI,
                                    user=self.group_user_one.user,
                                    url_params=dict(proposal_id=self.proposal_one.id),
                                    data=dict(kpi_id=self.group_kpi_one.id,
                                              values=values,
                                              weights=weights))

        self.assertEqual(response.status_code, 200, response.data)

        for i in range(3):
            self.assertTrue(PollProposalKPIBet.objects.filter(created_by=self.group_user_one,
                                                              proposal_kpi__kpi_value__value=values[i],
                                                              weight=weights[i]).exists(),
                            f"KPI bet with value {values[i]} and weight {weights[i]} does not exist!")

    def test_kpi_bet_rejects_over_100_percent(self):
        response = generate_request(api=PollProposalKPIBetAPI,
                                    user=self.group_user_one.user,
                                    url_params=dict(proposal_id=self.proposal_one.id),
                                    data=dict(kpi_id=self.group_kpi_one.id,
                                              values=[12, 22, 29],
                                              weights=[50, 40, 11]))

        self.assertEqual(response.status_code, 400, response.data)
        self.assertFalse(PollProposalKPIBet.objects.filter(created_by=self.group_user_one).exists())

    def test_kpi_vote(self):
        bets = [(self.group_kpi_one, 12), (self.group_kpi_one, 22), (self.group_kpi_two, 99)]
        for i in range(3):
            PollProposalKPIBetFactory(created_by=self.group_user_one,
                                      proposal_kpi=PollProposalKPI.objects.get(proposal=self.proposal_one,
                                                                               kpi_value__kpi=bets[i][0],
                                                                               kpi_value__value=bets[i][1]))

        Poll.objects.filter(id=self.poll.id).update(**generate_poll_phase_kwargs('prediction_vote'))
        response = generate_request(api=PollProposalKPIVoteAPI,
                                    user=self.group_user_two.user,
                                    url_params=dict(proposal_id=self.proposal_one.id),
                                    data=dict(kpi_id=self.group_kpi_one.id,
                                              vote=22))

        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(PollProposalKPIVote.objects.filter(created_by=self.group_user_two,
                                                           proposal_kpi__kpi_value__value=22).exists())

    def generate_kpi_poll(self, group: Group) -> Poll:
        poll = PollFactory(created_by=group.group_user_creator,
                           poll_type=Poll.PollType.SCORE,
                           version=2,
                           **generate_poll_phase_kwargs('prediction_bet'))

        return poll

    def generate_kpi_bet(self,
                         group_user: GroupUser,
                         group_kpi: GroupKPI,
                         proposal: PollProposal,
                         value: int,
                         weight: int) -> PollProposal:

        PollProposalKPIBetFactory(created_by=group_user,
                                  weight=weight,
                                  proposal_kpi=PollProposalKPI.objects.get(proposal=proposal,
                                                                           kpi_value__kpi=group_kpi,
                                                                           kpi_value__value=value))

        return proposal

    def generate_kpi_vote(self, group_user: GroupUser, group_kpi: GroupKPI, proposal: PollProposal, value: int):
        return PollProposalKPIVoteFactory(created_by=group_user,
                                          proposal_kpi=PollProposalKPI.objects.get(proposal=proposal,
                                                                                   kpi_value__kpi=group_kpi,
                                                                                   kpi_value__value=value))

    def test_bet_outcome_matrix_matches_comment_example(self):
        proposals = []
        winners = []

        for _ in range(2):
            poll = self.generate_kpi_poll(group=self.group)
            proposal = PollProposalFactory(poll=poll, created_by=self.group_user_creator)
            PollProposalKPI.generate_kpis(proposal_id=proposal.id)
            proposal_kpis = list(
                PollProposalKPI.objects.filter(
                    proposal=proposal,
                    kpi_value__kpi=self.group_kpi_one,
                ).order_by("id")
            )

            self.generate_kpi_bet(
                self.group_user_one, self.group_kpi_one, proposal, 29, 100
            )
            for proposal_kpi, weight in zip(proposal_kpis, [33, 33, 34]):
                PollProposalKPIBetFactory(
                    created_by=self.group_user_two,
                    proposal_kpi=proposal_kpi,
                    weight=weight,
                )

            proposals.append(proposal)
            winners.append(proposal_kpis[2])

        matrix = bet_outcome_matrix(
            PollProposalKPIBet.objects.filter(proposal_kpi__proposal__in=proposals),
            PollProposalKPI.objects.filter(id__in=[winner.id for winner in winners]),
        )

        np.testing.assert_allclose(
            matrix,
            [
                [0, 0, 0, 0, 0, 0],
                [0.33, 0.33, -0.66, 0.33, 0.33, -0.66],
            ],
        )

    def test_update_kpi_combined_bets(self):
        poll = self.generate_kpi_poll(group=self.group)
        proposal = PollProposalFactory(
            poll=poll, created_by=self.group_user_creator
        )
        PollProposalKPI.generate_kpis(proposal_id=proposal.id)
        self.generate_kpi_vote(
            self.group_user_one, self.group_kpi_one, proposal, 12
        )
        self.generate_kpi_vote(
            self.group_user_two, self.group_kpi_one, proposal, 22
        )

        combined_bets = dict(
            PollProposalKPI.objects.filter(
                proposal=proposal, kpi_value__kpi=self.group_kpi_one
            ).values_list("kpi_value__value", "combined_bet")
        )
        self.assertEqual(float(combined_bets["12"]), 0.25)
        self.assertEqual(float(combined_bets["22"]), 0.75)
        self.assertEqual(float(combined_bets["29"]), 0)
        self.assertEqual(sum(map(float, combined_bets.values())), 1)

    def test_kpi_combined_bet(self):
        # group_kpi_one, [12, 22, 29]
        # group_kpi_two, [19, 99, 218, 227, 310, 827]
        # group_kpi_three, [12, 127, 198, 228]
        print("KPI names in order: ", self.group_kpi_one.name, self.group_kpi_two.name, self.group_kpi_three.name)

        # Poll one
        poll_one = self.generate_kpi_poll(group=self.group)
        proposal_one = PollProposalFactory(poll=poll_one, created_by=self.group_user_creator)

        self.generate_kpi_bet(self.group_user_one, self.group_kpi_one, proposal_one, 22, 10)
        self.generate_kpi_bet(self.group_user_two, self.group_kpi_one, proposal_one, 22, 10)
        self.generate_kpi_bet(self.group_user_two, self.group_kpi_one, proposal_one, 12, 16)
        Poll.objects.filter(id=poll_one.id).update(**generate_poll_phase_kwargs('prediction_vote'))
        poll_kpi_count(poll_id=poll_one.id, disable_dprint=False)

        print("\n\n")

        # User one won 10% on KPI 1, value 22
        # User two won 10% on KPI 1, value 22
        self.generate_kpi_vote(self.group_user_two, self.group_kpi_one, proposal_one, 22)

        # Poll two
        poll_two = self.generate_kpi_poll(group=self.group)
        proposal_two = PollProposalFactory(poll=poll_two, created_by=self.group_user_creator)

        self.generate_kpi_bet(self.group_user_one, self.group_kpi_one, proposal_two, 22, 22)
        self.generate_kpi_bet(self.group_user_two, self.group_kpi_one, proposal_two, 22, 12)
        self.generate_kpi_bet(self.group_user_one, self.group_kpi_one, proposal_two, 12, 16)
        Poll.objects.filter(id=poll_two.id).update(**generate_poll_phase_kwargs('prediction_vote'))
        poll_kpi_count(poll_id=poll_two.id, disable_dprint=False)

        print("\n\n")

        # User one won 16% on KPI 1, value 12
        self.generate_kpi_vote(self.group_user_two, self.group_kpi_one, proposal_two, 12)

        # Poll three
        poll_three = self.generate_kpi_poll(group=self.group)
        proposal_three = PollProposalFactory(poll=poll_three, created_by=self.group_user_creator)
        proposal_three_by_two = PollProposalFactory(poll=poll_three, created_by=self.group_user_creator)

        self.generate_kpi_bet(self.group_user_one, self.group_kpi_one, proposal_three_by_two, 22, 21)
        self.generate_kpi_bet(self.group_user_two, self.group_kpi_two, proposal_three_by_two, 227, 11)
        self.generate_kpi_bet(self.group_user_one, self.group_kpi_two, proposal_three_by_two, 227, 15)
        self.generate_kpi_bet(self.group_user_one, self.group_kpi_one, proposal_three, 22, 22)
        self.generate_kpi_bet(self.group_user_two, self.group_kpi_two, proposal_three, 227, 12)
        self.generate_kpi_bet(self.group_user_one, self.group_kpi_two, proposal_three, 227, 16)
        Poll.objects.filter(id=poll_three.id).update(**generate_poll_phase_kwargs('prediction_vote'))
        poll_kpi_count(poll_id=poll_three.id, disable_dprint=False)

        print("\n\n")

        # User one won (22% on KPI 1, value 22) (16% on KPI 2, value 227)
        # User two won (12% on KPI 2, value 227)
        self.generate_kpi_vote(self.group_user_two, self.group_kpi_one, proposal_three, 22)
        self.generate_kpi_vote(self.group_user_two, self.group_kpi_two, proposal_three, 227)

        # Poll four
        poll_four = self.generate_kpi_poll(group=self.group)
        proposal_four = PollProposalFactory(poll=poll_four, created_by=self.group_user_creator)
        proposal_four_by_two = PollProposalFactory(poll=poll_four, created_by=self.group_user_creator)

        self.generate_kpi_bet(self.group_user_one, self.group_kpi_two, proposal_four, 310, 22)
        self.generate_kpi_bet(self.group_user_two, self.group_kpi_two, proposal_four, 227, 12)
        self.generate_kpi_bet(self.group_user_two, self.group_kpi_one, proposal_four, 12, 16)
        self.generate_kpi_bet(self.group_user_two, self.group_kpi_one, proposal_four, 22, 30)
        self.generate_kpi_bet(self.group_user_one, self.group_kpi_two, proposal_four_by_two, 310, 21)
        self.generate_kpi_bet(self.group_user_two, self.group_kpi_two, proposal_four_by_two, 227, 11)
        self.generate_kpi_bet(self.group_user_two, self.group_kpi_one, proposal_four_by_two, 12, 15)
        self.generate_kpi_bet(self.group_user_two, self.group_kpi_one, proposal_four_by_two, 22, 29)

        poll_kpi_count(poll_id=poll_four.id, disable_dprint=False)
        print("\n\n")

    @override_settings(FLOWBACK_ENABLE_NEW_KPI_SYSTEM=True)
    def test_new_kpi_betting_returns_weighted_vote_average(self):
        poll = PollFactory(created_by=self.group_user_creator,
                           poll_type=Poll.PollType.V2_SCORE,
                           **generate_poll_phase_kwargs('prediction_vote'))
        proposal = PollProposalFactory(poll=poll, created_by=self.group_user_creator)

        PollProposalKPI.generate_kpis(proposal_id=proposal.id)
        self.generate_kpi_bet(
            self.group_user_one, self.group_kpi_one, proposal, 22, 10
        )
        self.generate_kpi_bet(
            self.group_user_two, self.group_kpi_one, proposal, 12, 5
        )
        self.generate_kpi_bet(
            self.group_user_one, self.group_kpi_two, proposal, 99, 7
        )

        other_proposal = PollProposalFactory(
            poll=poll, created_by=self.group_user_creator
        )
        self.generate_kpi_bet(
            self.group_user_one, self.group_kpi_one, other_proposal, 22, 9
        )

        self.generate_kpi_vote(
            self.group_user_creator, self.group_kpi_one, proposal, 22
        )
        self.generate_kpi_vote(
            self.group_user_one, self.group_kpi_one, proposal, 22
        )
        self.generate_kpi_vote(
            self.group_user_two, self.group_kpi_one, proposal, 12
        )

        self.assertEqual(
            poll_kpi_count(poll_id=poll.id),
            [
                {
                    "proposal_id": proposal.id,
                    "kpi_id": self.group_kpi_one.id,
                    "value": "22",
                    "weighted_average": 1.0,
                }
            ],
        )
        combined_bets = dict(
            PollProposalKPI.objects.filter(
                proposal=proposal, kpi_value__kpi=self.group_kpi_one
            ).values_list("kpi_value__value", "combined_bet")
        )
        self.assertEqual(float(combined_bets["12"]), 0)
        self.assertEqual(float(combined_bets["22"]), 1)
        self.assertEqual(float(combined_bets["29"]), 0)

    def test_new_kpi_betting_returns_no_averages_without_history(self):
        self.assertEqual(poll_kpi_count(poll_id=self.poll.id), [])
        self.assertFalse(
            PollProposalKPI.objects.filter(
                proposal__poll=self.poll, combined_bet__isnull=False
            ).exists()
        )

    def test_proposal_kpi_list(self):
        # TODO block users from accessing kpis they are not permitted to access (e.g. poll for specific workgroup)
        response = generate_request(api=PollProposalKPIListAPI,
                                    user=self.group_user_one.user,
                                    url_params=dict(group_id=self.group.id))

        self.assertEqual(response.status_code, 200, response.data)
        print(response.data)

    def test_kpi_bet_list(self):
        [PollProposalKPIBetFactory(proposal_kpi=PollProposalKPI.objects.get(proposal=self.proposal_one,
                                                                            kpi_value__kpi=self.group_kpi_one,
                                                                            kpi_value__value=i),
                                   created_by=self.group_user_one) for i in [12, 22, 29]]

        response = generate_request(api=PollProposalKPIBetListAPI,
                                    user=self.group_user_one.user,
                                    data=dict(kpi_ids=f'{self.group_kpi_one.id}'),
                                    url_params=dict(group_id=self.group.id))

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['count'], 3)

    def test_kpi_vote_list(self):
        for i in [12, 22, 29]:
            PollProposalKPIBetFactory(proposal_kpi=PollProposalKPI.objects.get(proposal=self.proposal_one,
                                                                               kpi_value__kpi=self.group_kpi_one,
                                                                               kpi_value__value=i),
                                      created_by=self.group_user_one)

        Poll.objects.filter(id=self.poll.id).update(**generate_poll_phase_kwargs('prediction_vote'))

        PollProposalKPIVote.objects.create(created_by=self.group_user_two,
                                           proposal_kpi=PollProposalKPI.objects.get(proposal=self.proposal_one,
                                                                                    kpi_value__value=22))

        response = generate_request(api=PollProposalKPIVoteListAPI,
                                    user=self.group_user_two.user,
                                    url_params=dict(group_id=self.group.id))

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['count'], 1)
