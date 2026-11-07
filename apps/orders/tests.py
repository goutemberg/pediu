import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.catalog.models import Product
from apps.customers.models import Customer
from apps.inventory.models import (
    StockBalance,
    StockMovement,
    StockReservation,
)
from .models import Order, OrderItem
from .services import (
    create_order,
    approve_order,
    reject_order,
    cancel_order,
    complete_order,
    expire_order,
)


@pytest.fixture
def customer_data():
    return {
        "name": "Cliente de Teste",
        "phone": "81999999999",
    }


def make_product(
    tenant,
    *,
    code,
    name,
    price="10.00",
    stock="10.000",
    minimum_quantity=1,
    quantity_multiple=1,
    is_active=True,
):
    product = Product.objects.create(
        tenant=tenant,
        code=code,
        name=name,
        price=price,
        minimum_quantity=minimum_quantity,
        quantity_multiple=quantity_multiple,
        is_active=is_active,
    )

    StockBalance.objects.create(
        tenant=tenant,
        product=product,
        physical_quantity=Decimal(stock),
    )

    return product


def make_order(*, tenant, customer_data, products):
    """Cria um pedido usando o fluxo real de criação."""

    items = [
        {
            "product_id": product.pk,
            "quantity": str(quantity),
        }
        for product, quantity in products
    ]

    return create_order(
        tenant=tenant,
        customer_data=customer_data,
        items=items,
    )


@pytest.mark.django_db
def test_new_order_is_pending(tenant):
    customer = Customer.objects.create(
        tenant=tenant,
        name="Cliente",
        phone="81999999999",
    )

    order = Order.objects.create(
        tenant=tenant,
        customer=customer,
        number="PED-0001",
        customer_name_snapshot="Cliente",
        customer_phone_snapshot="81999999999",
        subtotal="10.00",
        total="10.00",
    )

    assert order.status == Order.Status.PENDING


@pytest.mark.django_db
def test_order_number_unique_per_tenant(tenant):
    customer = Customer.objects.create(
        tenant=tenant,
        name="Cliente",
        phone="81999999999",
    )

    data = {
        "tenant": tenant,
        "customer": customer,
        "number": "PED-1",
        "customer_name_snapshot": "Cliente",
        "customer_phone_snapshot": "81999999999",
        "subtotal": "1.00",
        "total": "1.00",
    }

    Order.objects.create(**data)

    with pytest.raises(IntegrityError), transaction.atomic():
        Order.objects.create(**data)


@pytest.mark.django_db
def test_create_order_successfully(tenant, product, customer_data):
    order = create_order(
        tenant=tenant,
        customer_data=customer_data,
        items=[
            {
                "product_id": product.pk,
                "quantity": "2",
            }
        ],
    )

    order.refresh_from_db()

    assert order.status == Order.Status.PENDING
    assert order.subtotal == Decimal("25.00")
    assert order.total == Decimal("25.00")
    assert order.items.count() == 1

    item = order.items.first()

    assert item.product == product
    assert item.quantity == Decimal("2")
    assert item.unit_price == Decimal("12.50")
    assert item.line_total == Decimal("25.00")

    reservation = StockReservation.objects.get(order=order)

    assert reservation.quantity == Decimal("2")
    assert reservation.status == StockReservation.Status.ACTIVE

    balance = StockBalance.objects.get(product=product)

    assert balance.available_quantity == Decimal("8.000")


@pytest.mark.django_db
def test_create_order_creates_customer(tenant, product, customer_data):
    assert Customer.objects.filter(tenant=tenant).count() == 0

    order = create_order(
        tenant=tenant,
        customer_data=customer_data,
        items=[{"product_id": product.pk, "quantity": "1"}],
    )

    assert Customer.objects.filter(tenant=tenant).count() == 1
    assert order.customer.name == customer_data["name"]
    assert order.customer.phone == customer_data["phone"]


@pytest.mark.django_db
def test_create_order_reuses_customer_by_phone(tenant, product, customer_data):
    existing_customer = Customer.objects.create(
        tenant=tenant,
        name="Nome Antigo",
        phone=customer_data["phone"],
    )

    order = create_order(
        tenant=tenant,
        customer_data={
            **customer_data,
            "name": "Nome Atualizado",
        },
        items=[{"product_id": product.pk, "quantity": "1"}],
    )

    assert Customer.objects.filter(tenant=tenant).count() == 1
    assert order.customer_id == existing_customer.pk

    existing_customer.refresh_from_db()

    assert existing_customer.name == "Nome Atualizado"


@pytest.mark.django_db
def test_create_order_uses_server_product_price(tenant, product, customer_data):
    order = create_order(
        tenant=tenant,
        customer_data=customer_data,
        items=[
            {
                "product_id": product.pk,
                "quantity": "2",
                "price": "0.01",
            }
        ],
    )

    item = order.items.get()

    assert item.unit_price == Decimal("12.50")
    assert item.line_total == Decimal("25.00")
    assert order.total == Decimal("25.00")


@pytest.mark.django_db
def test_create_order_with_multiple_products(tenant, product, customer_data):
    second_product = make_product(
        tenant,
        code="SKU-002",
        name="Segundo Produto",
        price="5.00",
        stock="20.000",
    )

    order = create_order(
        tenant=tenant,
        customer_data=customer_data,
        items=[
            {"product_id": product.pk, "quantity": "2"},
            {"product_id": second_product.pk, "quantity": "3"},
        ],
    )

    assert order.items.count() == 2
    assert order.subtotal == Decimal("40.00")
    assert order.total == Decimal("40.00")
    assert StockReservation.objects.filter(order=order).count() == 2


@pytest.mark.django_db
def test_duplicate_product_lines_are_aggregated(tenant, product, customer_data):
    order = create_order(
        tenant=tenant,
        customer_data=customer_data,
        items=[
            {"product_id": product.pk, "quantity": "2"},
            {"product_id": product.pk, "quantity": "3"},
        ],
    )

    assert order.items.count() == 1
    assert order.items.get().quantity == Decimal("5")
    assert order.total == Decimal("62.50")

    reservation = StockReservation.objects.get(order=order)

    assert reservation.quantity == Decimal("5")


@pytest.mark.django_db
def test_create_order_rejects_product_from_another_tenant(
    tenant, another_tenant, customer_data
):
    foreign_product = make_product(
        another_tenant,
        code="FOREIGN-001",
        name="Produto de Outra Loja",
    )

    with pytest.raises(ValidationError):
        create_order(
            tenant=tenant,
            customer_data=customer_data,
            items=[
                {
                    "product_id": foreign_product.pk,
                    "quantity": "1",
                }
            ],
        )

    assert Order.objects.filter(tenant=tenant).count() == 0


@pytest.mark.django_db
def test_create_order_rejects_inactive_product(tenant, product, customer_data):
    product.is_active = False
    product.save()

    with pytest.raises(ValidationError):
        create_order(
            tenant=tenant,
            customer_data=customer_data,
            items=[{"product_id": product.pk, "quantity": "1"}],
        )

    assert Order.objects.filter(tenant=tenant).count() == 0


@pytest.mark.django_db
def test_create_order_rejects_insufficient_stock(tenant, product, customer_data):
    with pytest.raises(ValidationError):
        create_order(
            tenant=tenant,
            customer_data=customer_data,
            items=[{"product_id": product.pk, "quantity": "11"}],
        )

    assert Order.objects.filter(tenant=tenant).count() == 0
    assert StockReservation.objects.count() == 0


@pytest.mark.django_db
def test_create_order_rejects_quantity_below_minimum(tenant, customer_data):
    product = make_product(
        tenant,
        code="SKU-MIN",
        name="Produto com mínimo",
        minimum_quantity=3,
    )

    with pytest.raises(ValidationError):
        create_order(
            tenant=tenant,
            customer_data=customer_data,
            items=[{"product_id": product.pk, "quantity": "2"}],
        )

    assert Order.objects.filter(tenant=tenant).count() == 0


@pytest.mark.django_db
def test_create_order_rejects_invalid_quantity_multiple(tenant, customer_data):
    product = make_product(
        tenant,
        code="SKU-MULT",
        name="Produto com múltiplo",
        quantity_multiple=3,
    )

    with pytest.raises(ValidationError):
        create_order(
            tenant=tenant,
            customer_data=customer_data,
            items=[{"product_id": product.pk, "quantity": "4"}],
        )

    assert Order.objects.filter(tenant=tenant).count() == 0


@pytest.mark.django_db
def test_create_order_rolls_back_everything_on_stock_failure(
    tenant, product, customer_data
):
    second_product = make_product(
        tenant,
        code="SKU-002",
        name="Produto sem estoque suficiente",
        stock="2.000",
    )

    with pytest.raises(ValidationError):
        create_order(
            tenant=tenant,
            customer_data=customer_data,
            items=[
                {"product_id": product.pk, "quantity": "3"},
                {"product_id": second_product.pk, "quantity": "5"},
            ],
        )

    assert Order.objects.filter(tenant=tenant).count() == 0
    assert OrderItem.objects.count() == 0
    assert StockReservation.objects.count() == 0
    assert Customer.objects.filter(tenant=tenant).count() == 0

    first_balance = StockBalance.objects.get(product=product)

    assert first_balance.available_quantity == Decimal("10.000")


@pytest.mark.django_db
def test_create_order_is_idempotent(tenant, product, customer_data):
    key = uuid.uuid4()

    first_order = create_order(
        tenant=tenant,
        customer_data=customer_data,
        items=[{"product_id": product.pk, "quantity": "2"}],
        idempotency_key=key,
    )

    second_order = create_order(
        tenant=tenant,
        customer_data=customer_data,
        items=[{"product_id": product.pk, "quantity": "2"}],
        idempotency_key=key,
    )

    assert first_order.pk == second_order.pk
    assert Order.objects.filter(tenant=tenant).count() == 1
    assert StockReservation.objects.filter(order=first_order).count() == 1

    balance = StockBalance.objects.get(product=product)

    assert balance.available_quantity == Decimal("8.000")


# ============================================================
# CICLO DE VIDA DOS PEDIDOS
# ============================================================


@pytest.mark.django_db
def test_approve_order_keeps_stock_reserved(tenant, product, customer_data):
    order = make_order(
        tenant=tenant,
        customer_data=customer_data,
        products=[(product, 2)],
    )

    approved = approve_order(
        tenant=tenant,
        order_id=order.pk,
    )

    reservation = StockReservation.objects.get(order=order)
    balance = StockBalance.objects.get(product=product)

    assert approved.status == Order.Status.APPROVED
    assert reservation.status == StockReservation.Status.ACTIVE
    assert balance.available_quantity == Decimal("8.000")


@pytest.mark.django_db
def test_reject_order_releases_stock(tenant, product, customer_data):
    order = make_order(
        tenant=tenant,
        customer_data=customer_data,
        products=[(product, 2)],
    )

    rejected = reject_order(
        tenant=tenant,
        order_id=order.pk,
    )

    reservation = StockReservation.objects.get(order=order)
    balance = StockBalance.objects.get(product=product)

    assert rejected.status == Order.Status.REJECTED
    assert reservation.status == StockReservation.Status.RELEASED
    assert balance.available_quantity == Decimal("10.000")


@pytest.mark.django_db
def test_cancel_approved_order_releases_stock(tenant, product, customer_data):
    order = make_order(
        tenant=tenant,
        customer_data=customer_data,
        products=[(product, 2)],
    )

    approve_order(tenant=tenant, order_id=order.pk)

    cancelled = cancel_order(
        tenant=tenant,
        order_id=order.pk,
    )

    reservation = StockReservation.objects.get(order=order)
    balance = StockBalance.objects.get(product=product)

    assert cancelled.status == Order.Status.CANCELLED
    assert reservation.status == StockReservation.Status.RELEASED
    assert balance.available_quantity == Decimal("10.000")


@pytest.mark.django_db
def test_complete_ready_order_consumes_stock(tenant, product, customer_data):
    order = make_order(
        tenant=tenant,
        customer_data=customer_data,
        products=[(product, 2)],
    )

    approve_order(tenant=tenant, order_id=order.pk)

    order.status = Order.Status.READY
    order.save(update_fields=["status", "updated_at"])

    completed = complete_order(
        tenant=tenant,
        order_id=order.pk,
    )

    reservation = StockReservation.objects.get(order=order)
    balance = StockBalance.objects.get(product=product)
    movement = StockMovement.objects.get(
        reference=f"Pedido {order.number}",
    )

    assert completed.status == Order.Status.COMPLETED
    assert reservation.status == StockReservation.Status.CONSUMED
    assert balance.physical_quantity == Decimal("8.000")
    assert movement.kind == StockMovement.Kind.OUT
    assert movement.quantity == Decimal("2")


@pytest.mark.django_db
def test_cannot_complete_pending_order(tenant, product, customer_data):
    order = make_order(
        tenant=tenant,
        customer_data=customer_data,
        products=[(product, 2)],
    )

    with pytest.raises(ValidationError):
        complete_order(
            tenant=tenant,
            order_id=order.pk,
        )

    order.refresh_from_db()
    balance = StockBalance.objects.get(product=product)

    assert order.status == Order.Status.PENDING
    assert balance.physical_quantity == Decimal("10.000")


@pytest.mark.django_db
def test_expire_order_releases_all_reservations(tenant, product, customer_data):
    second_product = make_product(
        tenant,
        code="SKU-002",
        name="Segundo Produto",
        stock="20.000",
    )

    order = make_order(
        tenant=tenant,
        customer_data=customer_data,
        products=[
            (product, 2),
            (second_product, 3),
        ],
    )

    expired_time = timezone.now() - timedelta(minutes=1)

    StockReservation.objects.filter(order=order).update(
        expires_at=expired_time,
    )

    expired = expire_order(
        tenant=tenant,
        order_id=order.pk,
    )

    reservations = StockReservation.objects.filter(order=order)

    first_balance = StockBalance.objects.get(product=product)
    second_balance = StockBalance.objects.get(product=second_product)

    assert expired.status == Order.Status.EXPIRED
    assert reservations.count() == 2
    assert not reservations.exclude(status=StockReservation.Status.EXPIRED).exists()
    assert first_balance.available_quantity == Decimal("10.000")
    assert second_balance.available_quantity == Decimal("20.000")


@pytest.mark.django_db
def test_approve_expired_order_persists_expiration(tenant, product, customer_data):
    order = make_order(
        tenant=tenant,
        customer_data=customer_data,
        products=[(product, 2)],
    )

    StockReservation.objects.filter(order=order).update(
        expires_at=timezone.now() - timedelta(minutes=1),
    )

    with pytest.raises(ValidationError):
        approve_order(
            tenant=tenant,
            order_id=order.pk,
        )

    order.refresh_from_db()

    reservation = StockReservation.objects.get(order=order)
    balance = StockBalance.objects.get(product=product)

    assert order.status == Order.Status.EXPIRED
    assert reservation.status == StockReservation.Status.EXPIRED
    assert balance.available_quantity == Decimal("10.000")


@pytest.mark.django_db
def test_cannot_reject_already_approved_order(tenant, product, customer_data):
    order = make_order(
        tenant=tenant,
        customer_data=customer_data,
        products=[(product, 2)],
    )

    approve_order(
        tenant=tenant,
        order_id=order.pk,
    )

    with pytest.raises(ValidationError):
        reject_order(
            tenant=tenant,
            order_id=order.pk,
        )

    order.refresh_from_db()

    assert order.status == Order.Status.APPROVED
