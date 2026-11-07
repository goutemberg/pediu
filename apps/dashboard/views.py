from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q, Sum
from django.shortcuts import render
from django.utils import timezone
from django.urls import reverse

from apps.core.tenancy import get_active_tenant
from apps.catalog.models import Product
from apps.inventory.models import StockBalance
from apps.orders.models import Order


@login_required
def home(request):
    tenant = get_active_tenant(request)

    today = timezone.localdate()

    orders = Order.objects.filter(tenant=tenant)

    today_orders = orders.filter(created_at__date=today)

    completed_orders = orders.filter(status=Order.Status.COMPLETED)

    today_revenue = (
        today_orders.filter(status=Order.Status.COMPLETED).aggregate(
            total=Sum("total")
        )["total"]
        or 0
    )

    order_summary = orders.aggregate(
        pending=Count("id", filter=Q(status=Order.Status.PENDING)),
        approved=Count("id", filter=Q(status=Order.Status.APPROVED)),
        preparing=Count("id", filter=Q(status=Order.Status.PREPARING)),
        ready=Count("id", filter=Q(status=Order.Status.READY)),
        completed=Count("id", filter=Q(status=Order.Status.COMPLETED)),
    )

    products = Product.objects.filter(tenant=tenant)

    stock_balances = StockBalance.objects.filter(tenant=tenant).select_related(
        "product"
    )

    unavailable_products = []

    for balance in stock_balances:
        available = balance.available_quantity

        if available <= 0:
            unavailable_products.append(
                {
                    "product": balance.product,
                    "physical": balance.physical_quantity,
                    "reserved": balance.reserved_quantity,
                    "available": available,
                }
            )

    unavailable_products = unavailable_products[:6]

    recent_orders = orders.select_related("customer").order_by("-created_at")[:8]

    context = {
        "tenant": tenant,
        "storefront_url": request.build_absolute_uri(
            reverse("storefront:store", kwargs={"slug": tenant.slug})
        ),
        "today": today,
        "today_orders_count": today_orders.count(),
        "today_revenue": today_revenue,
        "total_products": products.count(),
        "active_products": products.filter(is_active=True).count(),
        "total_orders": orders.count(),
        "completed_orders": completed_orders.count(),
        "order_summary": order_summary,
        "recent_orders": recent_orders,
        "unavailable_products": unavailable_products,
    }

    return render(
        request,
        "dashboard/home.html",
        context,
    )
