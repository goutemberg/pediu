from decimal import Decimal

import pytest
from django.urls import reverse

from apps.catalog.models import Category, Product
from apps.inventory.models import StockBalance
from apps.orders.models import Order
from apps.tenants.models import Tenant


@pytest.fixture
def storefront_product(tenant):
    category = Category.objects.create(tenant=tenant, name="Rações", slug="racoes")
    product = Product.objects.create(
        tenant=tenant, category=category, code="RAC-001", name="Ração Premium",
        price="89.90", unit="SC", minimum_quantity="1.000", quantity_multiple="1.000",
    )
    StockBalance.objects.create(tenant=tenant, product=product, physical_quantity=Decimal("10"))
    return product


@pytest.mark.django_db
def test_public_storefront_is_accessible_without_login(client, tenant, storefront_product):
    response = client.get(reverse("storefront:store", kwargs={"slug": tenant.slug}))
    assert response.status_code == 200
    assert "Ração Premium" in response.content.decode()


@pytest.mark.django_db
def test_storefront_does_not_show_other_tenant_products(client, tenant, another_tenant, storefront_product):
    Product.objects.create(tenant=another_tenant, code="OUTRO", name="Produto privado", price="10.00")
    response = client.get(reverse("storefront:store", kwargs={"slug": tenant.slug}))
    assert "Produto privado" not in response.content.decode()


@pytest.mark.django_db
def test_suspended_tenant_storefront_is_hidden(client, tenant):
    tenant.status = Tenant.Status.SUSPENDED
    tenant.save(update_fields=["status"])
    response = client.get(reverse("storefront:store", kwargs={"slug": tenant.slug}))
    assert response.status_code == 404


@pytest.mark.django_db
def test_checkout_creates_delivery_order_and_reserves_stock(client, tenant, storefront_product):
    client.post(reverse("storefront:cart-add", kwargs={"slug": tenant.slug}), {
        "product_id": storefront_product.pk, "quantity": "2"
    })
    response = client.post(reverse("storefront:checkout", kwargs={"slug": tenant.slug}), {
        "name": "Cliente Loja", "phone": "81999990000", "fulfillment_method": "delivery",
        "delivery_address": "Rua das Flores, 100", "notes": "Casa azul"
    })
    order = Order.objects.get(tenant=tenant)
    assert response.status_code == 302
    assert order.fulfillment_method == Order.Fulfillment.DELIVERY
    assert order.delivery_address == "Rua das Flores, 100"
    assert order.notes == "Casa azul"
    assert order.status == Order.Status.PENDING
    assert order.reservations.filter(status="active").exists()


@pytest.mark.django_db
def test_delivery_checkout_requires_address(client, tenant, storefront_product):
    client.post(reverse("storefront:cart-add", kwargs={"slug": tenant.slug}), {
        "product_id": storefront_product.pk, "quantity": "1"
    })
    response = client.post(reverse("storefront:checkout", kwargs={"slug": tenant.slug}), {
        "name": "Cliente Loja", "phone": "81999990000", "fulfillment_method": "delivery",
        "delivery_address": ""
    })
    assert response.status_code == 200
    assert not Order.objects.filter(tenant=tenant).exists()


@pytest.mark.django_db
def test_storefront_paginates_products_in_batches(client, tenant):
    for index in range(26):
        Product.objects.create(
            tenant=tenant,
            code=f"PAGE-{index:03d}",
            name=f"Produto {index:03d}",
            price="5.00",
        )

    response = client.get(reverse("storefront:store", kwargs={"slug": tenant.slug}))
    assert response.status_code == 200
    assert len(response.context["product_rows"]) == 24
    assert response.context["has_next"] is True

    append_response = client.get(
        reverse("storefront:store", kwargs={"slug": tenant.slug}) + "?pagina=2",
        HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        HTTP_X_STOREFRONT_APPEND="1",
    )
    assert append_response.status_code == 200
    assert append_response["X-Has-Next"] == "0"
    assert "Produto 024" in append_response.content.decode()
    assert "Produto 025" in append_response.content.decode()


@pytest.mark.django_db
def test_ajax_category_request_returns_product_grid(client, tenant, storefront_product):
    response = client.get(
        reverse("storefront:store", kwargs={"slug": tenant.slug}) + "?categoria=racoes",
        HTTP_X_REQUESTED_WITH="XMLHttpRequest",
    )
    assert response.status_code == 200
    assert 'id="product-grid"' in response.content.decode()
    assert "Ração Premium" in response.content.decode()


@pytest.mark.django_db
def test_cart_remembers_last_catalog_category(client, tenant, storefront_product):
    store_url = reverse("storefront:store", kwargs={"slug": tenant.slug}) + "?categoria=racoes&q=Premium"
    client.get(store_url)
    response = client.get(reverse("storefront:cart", kwargs={"slug": tenant.slug}))
    assert response.status_code == 200
    cart_html = response.content.decode()
    assert "categoria=racoes" in cart_html
    assert "q=Premium" in cart_html
