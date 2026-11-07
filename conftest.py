import pytest
from django.contrib.auth import get_user_model
from apps.tenants.models import Tenant, Membership
from apps.catalog.models import Product
from apps.inventory.models import StockBalance
from decimal import Decimal


@pytest.fixture
def tenant(db):
    return Tenant.objects.create(name="Loja de Teste", slug="loja-teste")


@pytest.fixture
def another_tenant(db):
    return Tenant.objects.create(name="Outra Loja", slug="outra-loja")


@pytest.fixture
def user(db):
    User = get_user_model()
    return User.objects.create_user(
        username="owner", email="owner@example.com", password="test-password-123"
    )


@pytest.fixture
def membership(tenant, user):
    return Membership.objects.create(
        tenant=tenant, user=user, role=Membership.Role.OWNER
    )


@pytest.fixture
def product(tenant):
    item = Product.objects.create(
        tenant=tenant, code="SKU-001", name="Produto de Teste", price="12.50"
    )
    StockBalance.objects.create(
        tenant=tenant,
        product=item,
        physical_quantity=Decimal("10.000"),
    )
    return item
