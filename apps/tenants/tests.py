import pytest
from django.db import IntegrityError, transaction
from .models import Tenant, Membership

@pytest.mark.django_db
def test_tenant_creation(tenant):
    assert tenant.slug == "loja-teste"
    assert tenant.status == Tenant.Status.TRIAL

@pytest.mark.django_db
def test_tenant_slug_unique(tenant):
    with pytest.raises(IntegrityError), transaction.atomic():
        Tenant.objects.create(name="Duplicada", slug=tenant.slug)

@pytest.mark.django_db
def test_user_can_belong_to_multiple_tenants(user, tenant, another_tenant):
    Membership.objects.create(tenant=tenant, user=user, role=Membership.Role.OWNER)
    Membership.objects.create(tenant=another_tenant, user=user, role=Membership.Role.STAFF)
    assert user.memberships.count() == 2

@pytest.mark.django_db
def test_membership_unique_per_tenant_user(membership, tenant, user):
    with pytest.raises(IntegrityError), transaction.atomic():
        Membership.objects.create(tenant=tenant, user=user, role=Membership.Role.STAFF)
