import uuid
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from django_ratelimit.decorators import ratelimit

from apps.catalog.models import Category, Product
from apps.core.tenancy import get_active_tenant
from apps.core.permissions import require_roles, OWNER, MANAGER, STAFF
from apps.inventory.models import StockBalance
from apps.orders.models import Order
from apps.orders.services import (
    create_order,
    approve_order,
    reject_order,
    cancel_order,
    complete_order,
    transition_order,
)
from apps.tenants.models import Tenant


def _active_tenant(slug):
    tenant = get_object_or_404(Tenant, slug=slug)
    if tenant.status == Tenant.Status.SUSPENDED:
        raise Http404("Loja não encontrada.")
    return tenant


def _cart_key(tenant):
    return f"storefront_cart_{tenant.pk}"


def _reservation_expiration(order):
    """
    Retorna a data/hora de vencimento da reserva do pedido.
    Utilizada pelo contador regressivo nas telas do cliente e do lojista.
    """
    return (
        order.reservations.order_by("expires_at")
        .values_list("expires_at", flat=True)
        .first()
    )


def _cart_items(request, tenant):
    raw = request.session.get(_cart_key(tenant), {})
    if not isinstance(raw, dict):
        raw = {}

    ids = []
    for key in raw:
        try:
            ids.append(int(key))
        except (TypeError, ValueError):
            continue

    products = Product.objects.filter(
        tenant=tenant,
        is_active=True,
        pk__in=ids,
    ).select_related("category")

    balances = {
        b.product_id: b
        for b in StockBalance.objects.filter(
            tenant=tenant,
            product__in=products,
        )
    }

    result, total = [], Decimal("0.00")

    for product in products:
        try:
            quantity = Decimal(str(raw.get(str(product.pk), 0)))
        except (InvalidOperation, TypeError, ValueError):
            continue

        if not quantity.is_finite() or quantity <= 0:
            continue

        balance = balances.get(product.pk)
        available = balance.available_quantity if balance else Decimal("0")
        line_total = product.price * quantity

        result.append(
            {
                "product": product,
                "quantity": quantity,
                "available": available,
                "line_total": line_total,
            }
        )
        total += line_total

    return result, total


def store(request, slug):
    tenant = _active_tenant(slug)

    categories = Category.objects.filter(
        tenant=tenant,
        is_active=True,
    ).order_by("name")

    products = (
        Product.objects.filter(
            tenant=tenant,
            is_active=True,
        )
        .select_related("category")
        .order_by("name")
    )

    query = request.GET.get("q", "").strip()
    category_slug = request.GET.get("categoria", "").strip()

    if query:
        products = products.filter(name__icontains=query)

    if category_slug:
        products = products.filter(category__slug=category_slug)

    balances = {
        b.product_id: b
        for b in StockBalance.objects.filter(
            tenant=tenant,
            product__in=products,
        )
    }

    product_rows = [
        {
            "product": p,
            "available": (
                balances[p.pk].available_quantity if p.pk in balances else Decimal("0")
            ),
        }
        for p in products
    ]

    settings = tenant.settings if isinstance(tenant.settings, dict) else {}
    branding = (
        settings.get("storefront", {})
        if isinstance(settings.get("storefront", {}), dict)
        else {}
    )

    return render(
        request,
        "storefront/store.html",
        {
            "tenant": tenant,
            "categories": categories,
            "product_rows": product_rows,
            "query": query,
            "selected_category": category_slug,
            "branding": branding,
        },
    )


@require_POST
def cart_add(request, slug):
    tenant = _active_tenant(slug)

    product = get_object_or_404(
        Product,
        tenant=tenant,
        is_active=True,
        pk=request.POST.get("product_id"),
    )

    try:
        quantity = Decimal(request.POST.get("quantity", "1"))

        if not quantity.is_finite() or quantity <= 0:
            raise InvalidOperation

    except (InvalidOperation, TypeError, ValueError):
        messages.error(request, "Informe uma quantidade válida.")
        return redirect("storefront:store", slug=slug)

    cart = request.session.get(_cart_key(tenant), {})
    current = Decimal(str(cart.get(str(product.pk), "0")))
    quantity += current

    minimum = Decimal(str(product.minimum_quantity))
    multiple = Decimal(str(product.quantity_multiple))

    if quantity < minimum or quantity % multiple:
        messages.error(
            request,
            f"A quantidade deve respeitar o mínimo de {minimum} "
            f"e múltiplos de {multiple}.",
        )
    else:
        cart[str(product.pk)] = str(quantity)
        request.session[_cart_key(tenant)] = cart
        request.session.modified = True
        messages.success(request, "Produto adicionado ao carrinho.")

    return redirect("storefront:cart", slug=slug)


@require_POST
def cart_remove(request, slug):
    tenant = _active_tenant(slug)

    cart = request.session.get(_cart_key(tenant), {})
    cart.pop(str(request.POST.get("product_id")), None)

    request.session[_cart_key(tenant)] = cart
    request.session.modified = True

    return redirect("storefront:cart", slug=slug)


@require_POST
def cart_update(request, slug):
    tenant = _active_tenant(slug)

    cart = request.session.get(_cart_key(tenant), {})
    product_id = str(request.POST.get("product_id", ""))

    product = get_object_or_404(
        Product,
        tenant=tenant,
        is_active=True,
        pk=product_id,
    )

    try:
        quantity = Decimal(request.POST.get("quantity", "0"))

        if not quantity.is_finite() or quantity <= 0:
            raise InvalidOperation

        minimum = Decimal(str(product.minimum_quantity))
        multiple = Decimal(str(product.quantity_multiple))

        if quantity < minimum or quantity % multiple:
            raise ValidationError(
                f"A quantidade deve respeitar o mínimo de {minimum} "
                f"e múltiplos de {multiple}."
            )

    except (InvalidOperation, TypeError, ValueError):
        messages.error(request, "Informe uma quantidade válida.")

    except ValidationError as exc:
        for error in exc.messages:
            messages.error(request, error)

    else:
        cart[product_id] = str(quantity)
        request.session[_cart_key(tenant)] = cart
        request.session.modified = True

    return redirect("storefront:cart", slug=slug)


def cart(request, slug):
    tenant = _active_tenant(slug)
    items, total = _cart_items(request, tenant)

    return render(
        request,
        "storefront/cart.html",
        {
            "tenant": tenant,
            "items": items,
            "total": total,
        },
    )


@ratelimit(key="ip", rate="15/m", method="POST", block=True)
def checkout(request, slug):
    tenant = _active_tenant(slug)
    items, total = _cart_items(request, tenant)

    if not items:
        messages.info(request, "Seu carrinho está vazio.")
        return redirect("storefront:store", slug=slug)

    if request.method == "POST":
        fulfillment = request.POST.get("fulfillment_method", "pickup")
        address = request.POST.get("delivery_address", "").strip()
        if fulfillment not in Order.Fulfillment.values:
            messages.error(request, "Selecione uma modalidade de recebimento válida.")
            return redirect("storefront:checkout", slug=slug)
        if fulfillment == Order.Fulfillment.DELIVERY and not address:
            messages.error(request, "Informe o endereço para entrega.")
            return redirect("storefront:checkout", slug=slug)
        if len(address) > 1000:
            messages.error(request, "O endereço deve ter até 1.000 caracteres.")
            return redirect("storefront:checkout", slug=slug)

        customer_data = {
            "name": request.POST.get("name", "").strip(),
            "phone": request.POST.get("phone", "").strip(),
            "notes": request.POST.get("notes", "").strip(),
        }

        order_items = [
            {
                "product_id": row["product"].pk,
                "quantity": str(row["quantity"]),
            }
            for row in items
        ]

        key_name = f"storefront_idempotency_{tenant.pk}"
        idempotency = request.session.get(key_name)

        if not idempotency:
            idempotency = str(uuid.uuid4())
            request.session[key_name] = idempotency

        try:
            order = create_order(
                tenant=tenant,
                customer_data=customer_data,
                items=order_items,
                idempotency_key=idempotency,
                fulfillment_method=fulfillment,
                delivery_address=address,
            )

        except ValidationError as exc:
            for error in exc.messages:
                messages.error(request, error)

        else:
            request.session[_cart_key(tenant)] = {}
            request.session.pop(key_name, None)
            request.session.modified = True

            return redirect(
                "storefront:order-confirmation",
                slug=slug,
                public_id=order.public_id,
            )

    return render(
        request,
        "storefront/checkout.html",
        {
            "tenant": tenant,
            "items": items,
            "total": total,
        },
    )


def order_confirmation(request, slug, public_id):
    tenant = _active_tenant(slug)

    order = get_object_or_404(
        Order.objects.prefetch_related("items"),
        tenant=tenant,
        public_id=public_id,
    )

    return render(
        request,
        "storefront/order_confirmation.html",
        {
            "tenant": tenant,
            "order": order,
            "reservation_expires_at": _reservation_expiration(order),
        },
    )


def order_status(request, slug, public_id):
    """
    Retorna o status atualizado do pedido para acompanhamento
    automático pelo cliente, sem recarregar a página.
    """
    tenant = _active_tenant(slug)

    order = get_object_or_404(
        Order,
        tenant=tenant,
        public_id=public_id,
    )

    expiration = _reservation_expiration(order)

    return JsonResponse(
        {
            "status": order.status,
            "status_display": order.get_status_display(),
            "updated_at": order.updated_at.isoformat(),
            "reservation_expires_at": (expiration.isoformat() if expiration else None),
        }
    )


def order_tracking(request, slug, public_id):
    return order_confirmation(request, slug, public_id)


@login_required
@require_roles(OWNER, MANAGER, STAFF)
def merchant_orders(request):
    tenant = get_active_tenant(request)

    orders = (
        Order.objects.filter(tenant=tenant)
        .prefetch_related("items")
        .order_by("-created_at")
    )

    status = request.GET.get("status", "")

    if status in Order.Status.values:
        orders = orders.filter(status=status)

    return render(
        request,
        "storefront/merchant_orders.html",
        {
            "tenant": tenant,
            "orders": orders,
            "statuses": Order.Status.choices,
            "selected_status": status,
        },
    )


@login_required
@require_roles(OWNER, MANAGER, STAFF)
def merchant_order_detail(request, order_id):
    tenant = get_active_tenant(request)

    order = get_object_or_404(
        Order.objects.prefetch_related("items"),
        tenant=tenant,
        pk=order_id,
    )

    if request.method == "POST":
        action = request.POST.get("action")

        try:
            if action == "approve":
                approve_order(tenant=tenant, order_id=order.pk)

            elif action == "reject":
                reject_order(tenant=tenant, order_id=order.pk)

            elif action == "cancel":
                cancel_order(tenant=tenant, order_id=order.pk)

            elif action == "preparing":
                transition_order(
                    tenant=tenant,
                    order_id=order.pk,
                    expected_status=Order.Status.APPROVED,
                    new_status=Order.Status.PREPARING,
                )

            elif action == "ready":
                transition_order(
                    tenant=tenant,
                    order_id=order.pk,
                    expected_status=Order.Status.PREPARING,
                    new_status=Order.Status.READY,
                )

            elif action == "complete":
                complete_order(tenant=tenant, order_id=order.pk)

            else:
                raise ValidationError("Ação inválida para o status atual do pedido.")

        except ValidationError as exc:
            for error in exc.messages:
                messages.error(request, error)

        else:
            messages.success(request, "Pedido atualizado.")

        return redirect(
            "storefront:merchant-order-detail",
            order_id=order.pk,
        )

    return render(
        request,
        "storefront/merchant_order_detail.html",
        {
            "tenant": tenant,
            "order": order,
            "reservation_expires_at": _reservation_expiration(order),
        },
    )
