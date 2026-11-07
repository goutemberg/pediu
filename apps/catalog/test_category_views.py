import pytest

from django.urls import reverse

from apps.catalog.models import Category


@pytest.fixture
def catalog_category(tenant):
    return Category.objects.create(
        tenant=tenant,
        name="Bebidas",
        slug="bebidas",
    )


def authenticate_for_tenant(client, user, tenant, membership):
    """Autentica o usuário e seleciona uma empresa ativa."""

    tenant.status = "active"
    tenant.save(update_fields=["status"])

    membership.is_active = True
    membership.save(update_fields=["is_active"])

    client.force_login(user)

    session = client.session
    session["active_tenant_id"] = tenant.pk
    session.save()

    return client


# =========================================================
# CADASTRO DE CATEGORIAS
# =========================================================


@pytest.mark.django_db
def test_category_create_get_displays_form(
    client,
    user,
    membership,
    tenant,
):
    authenticate_for_tenant(client, user, tenant, membership)

    response = client.get(reverse("catalog:category-create"))

    assert response.status_code == 200
    assert response.context["is_edit"] is False
    assert response.context["page_title"] == "Nova categoria"


@pytest.mark.django_db
def test_category_create_successfully(
    client,
    user,
    membership,
    tenant,
):
    authenticate_for_tenant(client, user, tenant, membership)

    response = client.post(
        reverse("catalog:category-create"),
        data={
            "name": "Mercearia e Bebidas",
            "is_active": "on",
        },
    )

    assert response.status_code == 302
    assert response.url == reverse("catalog:category-list")

    category = Category.objects.get(
        tenant=tenant,
        name="Mercearia e Bebidas",
    )

    assert category.slug == "mercearia-e-bebidas"
    assert category.is_active is True


@pytest.mark.django_db
def test_category_create_rejects_duplicate_name(
    client,
    user,
    membership,
    tenant,
    catalog_category,
):
    authenticate_for_tenant(client, user, tenant, membership)

    response = client.post(
        reverse("catalog:category-create"),
        data={
            "name": "bebidas",
            "is_active": "on",
        },
    )

    assert response.status_code == 200
    assert Category.objects.filter(tenant=tenant).count() == 1
    assert response.context["form"].errors


@pytest.mark.django_db
def test_category_create_rejects_similar_slug(
    client,
    user,
    membership,
    tenant,
    catalog_category,
):
    authenticate_for_tenant(client, user, tenant, membership)

    response = client.post(
        reverse("catalog:category-create"),
        data={
            "name": "Bebidas!",
            "is_active": "on",
        },
    )

    assert response.status_code == 200
    assert Category.objects.filter(tenant=tenant).count() == 1
    assert response.context["form"].errors


# =========================================================
# LISTAGEM DE CATEGORIAS
# =========================================================


@pytest.mark.django_db
def test_category_list_displays_only_active_tenant_categories(
    client,
    user,
    membership,
    tenant,
    catalog_category,
    another_tenant,
):
    authenticate_for_tenant(client, user, tenant, membership)

    other_category = Category.objects.create(
        tenant=another_tenant,
        name="Categoria de Outra Empresa",
        slug="categoria-outra-empresa",
    )

    response = client.get(reverse("catalog:category-list"))

    assert response.status_code == 200

    displayed_categories = list(response.context["page_obj"].object_list)
    displayed_ids = [category.pk for category in displayed_categories]

    assert catalog_category.pk in displayed_ids
    assert other_category.pk not in displayed_ids


# =========================================================
# EDIÇÃO DE CATEGORIAS
# =========================================================


@pytest.mark.django_db
def test_category_update_get_displays_form(
    client,
    user,
    membership,
    tenant,
    catalog_category,
):
    authenticate_for_tenant(client, user, tenant, membership)

    response = client.get(
        reverse(
            "catalog:category-update",
            kwargs={"category_id": catalog_category.pk},
        )
    )

    assert response.status_code == 200
    assert response.context["is_edit"] is True
    assert response.context["category"].pk == catalog_category.pk


@pytest.mark.django_db
def test_category_update_changes_name_and_slug(
    client,
    user,
    membership,
    tenant,
    catalog_category,
):
    authenticate_for_tenant(client, user, tenant, membership)

    response = client.post(
        reverse(
            "catalog:category-update",
            kwargs={"category_id": catalog_category.pk},
        ),
        data={
            "name": "Alimentos e Mercearia",
            "is_active": "on",
        },
    )

    assert response.status_code == 302
    assert response.url == reverse("catalog:category-list")

    catalog_category.refresh_from_db()

    assert catalog_category.name == "Alimentos e Mercearia"
    assert catalog_category.slug == "alimentos-e-mercearia"
    assert catalog_category.is_active is True


@pytest.mark.django_db
def test_category_update_rejects_duplicate_name(
    client,
    user,
    membership,
    tenant,
    catalog_category,
):
    authenticate_for_tenant(client, user, tenant, membership)

    another_category = Category.objects.create(
        tenant=tenant,
        name="Alimentos",
        slug="alimentos",
    )

    response = client.post(
        reverse(
            "catalog:category-update",
            kwargs={"category_id": catalog_category.pk},
        ),
        data={
            "name": "alimentos",
            "is_active": "on",
        },
    )

    assert response.status_code == 200

    catalog_category.refresh_from_db()

    assert catalog_category.name == "Bebidas"
    assert another_category.name == "Alimentos"
    assert response.context["form"].errors


@pytest.mark.django_db
def test_category_update_rejects_similar_slug(
    client,
    user,
    membership,
    tenant,
    catalog_category,
):
    authenticate_for_tenant(client, user, tenant, membership)

    Category.objects.create(
        tenant=tenant,
        name="Alimentos",
        slug="alimentos",
    )

    response = client.post(
        reverse(
            "catalog:category-update",
            kwargs={"category_id": catalog_category.pk},
        ),
        data={
            "name": "Alimentos!",
            "is_active": "on",
        },
    )

    assert response.status_code == 200

    catalog_category.refresh_from_db()

    assert catalog_category.name == "Bebidas"
    assert response.context["form"].errors


@pytest.mark.django_db
def test_category_update_does_not_allow_access_to_another_tenant(
    client,
    user,
    membership,
    tenant,
    another_tenant,
):
    authenticate_for_tenant(client, user, tenant, membership)

    other_category = Category.objects.create(
        tenant=another_tenant,
        name="Categoria Protegida",
        slug="categoria-protegida",
    )

    response = client.get(
        reverse(
            "catalog:category-update",
            kwargs={"category_id": other_category.pk},
        )
    )

    assert response.status_code == 404


# =========================================================
# ATIVAÇÃO E DESATIVAÇÃO DE CATEGORIAS
# =========================================================


@pytest.mark.django_db
def test_category_toggle_status_deactivates_category(
    client,
    user,
    membership,
    tenant,
    catalog_category,
):
    authenticate_for_tenant(client, user, tenant, membership)

    assert catalog_category.is_active is True

    response = client.post(
        reverse(
            "catalog:category-toggle-status",
            kwargs={"category_id": catalog_category.pk},
        )
    )

    assert response.status_code == 302
    assert response.url == reverse("catalog:category-list")

    catalog_category.refresh_from_db()

    assert catalog_category.is_active is False


@pytest.mark.django_db
def test_category_toggle_status_activates_category(
    client,
    user,
    membership,
    tenant,
    catalog_category,
):
    authenticate_for_tenant(client, user, tenant, membership)

    catalog_category.is_active = False
    catalog_category.save(update_fields=["is_active"])

    response = client.post(
        reverse(
            "catalog:category-toggle-status",
            kwargs={"category_id": catalog_category.pk},
        )
    )

    assert response.status_code == 302

    catalog_category.refresh_from_db()

    assert catalog_category.is_active is True


@pytest.mark.django_db
def test_category_toggle_status_rejects_get_request(
    client,
    user,
    membership,
    tenant,
    catalog_category,
):
    authenticate_for_tenant(client, user, tenant, membership)

    response = client.get(
        reverse(
            "catalog:category-toggle-status",
            kwargs={"category_id": catalog_category.pk},
        )
    )

    assert response.status_code == 405

    catalog_category.refresh_from_db()

    assert catalog_category.is_active is True


@pytest.mark.django_db
def test_category_toggle_status_does_not_allow_another_tenant_category(
    client,
    user,
    membership,
    tenant,
    another_tenant,
):
    authenticate_for_tenant(client, user, tenant, membership)

    other_category = Category.objects.create(
        tenant=another_tenant,
        name="Categoria de Outra Empresa",
        slug="categoria-de-outra-empresa",
    )

    response = client.post(
        reverse(
            "catalog:category-toggle-status",
            kwargs={"category_id": other_category.pk},
        )
    )

    assert response.status_code == 404

    other_category.refresh_from_db()

    assert other_category.is_active is True


# =========================================================
# CENÁRIOS ADICIONAIS DE CATEGORIAS
# =========================================================


@pytest.mark.django_db
def test_category_create_rejects_empty_name(
    client,
    user,
    membership,
    tenant,
):
    authenticate_for_tenant(client, user, tenant, membership)

    response = client.post(
        reverse("catalog:category-create"),
        data={"name": "", "is_active": "on"},
    )

    assert response.status_code == 200
    assert not Category.objects.filter(tenant=tenant).exists()
    assert "name" in response.context["form"].errors


@pytest.mark.django_db
def test_category_create_allows_same_name_in_another_tenant(
    client,
    user,
    membership,
    tenant,
    another_tenant,
    catalog_category,
):
    authenticate_for_tenant(client, user, tenant, membership)

    response = client.post(
        reverse("catalog:category-create"),
        data={"name": "Mercearia", "is_active": "on"},
    )

    assert response.status_code == 302

    category = Category.objects.get(
        tenant=tenant,
        name="Mercearia",
    )

    other_category = Category.objects.create(
        tenant=another_tenant,
        name="Mercearia",
        slug="mercearia",
    )

    assert category.slug == other_category.slug
    assert category.tenant_id != other_category.tenant_id


@pytest.mark.django_db
def test_category_list_searches_by_name(
    client,
    user,
    membership,
    tenant,
    catalog_category,
):
    authenticate_for_tenant(client, user, tenant, membership)

    Category.objects.create(
        tenant=tenant,
        name="Alimentos",
        slug="alimentos",
    )

    response = client.get(
        reverse("catalog:category-list"),
        {"q": "beb"},
    )

    assert response.status_code == 200

    categories = list(response.context["page_obj"].object_list)

    assert len(categories) == 1
    assert categories[0].name == "Bebidas"


@pytest.mark.django_db
def test_category_list_filters_active_categories(
    client,
    user,
    membership,
    tenant,
    catalog_category,
):
    authenticate_for_tenant(client, user, tenant, membership)

    inactive_category = Category.objects.create(
        tenant=tenant,
        name="Inativa",
        slug="inativa",
        is_active=False,
    )

    response = client.get(
        reverse("catalog:category-list"),
        {"status": "active"},
    )

    assert response.status_code == 200

    categories = list(response.context["page_obj"].object_list)

    assert catalog_category in categories
    assert inactive_category not in categories


@pytest.mark.django_db
def test_category_list_filters_inactive_categories(
    client,
    user,
    membership,
    tenant,
    catalog_category,
):
    authenticate_for_tenant(client, user, tenant, membership)

    catalog_category.is_active = False
    catalog_category.save(update_fields=["is_active"])

    active_category = Category.objects.create(
        tenant=tenant,
        name="Ativa",
        slug="ativa",
        is_active=True,
    )

    response = client.get(
        reverse("catalog:category-list"),
        {"status": "inactive"},
    )

    assert response.status_code == 200

    categories = list(response.context["page_obj"].object_list)

    assert catalog_category in categories
    assert active_category not in categories


@pytest.mark.django_db
def test_category_list_displays_correct_category_counters(
    client,
    user,
    membership,
    tenant,
    catalog_category,
):
    authenticate_for_tenant(client, user, tenant, membership)

    Category.objects.create(
        tenant=tenant,
        name="Outra ativa",
        slug="outra-ativa",
        is_active=True,
    )

    Category.objects.create(
        tenant=tenant,
        name="Inativa",
        slug="inativa",
        is_active=False,
    )

    response = client.get(reverse("catalog:category-list"))

    assert response.status_code == 200
    assert response.context["total_categories"] == 3
    assert response.context["active_categories"] == 2
    assert response.context["inactive_categories"] == 1


@pytest.mark.django_db
def test_category_list_displays_correct_product_count(
    client,
    user,
    membership,
    tenant,
    catalog_category,
    product,
):
    authenticate_for_tenant(client, user, tenant, membership)

    product.category = catalog_category
    product.save(update_fields=["category"])

    response = client.get(reverse("catalog:category-list"))

    assert response.status_code == 200

    categories = list(response.context["page_obj"].object_list)

    category = next(item for item in categories if item.pk == catalog_category.pk)

    assert category.product_count == 1


@pytest.mark.django_db
def test_category_list_paginates_after_twelve_categories(
    client,
    user,
    membership,
    tenant,
):
    authenticate_for_tenant(client, user, tenant, membership)

    for number in range(13):
        Category.objects.create(
            tenant=tenant,
            name=f"Categoria {number:02d}",
            slug=f"categoria-{number:02d}",
        )

    response = client.get(reverse("catalog:category-list"))

    assert response.status_code == 200
    assert response.context["page_obj"].paginator.count == 13
    assert len(response.context["page_obj"].object_list) == 12
    assert response.context["page_obj"].has_next()


@pytest.mark.django_db
def test_category_list_displays_second_page(
    client,
    user,
    membership,
    tenant,
):
    authenticate_for_tenant(client, user, tenant, membership)

    for number in range(13):
        Category.objects.create(
            tenant=tenant,
            name=f"Categoria {number:02d}",
            slug=f"categoria-{number:02d}",
        )

    response = client.get(
        reverse("catalog:category-list"),
        {"page": 2},
    )

    assert response.status_code == 200
    assert response.context["page_obj"].number == 2
    assert len(response.context["page_obj"].object_list) == 1


@pytest.mark.django_db
def test_category_update_allows_keeping_own_name(
    client,
    user,
    membership,
    tenant,
    catalog_category,
):
    authenticate_for_tenant(client, user, tenant, membership)

    response = client.post(
        reverse(
            "catalog:category-update",
            kwargs={"category_id": catalog_category.pk},
        ),
        data={
            "name": catalog_category.name,
            "is_active": "on",
        },
    )

    assert response.status_code == 302

    catalog_category.refresh_from_db()

    assert catalog_category.name == "Bebidas"
    assert catalog_category.slug == "bebidas"


@pytest.mark.django_db
def test_category_update_rejects_empty_name(
    client,
    user,
    membership,
    tenant,
    catalog_category,
):
    authenticate_for_tenant(client, user, tenant, membership)

    response = client.post(
        reverse(
            "catalog:category-update",
            kwargs={"category_id": catalog_category.pk},
        ),
        data={
            "name": "",
            "is_active": "on",
        },
    )

    assert response.status_code == 200

    catalog_category.refresh_from_db()

    assert catalog_category.name == "Bebidas"
    assert "name" in response.context["form"].errors


@pytest.mark.django_db
def test_category_toggle_status_rejects_another_tenant_category(
    client,
    user,
    membership,
    tenant,
    another_tenant,
):
    authenticate_for_tenant(client, user, tenant, membership)

    other_category = Category.objects.create(
        tenant=another_tenant,
        name="Categoria protegida",
        slug="categoria-protegida",
    )

    response = client.post(
        reverse(
            "catalog:category-toggle-status",
            kwargs={"category_id": other_category.pk},
        )
    )

    assert response.status_code == 404

    other_category.refresh_from_db()

    assert other_category.is_active is True


@pytest.mark.django_db
def test_category_list_requires_authentication(client):
    response = client.get(reverse("catalog:category-list"))

    assert response.status_code == 302
    assert reverse("login") in response.url


@pytest.mark.django_db
def test_category_create_requires_authentication(client):
    response = client.get(reverse("catalog:category-create"))

    assert response.status_code == 302
    assert reverse("login") in response.url
