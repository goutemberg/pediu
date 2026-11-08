import uuid
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.db.models import Sum, Q
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST
from django_ratelimit.decorators import ratelimit

from apps.catalog.models import Category, Product
from apps.core.tenancy import get_active_tenant
from apps.core.permissions import require_roles, OWNER, MANAGER, STAFF
from apps.inventory.models import StockBalance, StockReservation
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


def _storefront_return_key(tenant):
    return f"storefront_last_catalog_url_{tenant.pk}"


def _reserved_quantities(tenant, product_ids):
    """Calcula reservas ativas em uma consulta agrupada, sem N+1 por produto."""
    if not product_ids:
        return {}

    now = timezone.now()
    reserving_order_statuses = ["approved", "preparing", "ready", "completed"]
    reservations = (
        StockReservation.objects.filter(
            tenant=tenant,
            product_id__in=product_ids,
            status=StockReservation.Status.ACTIVE,
        )
        .filter(
            Q(order__status="pending", expires_at__gt=now)
            | Q(order__status__in=reserving_order_statuses)
        )
        .values("product_id")
        .annotate(total=Sum("quantity"))
    )
    return {row["product_id"]: row["total"] or Decimal("0.000") for row in reservations}


def _cart_quantity_count(request, tenant):
    """Soma as quantidades de todos os produtos no carrinho da loja."""
    cart = request.session.get(_cart_key(tenant), {})
    if not isinstance(cart, dict):
        return 0

    total = Decimal("0")
    for value in cart.values():
        try:
            quantity = Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError):
            continue

        if quantity.is_finite() and quantity > 0:
            total += quantity

    return int(total) if total == total.to_integral_value() else float(total)


def _wants_json(request):
    return request.headers.get(
        "x-requested-with"
    ) == "XMLHttpRequest" or "application/json" in request.headers.get("accept", "")


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

    result, total = [], Decimal("0.00")

    for product in products:
        try:
            quantity = Decimal(str(raw.get(str(product.pk), 0)))
        except (InvalidOperation, TypeError, ValueError):
            continue

        if not quantity.is_finite() or quantity <= 0:
            continue

        line_total = product.price * quantity

        result.append(
            {
                "product": product,
                "quantity": quantity,
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
    ).only("id", "name", "slug").order_by("name")

    query = request.GET.get("q", "").strip()[:100]
    category_slug = request.GET.get("categoria", "").strip()[:120]

    products = Product.objects.filter(
        tenant=tenant,
        is_active=True,
    ).select_related("category").only(
        "id", "tenant_id", "category_id", "code", "name", "price", "unit",
        "minimum_quantity", "quantity_multiple", "image",
        "category__id", "category__name", "category__slug",
    ).order_by("name", "pk")

    if query:
        products = products.filter(name__icontains=query)

    if category_slug:
        products = products.filter(category__slug=category_slug)

    paginator = Paginator(products, 24)
    try:
        page_obj = paginator.page(request.GET.get("pagina", 1))
    except (PageNotAnInteger, EmptyPage, ValueError, TypeError):
        page_obj = paginator.page(paginator.num_pages or 1)

    page_products = list(page_obj.object_list)
    product_ids = [product.pk for product in page_products]

    balances = {
        balance.product_id: balance.physical_quantity
        for balance in StockBalance.objects.filter(
            tenant=tenant,
            product_id__in=product_ids,
        ).only("product_id", "physical_quantity")
    }
    reserved = _reserved_quantities(tenant, product_ids)

    product_rows = [
        {
            "product": product,
            "available": (
                Decimal(str(balances.get(product.pk, 0)))
                - reserved.get(product.pk, Decimal("0.000"))
            ),
        }
        for product in page_products
    ]

    settings = tenant.settings if isinstance(tenant.settings, dict) else {}
    branding = (
        settings.get("storefront", {})
        if isinstance(settings.get("storefront", {}), dict)
        else {}
    )

    # Guarda a última URL de catálogo segura para o link "Continuar comprando".
    return_query = request.GET.copy()
    return_query.pop("pagina", None)
    return_url = request.path
    if return_query:
        return_url = f"{return_url}?{return_query.urlencode()}"
    request.session[_storefront_return_key(tenant)] = return_url

    context = {
        "tenant": tenant,
        "categories": categories,
        "product_rows": product_rows,
        "query": query,
        "selected_category": category_slug,
        "branding": branding,
        "cart_quantity_count": _cart_quantity_count(request, tenant),
        "page_obj": page_obj,
        "has_next": page_obj.has_next(),
        "next_page": page_obj.next_page_number() if page_obj.has_next() else None,
    }

    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        if request.headers.get("x-storefront-append") == "1":
            response = render(request, "storefront/_product_cards.html", context)
            response["X-Has-Next"] = "1" if page_obj.has_next() else "0"
            response["X-Next-Page"] = str(page_obj.next_page_number()) if page_obj.has_next() else ""
            return response
        return render(request, "storefront/_product_grid.html", context)

    return render(request, "storefront/store.html", context)


@require_POST
def cart_add(request, slug):
    tenant = _active_tenant(slug)

    product = get_object_or_404(
        Product,
        tenant=tenant,
        is_active=True,
        pk=request.POST.get("product_id"),
    )

    wants_json = _wants_json(request)

    try:
        quantity = Decimal(request.POST.get("quantity", "1"))
        if not quantity.is_finite() or quantity <= 0:
            raise InvalidOperation
    except (InvalidOperation, TypeError, ValueError):
        error = "Informe uma quantidade válida."
        if wants_json:
            return JsonResponse(
                {
                    "success": False,
                    "message": error,
                    "cart_quantity_count": _cart_quantity_count(request, tenant),
                },
                status=400,
            )
        messages.error(request, error)
        return redirect("storefront:store", slug=slug)

    cart = request.session.get(_cart_key(tenant), {})
    if not isinstance(cart, dict):
        cart = {}

    try:
        current = Decimal(str(cart.get(str(product.pk), "0")))
        if not current.is_finite() or current < 0:
            current = Decimal("0")
    except (InvalidOperation, TypeError, ValueError):
        current = Decimal("0")

    new_quantity = quantity + current
    minimum = Decimal(str(product.minimum_quantity))
    multiple = Decimal(str(product.quantity_multiple))

    if new_quantity < minimum or multiple <= 0 or new_quantity % multiple:
        error = (
            f"A quantidade deve respeitar o mínimo de {minimum} "
            f"e múltiplos de {multiple}."
        )
        if wants_json:
            return JsonResponse(
                {
                    "success": False,
                    "message": error,
                    "cart_quantity_count": _cart_quantity_count(request, tenant),
                },
                status=400,
            )
        messages.error(request, error)
    else:
        cart[str(product.pk)] = str(new_quantity)
        request.session[_cart_key(tenant)] = cart
        request.session.modified = True
        count = _cart_quantity_count(request, tenant)

        if wants_json:
            return JsonResponse(
                {
                    "success": True,
                    "message": "Produto adicionado ao carrinho!",
                    "cart_quantity_count": count,
                    "product_id": product.pk,
                    "product_quantity": str(new_quantity),
                }
            )

        messages.success(request, "Produto adicionado ao carrinho.")

    return redirect("storefront:store", slug=slug)


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

    fallback_url = reverse("storefront:store", kwargs={"slug": tenant.slug})
    saved_url = request.session.get(_storefront_return_key(tenant), fallback_url)
    if (
        not isinstance(saved_url, str)
        or not url_has_allowed_host_and_scheme(
            saved_url,
            allowed_hosts={request.get_host()},
        )
        or not saved_url.startswith(fallback_url)
    ):
        saved_url = fallback_url

    return render(
        request,
        "storefront/cart.html",
        {
            "tenant": tenant,
            "items": items,
            "total": total,
            "cart_quantity_count": _cart_quantity_count(request, tenant),
            "continue_shopping_url": saved_url,
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
            "cart_quantity_count": _cart_quantity_count(request, tenant),
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
            "cart_quantity_count": _cart_quantity_count(request, tenant),
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
