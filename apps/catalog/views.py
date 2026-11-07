from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.db.models import Q, Count
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.catalog.forms import ProductForm, CategoryForm
from apps.catalog.models import Product, Category, ProductCodeSequence
from apps.core.tenancy import get_active_tenant
from apps.core.permissions import require_roles, OWNER, MANAGER
from apps.inventory.models import StockBalance, StockMovement
from apps.tenants.models import Tenant

# =========================================================
# GERAÇÃO DE CÓDIGO DO PRODUTO
# =========================================================


def _generate_product_code(*, tenant):
    """
    Gera um código PROD sequencial por empresa.

    A linha da empresa é bloqueada durante a operação para
    evitar duplicidade em cadastros simultâneos.

    Códigos existentes, inclusive os manuais, são ignorados.
    """

    locked_tenant = Tenant.objects.select_for_update().get(pk=tenant.pk)

    sequence, _ = ProductCodeSequence.objects.get_or_create(
        tenant=locked_tenant,
        defaults={"next_number": 1},
    )

    sequence = ProductCodeSequence.objects.select_for_update().get(pk=sequence.pk)

    while True:
        code = f"PROD-{sequence.next_number:06d}"
        sequence.next_number += 1

        code_exists = Product.objects.filter(
            tenant=locked_tenant,
            code__iexact=code,
        ).exists()

        if not code_exists:
            break

    sequence.save(
        update_fields=[
            "next_number",
            "updated_at",
        ]
    )

    return code


# =========================================================
# PRODUTOS
# =========================================================


def _get_product_stock_context(*, tenant, product):
    """Retorna os dados de estoque para a tela de edição."""

    balance = StockBalance.objects.filter(
        tenant=tenant,
        product=product,
    ).first()

    if not balance:
        return {
            "stock_balance": None,
            "physical_stock": Decimal("0.000"),
            "reserved_stock": Decimal("0.000"),
            "available_stock": Decimal("0.000"),
        }

    return {
        "stock_balance": balance,
        "physical_stock": balance.physical_quantity,
        "reserved_stock": balance.reserved_quantity,
        "available_stock": balance.available_quantity,
    }


def _adjust_product_stock(*, tenant, product, new_quantity, reason):
    """
    Ajusta o estoque físico para a quantidade informada.

    Registra a diferença como entrada ou saída.
    Impede estoque físico inferior ao estoque reservado.
    """

    try:
        new_quantity = Decimal(str(new_quantity))
    except (InvalidOperation, TypeError, ValueError):
        raise ValidationError("Informe uma quantidade de estoque válida.")

    if not new_quantity.is_finite() or new_quantity < 0:
        raise ValidationError("O estoque físico não pode ser negativo.")

    if new_quantity != new_quantity.quantize(Decimal("0.001")):
        raise ValidationError("O estoque deve ter no máximo três casas decimais.")

    reason = str(reason or "").strip()

    if not reason:
        raise ValidationError("Informe o motivo do ajuste de estoque.")

    if len(reason) > 255:
        raise ValidationError("O motivo do ajuste deve ter até 255 caracteres.")

    # O produto deve estar bloqueado antes do saldo,
    # seguindo a ordem de bloqueios do serviço de pedidos.
    locked_product = Product.objects.select_for_update().get(
        pk=product.pk,
        tenant=tenant,
    )

    balance = (
        StockBalance.objects.select_for_update()
        .filter(
            tenant=tenant,
            product=locked_product,
        )
        .first()
    )

    if not balance:
        balance = StockBalance.objects.create(
            tenant=tenant,
            product=locked_product,
            physical_quantity=Decimal("0.000"),
        )

    current_quantity = Decimal(str(balance.physical_quantity))
    reserved_quantity = Decimal(str(balance.reserved_quantity))

    if new_quantity < reserved_quantity:
        raise ValidationError(
            f"Não é possível definir esse estoque. "
            f"Existem {reserved_quantity:.3f} unidades reservadas."
        )

    difference = new_quantity - current_quantity

    # Não cria movimentação quando não existe alteração.
    if difference == Decimal("0.000"):
        return False

    if difference > 0:
        movement_kind = StockMovement.Kind.IN
        movement_quantity = difference
    else:
        movement_kind = StockMovement.Kind.OUT
        movement_quantity = abs(difference)

    balance.physical_quantity = new_quantity
    balance.save(
        update_fields=[
            "physical_quantity",
            "updated_at",
        ]
    )

    StockMovement.objects.create(
        tenant=tenant,
        product=locked_product,
        kind=movement_kind,
        quantity=movement_quantity,
        reference="AJUSTE_ESTOQUE",
        note=reason,
    )

    return True


@login_required
def product_list(request):
    tenant = get_active_tenant(request)

    products = (
        Product.objects.filter(tenant=tenant)
        .select_related("category", "stock_balance")
        .order_by("name")
    )

    search = request.GET.get("q", "").strip()
    status = request.GET.get("status", "all")

    if search:
        products = products.filter(
            Q(name__icontains=search)
            | Q(code__icontains=search)
            | Q(description__icontains=search)
        )

    if status == "active":
        products = products.filter(is_active=True)
    elif status == "inactive":
        products = products.filter(is_active=False)

    paginator = Paginator(products, 12)
    page_obj = paginator.get_page(request.GET.get("page"))

    product_rows = []

    for product in page_obj.object_list:
        try:
            balance = product.stock_balance
            physical = balance.physical_quantity
            reserved = balance.reserved_quantity
            available = balance.available_quantity
        except StockBalance.DoesNotExist:
            physical = Decimal("0.000")
            reserved = Decimal("0.000")
            available = Decimal("0.000")

        product_rows.append(
            {
                "product": product,
                "physical": physical,
                "reserved": reserved,
                "available": available,
            }
        )

    context = {
        "tenant": tenant,
        "page_obj": page_obj,
        "product_rows": product_rows,
        "search": search,
        "status": status,
        "total_products": Product.objects.filter(tenant=tenant).count(),
        "active_products": Product.objects.filter(
            tenant=tenant,
            is_active=True,
        ).count(),
        "inactive_products": Product.objects.filter(
            tenant=tenant,
            is_active=False,
        ).count(),
    }

    return render(
        request,
        "catalog/product_list.html",
        context,
    )


@login_required
@require_roles(OWNER, MANAGER)
def product_create(request):
    tenant = get_active_tenant(request)

    if request.method == "POST":
        form = ProductForm(
            request.POST,
            request.FILES,
            tenant=tenant,
        )

        if form.is_valid():
            try:
                with transaction.atomic():
                    product = form.save(commit=False)
                    product.tenant = tenant

                    # Código automático ou manual.
                    if form.cleaned_data["code_mode"] == "auto":
                        product.code = _generate_product_code(tenant=tenant)
                    else:
                        product.code = form.cleaned_data["manual_code"].upper()

                    product.save()

                    initial_stock = form.cleaned_data["initial_stock"]

                    StockBalance.objects.create(
                        tenant=tenant,
                        product=product,
                        physical_quantity=initial_stock,
                    )

                    if initial_stock > 0:
                        StockMovement.objects.create(
                            tenant=tenant,
                            product=product,
                            kind=StockMovement.Kind.IN,
                            quantity=initial_stock,
                            reference="ESTOQUE_INICIAL",
                            note=(
                                "Estoque inicial informado no " "cadastro do produto."
                            ),
                        )

                messages.success(
                    request,
                    f"Produto {product.code} cadastrado com sucesso!",
                )

                return redirect("catalog:product-list")

            except IntegrityError:
                form.add_error(
                    None,
                    "Não foi possível cadastrar o produto porque "
                    "o código já está em uso. Tente novamente.",
                )

    else:
        form = ProductForm(tenant=tenant)

    return render(
        request,
        "catalog/product_form.html",
        {
            "form": form,
            "tenant": tenant,
            "page_title": "Novo produto",
            "is_edit": False,
        },
    )


@login_required
@require_roles(OWNER, MANAGER)
def product_update(request, product_id):
    tenant = get_active_tenant(request)

    product = get_object_or_404(
        Product,
        pk=product_id,
        tenant=tenant,
    )

    if request.method == "POST":
        try:
            with transaction.atomic():
                # Bloqueia o produto antes de construir e validar o formulário.
                # Assim, a mesma instância recebe os dados e é salva.
                locked_product = Product.objects.select_for_update().get(
                    pk=product_id,
                    tenant=tenant,
                )

                form = ProductForm(
                    request.POST,
                    request.FILES,
                    instance=locked_product,
                    tenant=tenant,
                )

                # O estoque é tratado separadamente, por movimentação.
                form.fields.pop("initial_stock", None)

                if form.is_valid():
                    form.save()

                    stock_was_adjusted = False

                    # Só ajusta se o campo estiver presente no POST.
                    if "stock_quantity" in request.POST:
                        stock_was_adjusted = _adjust_product_stock(
                            tenant=tenant,
                            product=locked_product,
                            new_quantity=request.POST.get("stock_quantity"),
                            reason=request.POST.get(
                                "stock_adjustment_reason",
                                "",
                            ),
                        )

                else:
                    stock_context = _get_product_stock_context(
                        tenant=tenant,
                        product=locked_product,
                    )

                    return render(
                        request,
                        "catalog/product_form.html",
                        {
                            "form": form,
                            "tenant": tenant,
                            "product": locked_product,
                            "page_title": "Editar produto",
                            "is_edit": True,
                            **stock_context,
                        },
                    )

            if stock_was_adjusted:
                messages.success(
                    request,
                    "Produto atualizado e estoque ajustado com sucesso!",
                )
            else:
                messages.success(
                    request,
                    "Produto atualizado com sucesso!",
                )

            return redirect("catalog:product-list")

        except ValidationError as exc:
            if hasattr(exc, "messages"):
                errors = exc.messages
            else:
                errors = [str(exc)]

            for error in errors:
                form.add_error(None, error)

        except IntegrityError:
            form.add_error(
                None,
                "Não foi possível atualizar o produto. "
                "Verifique os dados e tente novamente.",
            )

    else:
        form = ProductForm(
            instance=product,
            tenant=tenant,
        )
        form.fields.pop("initial_stock", None)

    stock_context = _get_product_stock_context(
        tenant=tenant,
        product=product,
    )

    return render(
        request,
        "catalog/product_form.html",
        {
            "form": form,
            "tenant": tenant,
            "product": product,
            "page_title": "Editar produto",
            "is_edit": True,
            **stock_context,
        },
    )


@login_required
@require_roles(OWNER)
@require_POST
def product_toggle_status(request, product_id):
    tenant = get_active_tenant(request)

    with transaction.atomic():
        product = get_object_or_404(
            Product.objects.select_for_update(),
            pk=product_id,
            tenant=tenant,
        )

        product.is_active = not product.is_active
        product.save(update_fields=["is_active", "updated_at"])

    messages.success(
        request,
        (
            "Produto ativado com sucesso."
            if product.is_active
            else "Produto desativado com sucesso."
        ),
    )

    return redirect("catalog:product-list")


# =========================================================
# CATEGORIAS
# =========================================================


@login_required
def category_list(request):
    tenant = get_active_tenant(request)

    categories = (
        Category.objects.filter(tenant=tenant)
        .annotate(product_count=Count("products"))
        .order_by("name")
    )

    search = request.GET.get("q", "").strip()
    status = request.GET.get("status", "all")

    if search:
        categories = categories.filter(name__icontains=search)

    if status == "active":
        categories = categories.filter(is_active=True)
    elif status == "inactive":
        categories = categories.filter(is_active=False)

    paginator = Paginator(categories, 12)
    page_obj = paginator.get_page(request.GET.get("page"))

    context = {
        "tenant": tenant,
        "page_obj": page_obj,
        "search": search,
        "status": status,
        "total_categories": Category.objects.filter(tenant=tenant).count(),
        "active_categories": Category.objects.filter(
            tenant=tenant,
            is_active=True,
        ).count(),
        "inactive_categories": Category.objects.filter(
            tenant=tenant,
            is_active=False,
        ).count(),
    }

    return render(
        request,
        "catalog/category_list.html",
        context,
    )


@login_required
@require_roles(OWNER, MANAGER)
def category_create(request):
    tenant = get_active_tenant(request)

    if request.method == "POST":
        form = CategoryForm(
            request.POST,
            tenant=tenant,
        )

        if form.is_valid():
            form.save()

            messages.success(
                request,
                "Categoria cadastrada com sucesso!",
            )

            return redirect("catalog:category-list")

    else:
        form = CategoryForm(tenant=tenant)

    return render(
        request,
        "catalog/category_form.html",
        {
            "form": form,
            "tenant": tenant,
            "page_title": "Nova categoria",
            "is_edit": False,
        },
    )


@login_required
@require_roles(OWNER, MANAGER)
def category_update(request, category_id):
    tenant = get_active_tenant(request)

    category = get_object_or_404(
        Category,
        pk=category_id,
        tenant=tenant,
    )

    if request.method == "POST":
        form = CategoryForm(
            request.POST,
            instance=category,
            tenant=tenant,
        )

        if form.is_valid():
            form.save()

            messages.success(
                request,
                "Categoria atualizada com sucesso!",
            )

            return redirect("catalog:category-list")

    else:
        form = CategoryForm(
            instance=category,
            tenant=tenant,
        )

    return render(
        request,
        "catalog/category_form.html",
        {
            "form": form,
            "tenant": tenant,
            "category": category,
            "page_title": "Editar categoria",
            "is_edit": True,
        },
    )


@login_required
@require_roles(OWNER)
@require_POST
def category_toggle_status(request, category_id):
    tenant = get_active_tenant(request)

    with transaction.atomic():
        category = get_object_or_404(
            Category.objects.select_for_update(),
            pk=category_id,
            tenant=tenant,
        )

        category.is_active = not category.is_active
        category.save(update_fields=["is_active"])

    messages.success(
        request,
        (
            "Categoria ativada com sucesso."
            if category.is_active
            else "Categoria desativada com sucesso."
        ),
    )

    return redirect("catalog:category-list")
