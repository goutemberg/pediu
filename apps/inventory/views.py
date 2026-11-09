from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.catalog.models import Product
from apps.core.permissions import OWNER, MANAGER, STAFF, require_roles
from apps.core.tenancy import get_active_tenant
from apps.orders.models import Order
from apps.tenants.models import Membership

from .models import StockBalance, StockMovement, StockReservation
from .stock_settings import get_minimum_stock, set_minimum_stock


def _stock_rows(tenant, products):
    """Monta saldos em lote para evitar consultas repetidas por produto."""
    balances = {
        item.product_id: item
        for item in StockBalance.objects.filter(
            tenant=tenant,
            product__in=products,
        )
    }

    now = timezone.now()
    reserving = (
        StockReservation.objects.filter(
            tenant=tenant,
            status=StockReservation.Status.ACTIVE,
        )
        .filter(
            Q(order__status=Order.Status.PENDING, expires_at__gt=now)
            | Q(order__status__in=[
                Order.Status.APPROVED,
                Order.Status.PREPARING,
                Order.Status.READY,
                Order.Status.COMPLETED,
            ])
        )
        .values("product_id")
        .annotate(total=Sum("quantity"))
    )
    reserved_by_product = {
        row["product_id"]: row["total"] or Decimal("0.000")
        for row in reserving
    }

    rows = []
    minimum = get_minimum_stock(tenant)
    for product in products:
        balance = balances.get(product.pk)
        physical = balance.physical_quantity if balance else Decimal("0.000")
        reserved = reserved_by_product.get(product.pk, Decimal("0.000"))
        available = physical - reserved
        if available <= 0:
            status = "out"
            status_label = "Sem estoque"
        elif available <= minimum:
            status = "low"
            status_label = "Estoque baixo"
        else:
            status = "ok"
            status_label = "Normal"
        rows.append({
            "product": product,
            "physical": physical,
            "reserved": reserved,
            "available": available,
            "status": status,
            "status_label": status_label,
        })
    return rows


@login_required
@require_roles(OWNER, MANAGER, STAFF)
def stock_list(request):
    tenant = get_active_tenant(request)
    search = request.GET.get("q", "").strip()
    status_filter = request.GET.get("status", "all")

    products = Product.objects.filter(tenant=tenant).select_related("category").order_by("name")
    if search:
        products = products.filter(
            Q(name__icontains=search)
            | Q(code__icontains=search)
            | Q(category__name__icontains=search)
        )

    # O cálculo de saldos é feito em lote para que a paginação não gere N+1 queries.
    all_rows = _stock_rows(tenant, list(products))
    if status_filter == "low":
        all_rows = [row for row in all_rows if row["status"] == "low"]
    elif status_filter == "out":
        all_rows = [row for row in all_rows if row["status"] == "out"]
    elif status_filter == "ok":
        all_rows = [row for row in all_rows if row["status"] == "ok"]

    # Mantém o mesmo padrão de paginação do catálogo (12 itens por página).
    # O filtro é aplicado antes da paginação, para paginar somente os resultados.
    paginator = Paginator(all_rows, 12)
    page_obj = paginator.get_page(request.GET.get("page"))
    rows = page_obj.object_list

    totals = {
        "products": len(all_rows),
        "physical": sum((row["physical"] for row in all_rows), Decimal("0.000")),
        "reserved": sum((row["reserved"] for row in all_rows), Decimal("0.000")),
        "available": sum((row["available"] for row in all_rows), Decimal("0.000")),
        "low": sum(1 for row in all_rows if row["status"] == "low"),
        "out": sum(1 for row in all_rows if row["status"] == "out"),
    }

    can_manage = Membership.objects.filter(
        user=request.user,
        tenant=tenant,
        is_active=True,
        role__in=[OWNER, MANAGER],
    ).exists()

    return render(request, "inventory/stock_list.html", {
        "tenant": tenant,
        "can_manage": can_manage,
        "rows": rows,
        "page_obj": page_obj,
        "search": search,
        "status_filter": status_filter,
        "minimum_stock": get_minimum_stock(tenant),
        "totals": totals,
        "tenant_product_count": Product.objects.filter(tenant=tenant).count(),
    })


@login_required
@require_roles(OWNER, MANAGER)
def stock_settings(request):
    tenant = get_active_tenant(request)
    if request.method == "POST":
        try:
            value = set_minimum_stock(tenant, request.POST.get("minimum_stock", ""))
            messages.success(request, f"Estoque mínimo padrão atualizado para {value:.3f}.")
            return redirect("inventory:stock-settings")
        except ValueError as exc:
            messages.error(request, str(exc))

    return render(request, "inventory/stock_settings.html", {
        "tenant": tenant,
        "minimum_stock": get_minimum_stock(tenant),
    })


@login_required
@require_roles(OWNER, MANAGER)
def stock_adjust(request, product_id):
    tenant = get_active_tenant(request)
    product = get_object_or_404(Product, pk=product_id, tenant=tenant)

    balance = StockBalance.objects.filter(tenant=tenant, product=product).first()
    physical = balance.physical_quantity if balance else Decimal("0.000")
    reserved = balance.reserved_quantity if balance else Decimal("0.000")
    available = physical - reserved

    if request.method == "POST":
        action = request.POST.get("action", "")
        reason = request.POST.get("reason", "").strip()
        raw_quantity = request.POST.get("quantity", "").strip()
        try:
            quantity = Decimal(raw_quantity.replace(",", "."))
            if not quantity.is_finite() or quantity <= 0:
                raise ValueError
            if quantity != quantity.quantize(Decimal("0.001")):
                raise ValueError
            if not reason:
                raise ValidationError("Informe o motivo da movimentação.")
            if len(reason) > 255:
                raise ValidationError("O motivo deve ter até 255 caracteres.")
            if action not in ("in", "out", "adjustment"):
                raise ValidationError("Tipo de movimentação inválido.")

            with transaction.atomic():
                locked_product = Product.objects.select_for_update().get(
                    pk=product.pk, tenant=tenant
                )
                locked_balance, _ = StockBalance.objects.select_for_update().get_or_create(
                    tenant=tenant,
                    product=locked_product,
                    defaults={"physical_quantity": Decimal("0.000")},
                )
                current = locked_balance.physical_quantity
                current_reserved = locked_balance.reserved_quantity

                if action == "in":
                    new_value = current + quantity
                    movement_kind = StockMovement.Kind.IN
                    movement_quantity = quantity
                elif action == "out":
                    if quantity > current - current_reserved:
                        raise ValidationError(
                            "A saída não pode ser maior que o estoque disponível "
                            f"({current - current_reserved:.3f})."
                        )
                    new_value = current - quantity
                    movement_kind = StockMovement.Kind.OUT
                    movement_quantity = quantity
                else:
                    new_value = quantity
                    if new_value < current_reserved:
                        raise ValidationError(
                            "O saldo ajustado não pode ficar abaixo da quantidade reservada "
                            f"({current_reserved:.3f})."
                        )
                    difference = new_value - current
                    if difference == 0:
                        messages.info(request, "O saldo informado já é o saldo atual.")
                        return redirect("inventory:stock-list")
                    movement_kind = StockMovement.Kind.ADJUSTMENT
                    movement_quantity = abs(difference)

                locked_balance.physical_quantity = new_value
                locked_balance.save(update_fields=["physical_quantity", "updated_at"])
                StockMovement.objects.create(
                    tenant=tenant,
                    product=locked_product,
                    kind=movement_kind,
                    quantity=movement_quantity,
                    reference="GESTAO_ESTOQUE",
                    note=reason,
                )

            messages.success(request, "Movimentação de estoque registrada com sucesso.")
            return redirect("inventory:stock-list")
        except (InvalidOperation, TypeError, ValueError):
            messages.error(request, "Informe uma quantidade válida, maior que zero, com até três casas decimais.")
        except ValidationError as exc:
            for error in exc.messages:
                messages.error(request, error)

    return render(request, "inventory/stock_adjust.html", {
        "tenant": tenant,
        "product": product,
        "physical": physical,
        "reserved": reserved,
        "available": available,
    })


@login_required
@require_roles(OWNER, MANAGER, STAFF)
def stock_movements(request, product_id=None):
    tenant = get_active_tenant(request)
    movements = StockMovement.objects.filter(tenant=tenant).select_related("product").order_by("-created_at", "-id")
    product = None
    if product_id is not None:
        product = get_object_or_404(Product, pk=product_id, tenant=tenant)
        movements = movements.filter(product=product)

    kind = request.GET.get("kind", "")
    if kind in StockMovement.Kind.values:
        movements = movements.filter(kind=kind)

    paginator = Paginator(movements, 30)
    page_obj = paginator.get_page(request.GET.get("page"))
    return render(request, "inventory/stock_movements.html", {
        "tenant": tenant,
        "product": product,
        "page_obj": page_obj,
        "movements": page_obj.object_list,
        "kind": kind,
        "movement_kinds": StockMovement.Kind.choices,
    })
