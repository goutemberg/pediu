from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.core.validators import validate_email
from django.db.models import Count, Max, Q
from django.shortcuts import get_object_or_404, redirect, render

from apps.core.permissions import OWNER, MANAGER, STAFF, require_roles
from apps.core.tenancy import get_active_tenant
from apps.orders.models import Order
from apps.tenants.models import Membership

from .models import Customer


def _customer_form_data(request):
    return {
        "name": request.POST.get("name", "").strip(),
        "phone": request.POST.get("phone", "").strip(),
        "email": request.POST.get("email", "").strip(),
        "notes": request.POST.get("notes", "").strip(),
    }


def _validate_customer_data(data):
    errors = []
    if not data["name"]:
        errors.append("Informe o nome do cliente.")
    elif len(data["name"]) > 160:
        errors.append("O nome deve ter até 160 caracteres.")

    if not data["phone"]:
        errors.append("Informe o telefone do cliente.")
    elif len(data["phone"]) > 30:
        errors.append("O telefone deve ter até 30 caracteres.")

    if len(data["email"]) > 254:
        errors.append("O e-mail deve ter até 254 caracteres.")
    elif data["email"]:
        try:
            validate_email(data["email"])
        except ValidationError:
            errors.append("Informe um endereço de e-mail válido.")

    return errors


def _can_manage_customers(user, tenant):
    return Membership.objects.filter(
        user=user,
        tenant=tenant,
        is_active=True,
        role__in=[OWNER, MANAGER],
    ).exists()


@login_required
@require_roles(OWNER, MANAGER, STAFF)
def customer_list(request):
    tenant = get_active_tenant(request)
    search = request.GET.get("q", "").strip()

    customers = Customer.objects.filter(tenant=tenant).annotate(
        orders_count=Count("orders", distinct=True),
        last_order_at=Max("orders__created_at"),
    )

    if search:
        customers = customers.filter(
            Q(name__icontains=search)
            | Q(phone__icontains=search)
            | Q(email__icontains=search)
        )

    customers = customers.order_by("name", "id")
    paginator = Paginator(customers, 15)
    page_obj = paginator.get_page(request.GET.get("page"))

    return render(request, "customers/customer_list.html", {
        "tenant": tenant,
        "customers": page_obj.object_list,
        "page_obj": page_obj,
        "search": search,
        "can_manage": _can_manage_customers(request.user, tenant),
        "total_customers": customers.count(),
    })


@login_required
@require_roles(OWNER, MANAGER)
def customer_create(request):
    tenant = get_active_tenant(request)
    data = {"name": "", "phone": "", "email": "", "notes": ""}

    if request.method == "POST":
        data = _customer_form_data(request)
        errors = _validate_customer_data(data)
        if not errors and Customer.objects.filter(
            tenant=tenant, phone=data["phone"]
        ).exists():
            errors.append("Já existe um cliente cadastrado com este telefone.")

        if errors:
            for error in errors:
                messages.error(request, error)
        else:
            customer = Customer.objects.create(tenant=tenant, **data)
            messages.success(request, "Cliente cadastrado com sucesso.")
            return redirect("customers:customer-detail", customer_id=customer.pk)

    return render(request, "customers/customer_form.html", {
        "tenant": tenant,
        "customer": None,
        "form_data": data,
        "page_title": "Novo cliente",
        "breadcrumb_title": "Novo cliente",
    })


@login_required
@require_roles(OWNER, MANAGER)
def customer_update(request, customer_id):
    tenant = get_active_tenant(request)
    customer = get_object_or_404(Customer, pk=customer_id, tenant=tenant)
    data = {
        "name": customer.name,
        "phone": customer.phone,
        "email": customer.email,
        "notes": customer.notes,
    }

    if request.method == "POST":
        data = _customer_form_data(request)
        errors = _validate_customer_data(data)
        duplicate = Customer.objects.filter(
            tenant=tenant, phone=data["phone"]
        ).exclude(pk=customer.pk).exists()
        if not errors and duplicate:
            errors.append("Já existe outro cliente cadastrado com este telefone.")

        if errors:
            for error in errors:
                messages.error(request, error)
        else:
            for field, value in data.items():
                setattr(customer, field, value)
            customer.save(update_fields=["name", "phone", "email", "notes"])
            messages.success(request, "Dados do cliente atualizados.")
            return redirect("customers:customer-detail", customer_id=customer.pk)

    return render(request, "customers/customer_form.html", {
        "tenant": tenant,
        "customer": customer,
        "form_data": data,
        "page_title": "Editar cliente",
        "breadcrumb_title": "Editar cliente",
    })


@login_required
@require_roles(OWNER, MANAGER, STAFF)
def customer_detail(request, customer_id):
    tenant = get_active_tenant(request)
    customer = get_object_or_404(Customer, pk=customer_id, tenant=tenant)
    orders = Order.objects.filter(
        tenant=tenant, customer=customer
    ).order_by("-created_at", "-id")

    paginator = Paginator(orders, 10)
    page_obj = paginator.get_page(request.GET.get("page"))

    return render(request, "customers/customer_detail.html", {
        "tenant": tenant,
        "customer": customer,
        "orders": page_obj.object_list,
        "page_obj": page_obj,
        "can_manage": _can_manage_customers(request.user, tenant),
        "orders_count": orders.count(),
    })
