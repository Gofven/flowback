from rest_framework.test import APITestCase

from flowback.common.tests import generate_request
from flowback.group.models import GroupKPI, GroupKPIValue
from flowback.group.tests.factories import GroupUserFactory, GroupKPIFactory, GroupFactory
from flowback.group.views.kpi import GroupKPIListAPI, GroupKPICreateAPI, GroupKPIUpdateAPI


class GroupKPITest(APITestCase):
    def setUp(self):
        self.group = GroupFactory()
        self.group_user_creator = self.group.group_user_creator
        self.group_user = GroupUserFactory(group=self.group)

    def test_group_kpi_list(self):
        [GroupKPIFactory(group=self.group) for _ in range(10)]

        response = generate_request(api=GroupKPIListAPI,
                                    url_params=dict(group_id=self.group.id),
                                    user=self.group_user.user)

    def test_group_kpi_create(self):
        data = dict(name="test", description="test", values="1,9,19,39,77,1745")

        response = generate_request(api=GroupKPICreateAPI,
                                    url_params=dict(group_id=self.group.id),
                                    data=data,
                                    user=self.group_user_creator.user)

        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(GroupKPI.objects.all().count(), 1)
        self.assertEqual(
            list(GroupKPIValue.objects.filter(kpi_id=response.data).values_list("value", flat=True)),
            data["values"].split(","),
        )

    def test_group_kpi_create_one_letter(self):
        data = dict(name="test", description="test", values="d")

        response = generate_request(api=GroupKPICreateAPI,
                                    url_params=dict(group_id=self.group.id),
                                    data=data,
                                    user=self.group_user_creator.user)

        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(GroupKPI.objects.all().count(), 1)
        self.assertEqual(GroupKPIValue.objects.filter(kpi_id=response.data).first().value, "d")

    def test_group_kpi_create_duplicates(self):
        data = dict(name="test", description="test", values="1,9,19,39,77,77,1745")

        response = generate_request(api=GroupKPICreateAPI,
                                    url_params=dict(group_id=self.group.id),
                                    data=data,
                                    user=self.group_user_creator.user)

        self.assertEqual(response.status_code, 400, response.data)
        self.assertEqual(GroupKPI.objects.all().count(), 0)


    def test_group_kpi_create_not_admin(self):
        data = dict(name="test", description="test", values="1,9,19,39,77,1745")

        response = generate_request(api=GroupKPICreateAPI,
                                    url_params=dict(group_id=self.group.id),
                                    data=data,
                                    user=self.group_user.user)

        self.assertEqual(response.status_code, 403, response.data)
        self.assertEqual(GroupKPI.objects.all().count(), 0)

    def test_group_kpi_update(self):
        kpi = GroupKPIFactory(group=self.group)

        response = generate_request(api=GroupKPIUpdateAPI,
                                    url_params=dict(kpi_id=kpi.id),
                                    data=dict(active=False),
                                    user=self.group_user_creator.user)

        self.assertEqual(response.status_code, 200, response.data)
        kpi.refresh_from_db()
        self.assertFalse(kpi.active)

    def test_group_kpi_update_not_admin(self):
        kpi = GroupKPIFactory(group=self.group)

        response = generate_request(api=GroupKPIUpdateAPI,
                                    url_params=dict(kpi_id=kpi.id),
                                    data=dict(active=False),
                                    user=self.group_user.user)

        self.assertEqual(response.status_code, 403, response.data)
        kpi.refresh_from_db()
        self.assertTrue(kpi.active)

    def test_group_kpi_update_wrong_group(self):
        kpi = GroupKPIFactory()

        response = generate_request(api=GroupKPIUpdateAPI,
                                    url_params=dict(kpi_id=kpi.id),
                                    user=self.group_user_creator.user)

        self.assertEqual(response.status_code, 400, response.data)
        kpi.refresh_from_db()
        self.assertTrue(kpi.active)
