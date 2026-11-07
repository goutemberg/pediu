"""
Casos de uso de pedidos.

Toda escrita deve acontecer por esta camada de serviços.
As operações são transacionais e integram pedidos, clientes
e reservas de estoque.
"""

import uuid
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.tenants.models import Tenant
from apps.customers.models import Customer
from apps.catalog.models import Product
from apps.inventory.models import StockBalance, StockReservation
from apps.inventory.services import (
    reserve_stock,
    release_stock,
    consume_stock,
)

from .models import Order, OrderItem

CENT = Decimal("0.01")
ZERO = Decimal("0.00")


def _decimal_quantity(value):
    """Converte e valida uma quantidade."""

    try:
        quantity = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ValidationError("Quantidade inválida.")

    if not quantity.is_finite() or quantity <= 0:
        raise ValidationError("A quantidade deve ser maior que zero.")

    return quantity


def _money(value):
    """Arredonda valores monetários para duas casas decimais."""

    return Decimal(value).quantize(
        CENT,
        rounding=ROUND_HALF_UP,
    )


def _validate_customer_data(customer_data):
    """Valida os dados básicos do cliente."""

    if not isinstance(customer_data, dict):
        raise ValidationError("Os dados do cliente são inválidos.")

    name = str(customer_data.get("name", "")).strip()
    phone = str(customer_data.get("phone", "")).strip()
    email = str(customer_data.get("email", "")).strip()
    notes = str(customer_data.get("notes", "")).strip()

    if not name:
        raise ValidationError("O nome do cliente é obrigatório.")

    if len(name) > 160:
        raise ValidationError("O nome do cliente deve ter até 160 caracteres.")

    if not phone:
        raise ValidationError("O telefone do cliente é obrigatório.")

    if len(phone) > 30:
        raise ValidationError("O telefone deve ter até 30 caracteres.")

    return {
        "name": name,
        "phone": phone,
        "email": email,
        "notes": notes,
    }


def _get_or_create_customer(*, tenant, customer_data):
    """Localiza o cliente pelo telefone ou cadastra um novo."""

    customer, created = Customer.objects.get_or_create(
        tenant=tenant,
        phone=customer_data["phone"],
        defaults={
            "name": customer_data["name"],
            "email": customer_data["email"],
            "notes": customer_data["notes"],
        },
    )

    if not created:
        changed_fields = []

        if customer.name != customer_data["name"]:
            customer.name = customer_data["name"]
            changed_fields.append("name")

        if customer.email != customer_data["email"]:
            customer.email = customer_data["email"]
            changed_fields.append("email")

        if customer_data["notes"] and customer.notes != customer_data["notes"]:
            customer.notes = customer_data["notes"]
            changed_fields.append("notes")

        if changed_fields:
            customer.save(update_fields=changed_fields)

    return customer


def _normalize_items(items):
    """Valida e agrupa os itens por produto."""

    if not isinstance(items, (list, tuple)) or not items:
        raise ValidationError("O pedido precisa ter pelo menos um produto.")

    quantities = {}

    for item in items:
        if not isinstance(item, dict):
            raise ValidationError("Um dos itens do pedido é inválido.")

        product_id = item.get("product_id")

        if product_id is None:
            raise ValidationError("Um item não informou o produto.")

        try:
            product_id = int(product_id)
        except (TypeError, ValueError):
            raise ValidationError("Identificador de produto inválido.")

        if product_id <= 0:
            raise ValidationError("Identificador de produto inválido.")

        quantity = _decimal_quantity(item.get("quantity"))

        quantities[product_id] = quantities.get(product_id, Decimal("0.000")) + quantity

    return quantities


def _validate_product_quantity(*, product, quantity):
    """Valida quantidade mínima e múltiplo de venda."""

    minimum = Decimal(str(product.minimum_quantity))
    multiple = Decimal(str(product.quantity_multiple))

    if quantity < minimum:
        raise ValidationError(f"A quantidade mínima de {product.name} é {minimum}.")

    if quantity % multiple != 0:
        raise ValidationError(
            f"A quantidade de {product.name} deve ser múltipla de {multiple}."
        )


def _get_locked_order(*, tenant, order_id):
    """Busca e bloqueia um pedido pertencente à empresa."""

    try:
        return Order.objects.select_for_update().get(
            tenant=tenant,
            pk=order_id,
        )
    except Order.DoesNotExist:
        raise ValidationError("Pedido não encontrado.")


def _expire_locked_order(order):
    """
    Expira um pedido pendente e suas reservas.

    Ordem dos bloqueios:
    saldo de estoque -> reserva.
    """

    reservations = list(
        StockReservation.objects.filter(
            order=order,
            status=StockReservation.Status.ACTIVE,
        ).order_by("product_id", "id")
    )

    product_ids = sorted({reservation.product_id for reservation in reservations})

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

    for reservation in locked_reservations:
        reservation.status = StockReservation.Status.EXPIRED
        reservation.save(update_fields=["status"])

    order.status = Order.Status.EXPIRED
    order.save(update_fields=["status", "updated_at"])

    return order


@transaction.atomic
def create_order(
    *,
    tenant,
    customer_data,
    items,
    idempotency_key=None,
    fulfillment_method="pickup",
    delivery_address="",
):
    """
    Cria um pedido e reserva o estoque de seus produtos.

    Regras:
    - Pedido inicia como PENDING.
    - Cliente é identificado pelo telefone dentro da empresa.
    - Produtos precisam estar ativos e pertencer à empresa.
    - Preços são obtidos diretamente do banco.
    - Quantidades respeitam mínimo e múltiplo de venda.
    - Estoque é reservado por 30 minutos.
    - Itens armazenam snapshots dos dados comerciais.
    - A chave de idempotência evita duplicação pelo serviço.

    Retorna:
        Order
    """

    try:
        tenant = Tenant.objects.select_for_update().get(pk=tenant.pk)
    except Tenant.DoesNotExist:
        raise ValidationError("Empresa não encontrada.")

    if idempotency_key:
        try:
            idempotency_key = uuid.UUID(str(idempotency_key))
        except (ValueError, TypeError, AttributeError):
            raise ValidationError("Chave de idempotência inválida.")

        existing_order = Order.objects.filter(
            tenant=tenant,
            idempotency_key=idempotency_key,
        ).first()

        if existing_order:
            return existing_order

    customer_data = _validate_customer_data(customer_data)
    quantities = _normalize_items(items)

    fulfillment_method = str(fulfillment_method or "pickup").strip().lower()
    delivery_address = str(delivery_address or "").strip()
    if fulfillment_method not in ("delivery", "pickup"):
        raise ValidationError("Forma de recebimento inválida.")
    if fulfillment_method == "delivery" and not delivery_address:
        raise ValidationError("Informe o endereço para entrega.")
    if len(delivery_address) > 1000:
        raise ValidationError("O endereço deve ter até 1.000 caracteres.")

    products = list(
        Product.objects.select_for_update()
        .filter(
            tenant=tenant,
            id__in=quantities.keys(),
            is_active=True,
        )
        .order_by("id")
    )

    products_by_id = {product.id: product for product in products}

    missing_ids = set(quantities.keys()) - set(products_by_id.keys())

    if missing_ids:
        raise ValidationError(
            "Um ou mais produtos não existem, estão inativos "
            "ou não pertencem a esta empresa."
        )

    customer = _get_or_create_customer(
        tenant=tenant,
        customer_data=customer_data,
    )

    order_number = f"PED-{uuid.uuid4().hex[:12].upper()}"

    order = Order.objects.create(
        tenant=tenant,
        customer=customer,
        number=order_number,
        status=Order.Status.PENDING,
        customer_name_snapshot=customer.name,
        customer_phone_snapshot=customer.phone,
        subtotal=ZERO,
        total=ZERO,
        notes=customer_data["notes"],
        idempotency_key=idempotency_key,
        fulfillment_method=fulfillment_method,
        delivery_address=delivery_address if fulfillment_method == "delivery" else "",
    )

    order_items = []
    reservations = []
    subtotal = ZERO

    for product_id in sorted(quantities):
        product = products_by_id[product_id]
        quantity = quantities[product_id]

        _validate_product_quantity(
            product=product,
            quantity=quantity,
        )

        unit_price = _money(product.price)
        line_total = _money(unit_price * quantity)

        order_items.append(
            OrderItem(
                tenant=tenant,
                order=order,
                product=product,
                product_code_snapshot=product.code,
                product_name_snapshot=product.name,
                unit_snapshot=product.unit,
                quantity=quantity,
                unit_price=unit_price,
                line_total=line_total,
            )
        )

        subtotal += line_total

        reservations.append(
            {
                "product": product,
                "quantity": quantity,
            }
        )

    subtotal = _money(subtotal)

    OrderItem.objects.bulk_create(order_items)

    order.subtotal = subtotal
    order.total = subtotal

    order.save(
        update_fields=[
            "subtotal",
            "total",
            "updated_at",
        ]
    )

    for item in reservations:
        reserve_stock(
            tenant=tenant,
            product=item["product"],
            order=order,
            quantity=item["quantity"],
        )

    return order


def approve_order(*, tenant, order_id):
    """
    Aprova um pedido pendente e mantém suas reservas.

    Se alguma reserva estiver vencida, expira o pedido
    e confirma a expiração antes de retornar o erro.
    """

    expired = False
    order = None

    with transaction.atomic():
        order = _get_locked_order(
            tenant=tenant,
            order_id=order_id,
        )

        if order.status != Order.Status.PENDING:
            raise ValidationError("Somente pedidos pendentes podem ser aprovados.")

        reservations = list(order.reservations.all().order_by("product_id", "id"))

        if not reservations:
            raise ValidationError("O pedido não possui reservas de estoque.")

        now = timezone.now()

        has_invalid_reservation = any(
            reservation.status != StockReservation.Status.ACTIVE
            or reservation.expires_at <= now
            for reservation in reservations
        )

        if has_invalid_reservation:
            _expire_locked_order(order)
            expired = True
        else:
            order.status = Order.Status.APPROVED

            order.save(
                update_fields=[
                    "status",
                    "updated_at",
                ]
            )

    if expired:
        raise ValidationError("O prazo da reserva expirou. O pedido foi expirado.")

    return order


@transaction.atomic
def reject_order(*, tenant, order_id):
    """Rejeita um pedido pendente e libera o estoque."""

    order = _get_locked_order(
        tenant=tenant,
        order_id=order_id,
    )

    if order.status != Order.Status.PENDING:
        raise ValidationError("Somente pedidos pendentes podem ser rejeitados.")

    order.status = Order.Status.REJECTED

    order.save(
        update_fields=[
            "status",
            "updated_at",
        ]
    )

    reservations = order.reservations.filter(
        status=StockReservation.Status.ACTIVE
    ).order_by("product_id", "id")

    for reservation in reservations:
        release_stock(reservation=reservation)

    return order


@transaction.atomic
def cancel_order(*, tenant, order_id):
    """Cancela um pedido ainda não concluído e libera o estoque."""

    order = _get_locked_order(
        tenant=tenant,
        order_id=order_id,
    )

    cancellable_statuses = [
        Order.Status.PENDING,
        Order.Status.APPROVED,
        Order.Status.PREPARING,
        Order.Status.READY,
    ]

    if order.status not in cancellable_statuses:
        raise ValidationError("Este pedido não pode mais ser cancelado.")

    order.status = Order.Status.CANCELLED

    order.save(
        update_fields=[
            "status",
            "updated_at",
        ]
    )

    reservations = order.reservations.filter(
        status=StockReservation.Status.ACTIVE
    ).order_by("product_id", "id")

    for reservation in reservations:
        release_stock(reservation=reservation)

    return order


@transaction.atomic
def complete_order(*, tenant, order_id):
    """Conclui um pedido pronto e efetua a baixa física do estoque."""

    order = _get_locked_order(
        tenant=tenant,
        order_id=order_id,
    )

    if order.status != Order.Status.READY:
        raise ValidationError("Somente pedidos prontos podem ser concluídos.")

    reservations = list(
        order.reservations.filter(status=StockReservation.Status.ACTIVE).order_by(
            "product_id", "id"
        )
    )

    if not reservations:
        raise ValidationError("O pedido não possui reservas ativas.")

    order.status = Order.Status.COMPLETED

    order.save(
        update_fields=[
            "status",
            "updated_at",
        ]
    )

    for reservation in reservations:
        consume_stock(reservation=reservation)

    return order


@transaction.atomic
def expire_order(*, tenant, order_id):
    """Expira manualmente um pedido pendente cujo prazo terminou."""

    order = _get_locked_order(
        tenant=tenant,
        order_id=order_id,
    )

    if order.status != Order.Status.PENDING:
        raise ValidationError("Somente pedidos pendentes podem expirar.")

    has_expired_reservation = order.reservations.filter(
        status=StockReservation.Status.ACTIVE,
        expires_at__lte=timezone.now(),
    ).exists()

    if not has_expired_reservation:
        raise ValidationError("O prazo de reserva deste pedido ainda não expirou.")

    return _expire_locked_order(order)


@transaction.atomic
def transition_order(*, tenant, order_id, expected_status, new_status):
    """Executa uma transição simples com bloqueio e validação do estado atual."""
    allowed = {
        (Order.Status.APPROVED, Order.Status.PREPARING),
        (Order.Status.PREPARING, Order.Status.READY),
    }
    if (expected_status, new_status) not in allowed:
        raise ValidationError("Transição de pedido não permitida.")

    order = _get_locked_order(tenant=tenant, order_id=order_id)
    if order.status != expected_status:
        raise ValidationError("O pedido foi atualizado por outra operação. Atualize a página.")

    order.status = new_status
    order.save(update_fields=["status", "updated_at"])
    return order
