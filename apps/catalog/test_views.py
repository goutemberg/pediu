import pytest

from django.urls import reverse

from apps.catalog.models import Category, Product
from apps.inventory.models import StockBalance, StockMovement
from decimal import Decimal


@pytest.fixture
def catalog_category(tenant):
    return Category.objects.create(
        tenant=tenant,
        name="Bebidas",
        slug="bebidas",
    )


def authenticate_for_tenant(client, user, tenant, membership):
    """
    Autentica o usuário e garante uma associação ativa
    com a empresa selecionada na sessão.
    """

    tenant.status = "active"
    tenant.save(update_fields=["status"])

    membership.is_active = True
    membership.save(update_fields=["is_active"])

    client.force_login(user)

    session = client.session
    session["active_tenant_id"] = tenant.pk
    session.save()

    return client


def valid_product_data(category, **overrides):
    """Monta os dados válidos utilizados nos formulários de produto."""

    data = {
        "code_mode": "auto",
        "manual_code": "",
        "name": "Produto de Teste",
        "category": str(category.pk),
        "description": "Descrição do produto",
        "price": "15.90",
        "unit": "UN",
        "minimum_quantity": "1.000",
        "quantity_multiple": "1.000",
        "initial_stock": "10.000",
        "is_active": "on",
    }

    data.update(overrides)

    return data


# =========================================================
# CADASTRO DE PRODUTOS
# =========================================================


@pytest.mark.django_db
def test_product_create_get_displays_automatic_code_option(
    client,
    user,
    membership,
    tenant,
):
    authenticate_for_tenant(client, user, tenant, membership)

    response = client.get(reverse("catalog:product-create"))

    assert response.status_code == 200
    assert response.context["is_edit"] is False
    assert response.context["page_title"] == "Novo produto"
    assert response.context["form"].fields["code_mode"].initial == "auto"


@pytest.mark.django_db
def test_product_create_generates_automatic_code_and_initial_stock(
    client,
    user,
    membership,
    tenant,
    catalog_category,
):
    authenticate_for_tenant(client, user, tenant, membership)

    response = client.post(
        reverse("catalog:product-create"),
        data=valid_product_data(catalog_category),
    )

    assert response.status_code == 302
    assert response.url == reverse("catalog:product-list")

    product = Product.objects.get(
        tenant=tenant,
        name="Produto de Teste",
    )

    assert product.code == "PROD-000001"

    balance = StockBalance.objects.get(
        tenant=tenant,
        product=product,
    )

    assert balance.physical_quantity == 10

    movement = StockMovement.objects.get(
        tenant=tenant,
        product=product,
        reference="ESTOQUE_INICIAL",
    )

    assert movement.quantity == 10
    assert movement.kind == StockMovement.Kind.IN


@pytest.mark.django_db
def test_product_create_accepts_manual_code(
    client,
    user,
    membership,
    tenant,
    catalog_category,
):
    authenticate_for_tenant(client, user, tenant, membership)

    response = client.post(
        reverse("catalog:product-create"),
        data=valid_product_data(
            catalog_category,
            code_mode="manual",
            manual_code="meu-produto-01",
            initial_stock="0",
        ),
    )

    assert response.status_code == 302

    product = Product.objects.get(
        tenant=tenant,
        name="Produto de Teste",
    )

    assert product.code == "MEU-PRODUTO-01"

    assert StockBalance.objects.filter(
        tenant=tenant,
        product=product,
        physical_quantity=0,
    ).exists()

    assert not StockMovement.objects.filter(
        tenant=tenant,
        product=product,
        reference="ESTOQUE_INICIAL",
    ).exists()


@pytest.mark.django_db
def test_product_create_rejects_duplicate_manual_code(
    client,
    user,
    membership,
    tenant,
    catalog_category,
    product,
):
    authenticate_for_tenant(client, user, tenant, membership)

    response = client.post(
        reverse("catalog:product-create"),
        data=valid_product_data(
            catalog_category,
            code_mode="manual",
            manual_code=product.code.lower(),
        ),
    )

    assert response.status_code == 200
    assert Product.objects.filter(tenant=tenant).count() == 1
    assert response.context["form"].errors


# =========================================================
# LISTAGEM DE PRODUTOS
# =========================================================


@pytest.mark.django_db
def test_product_list_displays_only_active_tenant_products(
    client,
    user,
    membership,
    tenant,
    product,
    another_tenant,
):
    authenticate_for_tenant(client, user, tenant, membership)

    other_product = Product.objects.create(
        tenant=another_tenant,
        code="OUTRA-LOJA-001",
        name="Produto de Outra Empresa",
        price="20.00",
    )

    response = client.get(reverse("catalog:product-list"))

    assert response.status_code == 200

    displayed_products = [row["product"] for row in response.context["product_rows"]]

    displayed_ids = [item.pk for item in displayed_products]

    assert product.pk in displayed_ids
    assert other_product.pk not in displayed_ids


# =========================================================
# EDIÇÃO DE PRODUTOS
# =========================================================


@pytest.mark.django_db
def test_product_update_preserves_existing_code(
    client,
    user,
    membership,
    tenant,
    product,
    catalog_category,
):
    authenticate_for_tenant(client, user, tenant, membership)

    original_code = product.code

    response = client.post(
        reverse(
            "catalog:product-update",
            kwargs={"product_id": product.pk},
        ),
        data=valid_product_data(
            catalog_category,
            name="Produto Atualizado",
            price="25.90",
        ),
    )

    assert response.status_code == 302
    assert response.url == reverse("catalog:product-list")

    product.refresh_from_db()

    assert product.name == "Produto Atualizado"
    assert product.price == Decimal("25.90")
    assert product.code == original_code


@pytest.mark.django_db
def test_product_update_get_displays_readonly_code(
    client,
    user,
    membership,
    tenant,
    product,
):
    authenticate_for_tenant(client, user, tenant, membership)

    response = client.get(
        reverse(
            "catalog:product-update",
            kwargs={"product_id": product.pk},
        )
    )

    assert response.status_code == 200
    assert response.context["is_edit"] is True
    assert response.context["form"].fields["current_code"].disabled is True
    assert response.context["form"].fields["current_code"].initial == product.code


@pytest.mark.django_db
def test_product_update_does_not_allow_access_to_another_tenant(
    client,
    user,
    membership,
    tenant,
    another_tenant,
):
    authenticate_for_tenant(client, user, tenant, membership)

    other_product = Product.objects.create(
        tenant=another_tenant,
        code="OUTRA-LOJA-002",
        name="Produto Protegido",
        price="30.00",
    )

    response = client.get(
        reverse(
            "catalog:product-update",
            kwargs={"product_id": other_product.pk},
        )
    )

    assert response.status_code == 404


# =========================================================
# ATIVAÇÃO E DESATIVAÇÃO DE PRODUTOS
# =========================================================


@pytest.mark.django_db
def test_product_toggle_status_deactivates_product(
    client,
    user,
    membership,
    tenant,
    product,
):
    authenticate_for_tenant(client, user, tenant, membership)

    assert product.is_active is True

    response = client.post(
        reverse(
            "catalog:product-toggle-status",
            kwargs={"product_id": product.pk},
        )
    )

    assert response.status_code == 302
    assert response.url == reverse("catalog:product-list")

    product.refresh_from_db()

    assert product.is_active is False


@pytest.mark.django_db
def test_product_toggle_status_activates_inactive_product(
    client,
    user,
    membership,
    tenant,
    product,
):
    authenticate_for_tenant(client, user, tenant, membership)

    product.is_active = False
    product.save(update_fields=["is_active"])

    response = client.post(
        reverse(
            "catalog:product-toggle-status",
            kwargs={"product_id": product.pk},
        )
    )

    assert response.status_code == 302

    product.refresh_from_db()

    assert product.is_active is True


@pytest.mark.django_db
def test_product_toggle_status_rejects_get_request(
    client,
    user,
    membership,
    tenant,
    product,
):
    authenticate_for_tenant(client, user, tenant, membership)

    response = client.get(
        reverse(
            "catalog:product-toggle-status",
            kwargs={"product_id": product.pk},
        )
    )

    assert response.status_code == 405

    product.refresh_from_db()

    assert product.is_active is True


@pytest.mark.django_db
def test_product_toggle_status_does_not_allow_another_tenant_product(
    client,
    user,
    membership,
    tenant,
    another_tenant,
):
    authenticate_for_tenant(client, user, tenant, membership)

    other_product = Product.objects.create(
        tenant=another_tenant,
        code="OUTRA-LOJA-003",
        name="Produto de Outra Empresa",
        price="40.00",
    )

    response = client.post(
        reverse(
            "catalog:product-toggle-status",
            kwargs={"product_id": other_product.pk},
        )
    )

    assert response.status_code == 404

    other_product.refresh_from_db()

    assert other_product.is_active is True
