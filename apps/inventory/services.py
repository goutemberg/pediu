"""
Operações de estoque do pediu.

Toda operação de escrita é transacional.

Ordem dos bloqueios nas operações de pedido:
1. Order, quando aplicável.
2. StockBalance.
3. StockReservation.
"""

from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.orders.models import Order

from .models import (
    StockBalance,
    StockMovement,
    StockReservation,
)

RESERVATION_MINUTES = 30


def _get_balance(*, tenant, product):
    """Busca e bloqueia o saldo do produto."""

    try:
        return StockBalance.objects.select_for_update().get(
            tenant=tenant,
            product=product,
        )
    except StockBalance.DoesNotExist:
        raise ValidationError(
            "Não existe saldo cadastrado para este produto nesta empresa."
        )


def _get_locked_reservation(*, reservation_id):
    """Busca e bloqueia uma reserva."""

    try:
        return StockReservation.objects.select_for_update().get(pk=reservation_id)
    except StockReservation.DoesNotExist:
        raise ValidationError("Reserva não encontrada.")


def _validate_quantity(quantity):
    """Normaliza e valida quantidades."""

    try:
        quantity = Decimal(str(quantity))
    except (TypeError, ValueError, ArithmeticError):
        raise ValidationError("Quantidade inválida.")

    if not quantity.is_finite() or quantity <= 0:
        raise ValidationError("A quantidade deve ser maior que zero.")

    return quantity


@transaction.atomic
def assert_available(*, tenant, product, quantity):
    """Verifica se existe estoque disponível."""

    quantity = _validate_quantity(quantity)

    balance = _get_balance(
        tenant=tenant,
        product=product,
    )

    if balance.available_quantity < quantity:
        raise ValidationError("Estoque insuficiente para atender ao pedido.")

    return balance


@transaction.atomic
def reserve_stock(
    *,
    tenant,
    product,
    order,
    quantity,
    expires_in_minutes=RESERVATION_MINUTES,
):
    """Reserva estoque para um pedido pendente."""

    quantity = _validate_quantity(quantity)

    if expires_in_minutes <= 0:
        raise ValidationError("O prazo da reserva deve ser maior que zero.")

    if order.tenant_id != tenant.id:
        raise ValidationError("O pedido não pertence à empresa informada.")

    if product.tenant_id != tenant.id:
        raise ValidationError("O produto não pertence à empresa informada.")

    if order.status != Order.Status.PENDING:
        raise ValidationError("Só é possível reservar estoque para pedidos pendentes.")

    balance = _get_balance(
        tenant=tenant,
        product=product,
    )

    existing = (
        StockReservation.objects.select_for_update()
        .filter(
            tenant=tenant,
            product=product,
            order=order,
            status=StockReservation.Status.ACTIVE,
        )
        .first()
    )

    now = timezone.now()

    if existing:
        if existing.expires_at > now:
            if existing.quantity != quantity:
                raise ValidationError(
                    "Já existe uma reserva ativa com quantidade diferente."
                )

            return existing

        existing.status = StockReservation.Status.EXPIRED
        existing.save(update_fields=["status"])

    if balance.available_quantity < quantity:
        raise ValidationError("Estoque insuficiente para atender ao pedido.")

    return StockReservation.objects.create(
        tenant=tenant,
        product=product,
        order=order,
        quantity=quantity,
        status=StockReservation.Status.ACTIVE,
        expires_at=now + timedelta(minutes=expires_in_minutes),
    )


@transaction.atomic
def release_stock(*, reservation):
    """Libera uma reserva ativa. Operação idempotente."""

    try:
        initial = StockReservation.objects.get(pk=reservation.pk)
    except StockReservation.DoesNotExist:
        raise ValidationError("Reserva não encontrada.")

    _get_balance(
        tenant=initial.tenant,
        product=initial.product,
    )

    locked = _get_locked_reservation(
        reservation_id=initial.pk,
    )

    if locked.status != StockReservation.Status.ACTIVE:
        return False

    locked.status = StockReservation.Status.RELEASED
    locked.save(update_fields=["status"])

    return True


@transaction.atomic
def consume_stock(*, reservation):
    """
    Consome uma reserva ativa e registra a saída física.

    A validação de transição do pedido é responsabilidade
    da camada de serviços de pedidos.
    """

    try:
        initial = StockReservation.objects.get(pk=reservation.pk)
    except StockReservation.DoesNotExist:
        raise ValidationError("Reserva não encontrada.")

    balance = _get_balance(
        tenant=initial.tenant,
        product=initial.product,
    )

    locked = _get_locked_reservation(
        reservation_id=initial.pk,
    )

    if locked.status == StockReservation.Status.CONSUMED:
        return False

    if locked.status != StockReservation.Status.ACTIVE:
        raise ValidationError("Não é possível consumir uma reserva que não está ativa.")

    order = locked.order

    if order.status == Order.Status.PENDING and locked.expires_at <= timezone.now():
        raise ValidationError(
            "A reserva expirou. O pedido precisa ser aprovado "
            "dentro do prazo de validade."
        )

    if order.status in [
        Order.Status.REJECTED,
        Order.Status.CANCELLED,
        Order.Status.EXPIRED,
    ]:
        raise ValidationError("Não é possível consumir estoque de um pedido encerrado.")

    if balance.physical_quantity < locked.quantity:
        raise ValidationError(
            "O estoque físico é insuficiente para concluir o consumo."
        )

    balance.physical_quantity -= locked.quantity
    balance.save(
        update_fields=[
            "physical_quantity",
            "updated_at",
        ]
    )

    StockMovement.objects.create(
        tenant=locked.tenant,
        product=locked.product,
        kind=StockMovement.Kind.OUT,
        quantity=locked.quantity,
        reference=f"Pedido {locked.order.number}",
        note="Consumo de reserva de pedido.",
    )

    locked.status = StockReservation.Status.CONSUMED
    locked.save(update_fields=["status"])

    return True


@transaction.atomic
def _expire_order_reservations(*, order_id, now):
    """
    Expira um pedido pendente e todas as suas reservas ativas.

    Só expira o pedido quando pelo menos uma reserva ativa
    já ultrapassou o prazo.
    """

    try:
        order = Order.objects.select_for_update().get(pk=order_id)
    except Order.DoesNotExist:
        return 0

    if order.status != Order.Status.PENDING:
        return 0

    active_reservations = list(
        StockReservation.objects.filter(
            order=order,
            status=StockReservation.Status.ACTIVE,
        ).order_by("product_id", "id")
    )

    if not active_reservations:
        return 0

    if not any(reservation.expires_at <= now for reservation in active_reservations):
        return 0

    product_ids = sorted(
        {reservation.product_id for reservation in active_reservations}
    )

    # Bloqueia todos os saldos antes de bloquear as reservas.
    balances = list(
        StockBalance.objects.select_for_update()
        .filter(
            tenant=order.tenant,
            product_id__in=product_ids,
        )
        .order_by("product_id")
    )

    if len(balances) != len(product_ids):
        raise ValidationError("Não foi possível localizar todos os saldos do pedido.")

    locked_reservations = list(
        StockReservation.objects.select_for_update()
        .filter(
            order=order,
            status=StockReservation.Status.ACTIVE,
        )
        .order_by("product_id", "id")
    )

    expired_count = 0

    for reservation in locked_reservations:
        reservation.status = StockReservation.Status.EXPIRED
        reservation.save(update_fields=["status"])
        expired_count += 1

    order.status = Order.Status.EXPIRED
    order.save(update_fields=["status", "updated_at"])

    return expired_count


def expire_reservations(*, limit=100):
    """
    Expira pedidos pendentes que tenham pelo menos uma reserva vencida.

    Todas as reservas ativas de um pedido expirado são encerradas.

    O limite controla a quantidade máxima de pedidos processados
    por execução.
    """

    if limit <= 0:
        raise ValidationError("O limite deve ser maior que zero.")

    now = timezone.now()

    order_ids = list(
        StockReservation.objects.filter(
            status=StockReservation.Status.ACTIVE,
            expires_at__lte=now,
            order__status=Order.Status.PENDING,
        )
        .order_by("order_id")
        .values_list("order_id", flat=True)
        .distinct()[:limit]
    )

    expired_count = 0

    for order_id in order_ids:
        expired_count += _expire_order_reservations(
            order_id=order_id,
            now=now,
        )

    return expired_count
