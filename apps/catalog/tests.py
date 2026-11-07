from decimal import Decimal

import pytest

from django.db import IntegrityError, transaction

from apps.catalog.forms import ProductForm
from apps.catalog.models import Category, Product, ProductCodeSequence
from apps.catalog.views import (
    _adjust_product_stock,
    _generate_product_code,
)
from apps.inventory.models import StockBalance, StockMovement

# =========================================================
# HELPERS
# =========================================================


@pytest.fixture
def category(tenant):
    return Category.objects.create(
        tenant=tenant,
        name="Alimentos",
        slug="alimentos",
    )


def product_form_data(*, category, **overrides):
    data = {
        "code_mode": "auto",
        "manual_code": "",
        "name": "Novo Produto",
        "category": str(category.pk),
        "description": "Produto para testes",
        "price": "15.90",
        "unit": "UN",
        "minimum_quantity": "1.000",
        "quantity_multiple": "1.000",
        "initial_stock": "0.000",
        "is_active": "on",
    }
    data.update(overrides)
    return data


# =========================================================
# TESTES DOS MODELOS
# =========================================================


@pytest.mark.django_db
@pytest.mark.unit
def test_product_quantity_defaults(product):
    assert product.minimum_quantity == 1
    assert product.quantity_multiple == 1
    assert str(product.price) == "12.50"


@pytest.mark.django_db
@pytest.mark.unit
def test_product_code_unique_inside_tenant(product, tenant):
    with pytest.raises(IntegrityError), transaction.atomic():
        Product.objects.create(
            tenant=tenant,
            code=product.code,
            name="Duplicado",
            price="5.00",
        )


@pytest.mark.django_db
@pytest.mark.unit
def test_same_product_code_allowed_in_other_tenant(
    product,
    another_tenant,
):
    other = Product.objects.create(
        tenant=another_tenant,
        code=product.code,
        name="Outro",
        price="8.00",
    )

    assert other.tenant_id != product.tenant_id


# =========================================================
# TESTES DA SEQUÊNCIA AUTOMÁTICA
# =========================================================


@pytest.mark.django_db
@pytest.mark.unit
def test_generate_first_product_code(tenant):
    with transaction.atomic():
        code = _generate_product_code(tenant=tenant)

    assert code == "PROD-000001"


@pytest.mark.django_db
@pytest.mark.unit
def test_generate_sequential_product_codes(tenant):
    with transaction.atomic():
        first_code = _generate_product_code(tenant=tenant)

    with transaction.atomic():
        second_code = _generate_product_code(tenant=tenant)

    with transaction.atomic():
        third_code = _generate_product_code(tenant=tenant)

    assert first_code == "PROD-000001"
    assert second_code == "PROD-000002"
    assert third_code == "PROD-000003"


@pytest.mark.django_db
@pytest.mark.unit
def test_product_sequence_is_independent_per_tenant(
    tenant,
    another_tenant,
):
    with transaction.atomic():
        first_tenant_code = _generate_product_code(tenant=tenant)

    with transaction.atomic():
        second_tenant_code = _generate_product_code(tenant=another_tenant)

    assert first_tenant_code == "PROD-000001"
    assert second_tenant_code == "PROD-000001"


@pytest.mark.django_db
@pytest.mark.unit
def test_automatic_code_skips_existing_manual_code(tenant):
    Product.objects.create(
        tenant=tenant,
        code="PROD-000001",
        name="Produto com código manual",
        price="10.00",
    )

    with transaction.atomic():
        generated_code = _generate_product_code(tenant=tenant)

    assert generated_code == "PROD-000002"


@pytest.mark.django_db
@pytest.mark.unit
def test_product_sequence_is_created_for_tenant(tenant):
    assert not ProductCodeSequence.objects.filter(tenant=tenant).exists()

    with transaction.atomic():
        _generate_product_code(tenant=tenant)

    sequence = ProductCodeSequence.objects.get(tenant=tenant)

    assert sequence.next_number == 2


# =========================================================
# TESTES DO FORMULÁRIO DE PRODUTO
# =========================================================


@pytest.mark.django_db
@pytest.mark.unit
def test_product_form_accepts_automatic_code(
    tenant,
    category,
):
    form = ProductForm(
        data=product_form_data(category=category),
        tenant=tenant,
    )

    assert form.is_valid(), form.errors
    assert form.cleaned_data["code_mode"] == "auto"


@pytest.mark.django_db
@pytest.mark.unit
def test_product_form_accepts_manual_code(
    tenant,
    category,
):
    form = ProductForm(
        data=product_form_data(
            category=category,
            code_mode="manual",
            manual_code="meu-produto-01",
        ),
        tenant=tenant,
    )

    assert form.is_valid(), form.errors

    product = form.save(commit=False)

    assert product.code == "MEU-PRODUTO-01"


@pytest.mark.django_db
@pytest.mark.unit
def test_product_form_rejects_duplicate_manual_code(
    tenant,
    category,
    product,
):
    form = ProductForm(
        data=product_form_data(
            category=category,
            code_mode="manual",
            manual_code=product.code,
        ),
        tenant=tenant,
    )

    assert not form.is_valid()
    assert "manual_code" in form.errors


@pytest.mark.django_db
@pytest.mark.unit
def test_product_form_requires_manual_code(
    tenant,
    category,
):
    form = ProductForm(
        data=product_form_data(
            category=category,
            code_mode="manual",
            manual_code="",
        ),
        tenant=tenant,
    )

    assert not form.is_valid()
    assert "manual_code" in form.errors


@pytest.mark.django_db
@pytest.mark.unit
def test_product_form_rejects_category_from_another_tenant(
    tenant,
    another_tenant,
):
    other_category = Category.objects.create(
        tenant=another_tenant,
        name="Categoria externa",
        slug="categoria-externa",
    )

    form = ProductForm(
        data=product_form_data(
            category=other_category,
        ),
        tenant=tenant,
    )

    assert not form.is_valid()
    assert "category" in form.errors


# =========================================================
# TESTES DE AJUSTE DE ESTOQUE
# =========================================================


@pytest.mark.django_db
@pytest.mark.integration
def test_stock_adjustment_registers_entry(product, tenant):
    with transaction.atomic():
        adjusted = _adjust_product_stock(
            tenant=tenant,
            product=product,
            new_quantity="15.000",
            reason="Reposição de mercadoria",
        )

    balance = StockBalance.objects.get(
        tenant=tenant,
        product=product,
    )

    movement = StockMovement.objects.get(
        tenant=tenant,
        product=product,
        reference="AJUSTE_ESTOQUE",
    )

    assert adjusted is True
    assert balance.physical_quantity == Decimal("15.000")
    assert movement.kind == StockMovement.Kind.IN
    assert movement.quantity == Decimal("5.000")


@pytest.mark.django_db
@pytest.mark.integration
def test_stock_adjustment_registers_exit(product, tenant):
    with transaction.atomic():
        adjusted = _adjust_product_stock(
            tenant=tenant,
            product=product,
            new_quantity="7.000",
            reason="Correção após inventário",
        )

    balance = StockBalance.objects.get(
        tenant=tenant,
        product=product,
    )

    movement = StockMovement.objects.get(
        tenant=tenant,
        product=product,
        reference="AJUSTE_ESTOQUE",
    )

    assert adjusted is True
    assert balance.physical_quantity == Decimal("7.000")
    assert movement.kind == StockMovement.Kind.OUT
    assert movement.quantity == Decimal("3.000")


@pytest.mark.django_db
@pytest.mark.integration
def test_stock_adjustment_does_not_create_movement_without_change(
    product,
    tenant,
):
    with transaction.atomic():
        adjusted = _adjust_product_stock(
            tenant=tenant,
            product=product,
            new_quantity="10.000",
            reason="Conferência de estoque",
        )

    assert adjusted is False

    assert not StockMovement.objects.filter(
        tenant=tenant,
        product=product,
        reference="AJUSTE_ESTOQUE",
    ).exists()


@pytest.mark.django_db
@pytest.mark.integration
def test_stock_adjustment_rejects_negative_quantity(
    product,
    tenant,
):
    with pytest.raises(Exception, match="não pode ser negativo"):
        with transaction.atomic():
            _adjust_product_stock(
                tenant=tenant,
                product=product,
                new_quantity="-1.000",
                reason="Teste de estoque",
            )


@pytest.mark.django_db
@pytest.mark.integration
def test_stock_adjustment_requires_reason(product, tenant):
    with pytest.raises(Exception, match="motivo do ajuste"):
        with transaction.atomic():
            _adjust_product_stock(
                tenant=tenant,
                product=product,
                new_quantity="12.000",
                reason="",
            )
