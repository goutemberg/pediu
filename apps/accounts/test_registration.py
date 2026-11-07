import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.tenants.models import Membership, Tenant


@pytest.mark.django_db
def test_registration_creates_user_tenant_and_owner_membership(client):
    response = client.post(reverse("accounts:register"), {
        "first_name": "Ana",
        "last_name": "Silva",
        "email": "ana@example.com",
        "password1": "Strong-Pass-2026!",
        "password2": "Strong-Pass-2026!",
        "store_name": "Loja de Ração",
        "store_phone": "81999990000",
    })

    assert response.status_code == 302
    assert response.url == reverse("dashboard:home")

    user = get_user_model().objects.get(email="ana@example.com")
    tenant = Tenant.objects.get(slug="loja-de-racao")
    membership = Membership.objects.get(user=user, tenant=tenant)

    assert user.check_password("Strong-Pass-2026!")
    assert membership.role == Membership.Role.OWNER
    assert membership.is_active is True
    assert client.session["_auth_user_id"] == str(user.pk)
    assert client.session["active_tenant_id"] == tenant.pk


@pytest.mark.django_db
def test_registration_generates_unique_slug_for_same_store_name(client, user, tenant):
    response = client.post(reverse("accounts:register"), {
        "first_name": "Bruno",
        "last_name": "Souza",
        "email": "bruno@example.com",
        "password1": "Strong-Pass-2026!",
        "password2": "Strong-Pass-2026!",
        "store_name": "Loja Teste",
        "store_phone": "81988887777",
    })

    assert response.status_code == 302
    assert Tenant.objects.filter(slug="loja-teste-2").exists()


@pytest.mark.django_db
def test_registration_rejects_existing_email(client, user):
    response = client.post(reverse("accounts:register"), {
        "first_name": "Ana",
        "last_name": "Silva",
        "email": user.email,
        "password1": "Strong-Pass-2026!",
        "password2": "Strong-Pass-2026!",
        "store_name": "Outra Loja",
    })

    assert response.status_code == 200
    assert get_user_model().objects.filter(email=user.email).count() == 1
    assert not Tenant.objects.filter(name="Outra Loja").exists()


@pytest.mark.django_db
def test_registration_does_not_create_partial_records_when_validation_fails(client):
    response = client.post(reverse("accounts:register"), {
        "first_name": "Ana",
        "last_name": "Silva",
        "email": "ana@example.com",
        "password1": "Strong-Pass-2026!",
        "password2": "Different-Pass-2026!",
        "store_name": "Loja de Ração",
    })

    assert response.status_code == 200
    assert get_user_model().objects.count() == 0
    assert Tenant.objects.count() == 0


@pytest.mark.django_db
def test_authenticated_user_can_create_another_store(client, user, membership):
    client.force_login(user)
    response = client.post(reverse("tenants:create"), {
        "name": "Segunda Loja",
        "phone": "81977776666",
        "description": "Nova unidade",
    })

    assert response.status_code == 302
    second_tenant = Tenant.objects.get(slug="segunda-loja")
    assert Membership.objects.filter(
        user=user, tenant=second_tenant, role=Membership.Role.OWNER, is_active=True
    ).exists()
    assert client.session["active_tenant_id"] == second_tenant.pk
    assert user.memberships.count() == 2


@pytest.mark.django_db
def test_login_without_membership_redirects_to_create_store(client):
    user = get_user_model().objects.create_user(
        username="semloja", email="semloja@example.com", password="Strong-Pass-2026!"
    )
    response = client.post(reverse("login"), {
        "username": user.email,
        "password": "Strong-Pass-2026!",
    })

    assert response.status_code == 302
    assert response.url == reverse("tenants:create")
