import pytest
from django.test import Client

@pytest.mark.django_db
def test_health_endpoint_returns_ok():
    assert Client().get("/health/").status_code == 200

import pytest
from django.core.exceptions import PermissionDenied
from django.test import RequestFactory

from apps.core.permissions import require_roles
from apps.tenants.models import Membership


@pytest.mark.django_db
def test_require_roles_allows_owner(tenant, user, membership):
    request = RequestFactory().get("/")
    request.user = user
    request.session = {"active_tenant_id": tenant.pk}

    @require_roles(Membership.Role.OWNER)
    def protected_view(request):
        return "ok"

    assert protected_view(request) == "ok"


@pytest.mark.django_db
def test_require_roles_blocks_staff_from_owner_action(tenant, user):
    Membership.objects.create(tenant=tenant, user=user, role=Membership.Role.STAFF)
    request = RequestFactory().get("/")
    request.user = user
    request.session = {"active_tenant_id": tenant.pk}

    @require_roles(Membership.Role.OWNER)
    def protected_view(request):
        return "ok"

    with pytest.raises(PermissionDenied):
        protected_view(request)


@pytest.mark.django_db
def test_require_roles_uses_active_tenant_membership(tenant, another_tenant, user):
    Membership.objects.create(tenant=tenant, user=user, role=Membership.Role.OWNER)
    Membership.objects.create(tenant=another_tenant, user=user, role=Membership.Role.STAFF)
    request = RequestFactory().get("/")
    request.user = user
    request.session = {"active_tenant_id": another_tenant.pk}

    @require_roles(Membership.Role.OWNER)
    def protected_view(request):
        return "ok"

    with pytest.raises(PermissionDenied):
        protected_view(request)
