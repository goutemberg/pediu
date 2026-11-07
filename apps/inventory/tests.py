from decimal import Decimal
from datetime import timedelta

import pytest

from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.customers.models import Customer
from apps.orders.models import Order
from apps.inventory.models import (
    StockBalance,
    StockReservation,
    StockMovement,
)
from apps.inventory.services import (
    reserve_stock,
    release_stock,
    consume_stock,
    expire_reservations,
)


def create_order(tenant, number="PED-TEST-001"):
    customer = Customer.objects.create(
        tenant=tenant,
        name="Cliente de Teste",
        phone="81999999999",
    )

    return Order.objects.create(
        tenant=tenant,
        customer=customer,
        number=number,
        customer_name_snapshot="Cliente de Teste",
        customer_phone_snapshot="81999999999",
        subtotal=Decimal("25.00"),
        total=Decimal("25.00"),
    )


# ---------------------------------------------------------
# SALDO DE ESTOQUE
# ---------------------------------------------------------


@pytest.mark.django_db
def test_stock_balance_without_reservations(product):
    balance = product.stock_balance

    assert Decimal(str(balance.physical_quantity)) == Decimal("10.000")
    assert balance.reserved_quantity == Decimal("0.000")
    assert balance.available_quantity == Decimal("10.000")


@pytest.mark.django_db
def test_active_reservation_reduces_available_stock(product, tenant):
    order = create_order(tenant)

    StockReservation.objects.create(
        tenant=tenant,
        product=product,
        order=order,
        quantity=Decimal("2.000"),
        expires_at=timezone.now() + timedelta(minutes=30),
    )

    assert product.stock_balance.reserved_quantity == Decimal("2.000")
    assert product.stock_balance.available_quantity == Decimal("8.000")


@pytest.mark.django_db
def test_expired_active_reservation_does_not_reduce_available_stock(
    product,
    tenant,
):
    order = create_order(tenant)

    StockReservation.objects.create(
        tenant=tenant,
        product=product,
        order=order,
        quantity=Decimal("3.000"),
        status=StockReservation.Status.ACTIVE,
        expires_at=timezone.now() - timedelta(minutes=1),
    )

    assert product.stock_balance.reserved_quantity == Decimal("0.000")
    assert product.stock_balance.available_quantity == Decimal("10.000")


@pytest.mark.django_db
@pytest.mark.parametrize(
    "status",
    [
        StockReservation.Status.RELEASED,
        StockReservation.Status.CONSUMED,
        StockReservation.Status.EXPIRED,
    ],
)
def test_inactive_reservations_do_not_reduce_available_stock(
    product,
    tenant,
    status,
):
    order = create_order(tenant)

    StockReservation.objects.create(
        tenant=tenant,
        product=product,
        order=order,
        quantity=Decimal("4.000"),
        status=status,
        expires_at=timezone.now() + timedelta(minutes=30),
    )

    assert product.stock_balance.reserved_quantity == Decimal("0.000")
    assert product.stock_balance.available_quantity == Decimal("10.000")


# ---------------------------------------------------------
# ISOLAMENTO ENTRE EMPRESAS
# ---------------------------------------------------------


@pytest.mark.django_db
def test_stock_balance_rejects_product_from_another_tenant(
    another_tenant,
    product,
):
    with pytest.raises(ValidationError):
        StockBalance.objects.create(
            tenant=another_tenant,
            product=product,
            physical_quantity=Decimal("5.000"),
        )


@pytest.mark.django_db
def test_reservation_rejects_order_from_another_tenant(
    product,
    another_tenant,
):
    order = create_order(another_tenant, "PED-OUTRA-001")

    with pytest.raises(ValidationError):
        StockReservation.objects.create(
            tenant=product.tenant,
            product=product,
            order=order,
            quantity=Decimal("2.000"),
            expires_at=timezone.now() + timedelta(minutes=30),
        )


@pytest.mark.django_db
def test_reservation_rejects_product_from_another_tenant(
    tenant,
    another_tenant,
):
    from apps.catalog.models import Product

    other_product = Product.objects.create(
        tenant=another_tenant,
        code="SKU-OUTRO",
        name="Produto de Outra Empresa",
        price=Decimal("15.00"),
    )

    order = create_order(tenant)

    with pytest.raises(ValidationError):
        StockReservation.objects.create(
            tenant=tenant,
            product=other_product,
            order=order,
            quantity=Decimal("1.000"),
            expires_at=timezone.now() + timedelta(minutes=30),
        )


@pytest.mark.django_db
def test_stock_movement_rejects_product_from_another_tenant(
    another_tenant,
    product,
):
    with pytest.raises(ValidationError):
        StockMovement.objects.create(
            tenant=another_tenant,
            product=product,
            kind=StockMovement.Kind.IN,
            quantity=Decimal("5.000"),
        )


@pytest.mark.django_db
def test_stock_movement_rejects_non_positive_quantity(product):
    with pytest.raises(ValidationError):
        StockMovement.objects.create(
            tenant=product.tenant,
            product=product,
            kind=StockMovement.Kind.IN,
            quantity=Decimal("0.000"),
        )


# ---------------------------------------------------------
# CRIAÇÃO DE RESERVAS
# ---------------------------------------------------------


@pytest.mark.django_db
def test_reserve_stock_creates_reservation(product, tenant):
    order = create_order(tenant)

    reservation = reserve_stock(
        tenant=tenant,
        product=product,
        order=order,
        quantity=Decimal("3.000"),
    )

    assert reservation.pk is not None
    assert reservation.status == StockReservation.Status.ACTIVE
    assert reservation.quantity == Decimal("3.000")
    assert reservation.expires_at > timezone.now()

    assert product.stock_balance.available_quantity == Decimal("7.000")


@pytest.mark.django_db
def test_reserve_stock_uses_30_minutes_by_default(product, tenant):
    order = create_order(tenant)

    before = timezone.now()

    reservation = reserve_stock(
        tenant=tenant,
        product=product,
        order=order,
        quantity=Decimal("2.000"),
    )

    expected_expiration = before + timedelta(minutes=30)

    assert abs((reservation.expires_at - expected_expiration).total_seconds()) < 2


@pytest.mark.django_db
def test_reserve_stock_rejects_insufficient_quantity(product, tenant):
    order = create_order(tenant)

    with pytest.raises(ValidationError, match="Estoque insuficiente"):
        reserve_stock(
            tenant=tenant,
            product=product,
            order=order,
            quantity=Decimal("11.000"),
        )

    assert not StockReservation.objects.filter(order=order).exists()


@pytest.mark.django_db
def test_reserve_stock_rejects_zero_quantity(product, tenant):
    order = create_order(tenant)

    with pytest.raises(ValidationError):
        reserve_stock(
            tenant=tenant,
            product=product,
            order=order,
            quantity=Decimal("0.000"),
        )


@pytest.mark.django_db
def test_reserve_stock_is_idempotent_for_same_order_and_quantity(
    product,
    tenant,
):
    order = create_order(tenant)

    first = reserve_stock(
        tenant=tenant,
        product=product,
        order=order,
        quantity=Decimal("2.000"),
    )

    second = reserve_stock(
        tenant=tenant,
        product=product,
        order=order,
        quantity=Decimal("2.000"),
    )

    assert first.pk == second.pk
    assert StockReservation.objects.filter(order=order).count() == 1
    assert product.stock_balance.available_quantity == Decimal("8.000")


@pytest.mark.django_db
def test_reserve_stock_rejects_different_quantity_for_existing_reservation(
    product,
    tenant,
):
    order = create_order(tenant)

    reserve_stock(
        tenant=tenant,
        product=product,
        order=order,
        quantity=Decimal("2.000"),
    )

    with pytest.raises(ValidationError):
        reserve_stock(
            tenant=tenant,
            product=product,
            order=order,
            quantity=Decimal("3.000"),
        )


@pytest.mark.django_db
def test_reserve_stock_rejects_order_from_another_tenant(
    product,
    another_tenant,
):
    order = create_order(another_tenant, "PED-OUTRA-002")

    with pytest.raises(ValidationError):
        reserve_stock(
            tenant=product.tenant,
            product=product,
            order=order,
            quantity=Decimal("1.000"),
        )


# ---------------------------------------------------------
# LIBERAÇÃO DE RESERVAS
# ---------------------------------------------------------


@pytest.mark.django_db
def test_release_stock_releases_active_reservation(product, tenant):
    order = create_order(tenant)

    reservation = reserve_stock(
        tenant=tenant,
        product=product,
        order=order,
        quantity=Decimal("3.000"),
    )

    result = release_stock(reservation=reservation)

    reservation.refresh_from_db()

    assert result is True
    assert reservation.status == StockReservation.Status.RELEASED
    assert product.stock_balance.available_quantity == Decimal("10.000")


@pytest.mark.django_db
def test_release_stock_is_idempotent(product, tenant):
    order = create_order(tenant)

    reservation = reserve_stock(
        tenant=tenant,
        product=product,
        order=order,
        quantity=Decimal("3.000"),
    )

    first = release_stock(reservation=reservation)
    second = release_stock(reservation=reservation)

    assert first is True
    assert second is False
    assert (
        StockReservation.objects.filter(
            order=order,
            status=StockReservation.Status.RELEASED,
        ).count()
        == 1
    )


# ---------------------------------------------------------
# CONSUMO DE RESERVAS
# ---------------------------------------------------------


@pytest.mark.django_db
def test_consume_stock_reduces_physical_quantity_and_creates_movement(
    product,
    tenant,
):
    order = create_order(tenant)

    reservation = reserve_stock(
        tenant=tenant,
        product=product,
        order=order,
        quantity=Decimal("3.000"),
    )

    result = consume_stock(reservation=reservation)

    reservation.refresh_from_db()
    product.stock_balance.refresh_from_db()

    assert result is True
    assert reservation.status == StockReservation.Status.CONSUMED
    assert product.stock_balance.physical_quantity == Decimal("7.000")

    movement = StockMovement.objects.get(
        product=product,
        reference=f"Pedido {order.number}",
    )

    assert movement.kind == StockMovement.Kind.OUT
    assert movement.quantity == Decimal("3.000")


@pytest.mark.django_db
def test_consume_stock_is_idempotent(product, tenant):
    order = create_order(tenant)

    reservation = reserve_stock(
        tenant=tenant,
        product=product,
        order=order,
        quantity=Decimal("3.000"),
    )

    first = consume_stock(reservation=reservation)
    second = consume_stock(reservation=reservation)

    assert first is True
    assert second is False

    assert (
        StockMovement.objects.filter(
            reference=f"Pedido {order.number}",
            kind=StockMovement.Kind.OUT,
        ).count()
        == 1
    )

    product.stock_balance.refresh_from_db()

    assert product.stock_balance.physical_quantity == Decimal("7.000")


@pytest.mark.django_db
def test_consume_stock_rejects_released_reservation(product, tenant):
    order = create_order(tenant)

    reservation = reserve_stock(
        tenant=tenant,
        product=product,
        order=order,
        quantity=Decimal("2.000"),
    )

    release_stock(reservation=reservation)

    with pytest.raises(ValidationError):
        consume_stock(reservation=reservation)

    assert not StockMovement.objects.filter(
        reference=f"Pedido {order.number}",
    ).exists()


# ---------------------------------------------------------
# EXPIRAÇÃO DE RESERVAS
# ---------------------------------------------------------


@pytest.mark.django_db
def test_expire_reservations_marks_pending_reservations_as_expired(
    product,
    tenant,
):
    order = create_order(tenant)

    reservation = StockReservation.objects.create(
        tenant=tenant,
        product=product,
        order=order,
        quantity=Decimal("2.000"),
        status=StockReservation.Status.ACTIVE,
        expires_at=timezone.now() - timedelta(minutes=1),
    )

    expired_count = expire_reservations()

    reservation.refresh_from_db()

    assert expired_count == 1
    assert reservation.status == StockReservation.Status.EXPIRED


@pytest.mark.django_db
def test_expire_reservations_does_not_expire_future_reservations(
    product,
    tenant,
):
    order = create_order(tenant)

    reservation = reserve_stock(
        tenant=tenant,
        product=product,
        order=order,
        quantity=Decimal("2.000"),
    )

    expired_count = expire_reservations()

    reservation.refresh_from_db()

    assert expired_count == 0
    assert reservation.status == StockReservation.Status.ACTIVE
