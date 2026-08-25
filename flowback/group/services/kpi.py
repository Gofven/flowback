from rest_framework.exceptions import ValidationError

from .permission import group_user_permissions
from ..models import GroupKPI, GroupKPIValue


def group_kpi_create(user_id: int, group_id: int, name: str, values: list[str], description: str = None):
    group_user_permissions(user=user_id, group=group_id, permissions=['admin'])

    if len(values) != len(set(values)):
        raise ValidationError("Duplicates in values are not permitted")

    kpi = GroupKPI(group_id=group_id, name=name, description=description)
    kpi.full_clean()
    kpi.save()

    kpi_values = [GroupKPIValue(kpi=kpi, value=i) for i in values]
    GroupKPIValue.objects.bulk_create(kpi_values)

    return kpi


def group_kpi_update(user_id: int, kpi_id: int, active: bool = True):
    kpi = GroupKPI.objects.get(id=kpi_id)

    group_user_permissions(user=user_id, group=kpi.group_id, permissions=['admin'])

    kpi.active = active
    kpi.save()
