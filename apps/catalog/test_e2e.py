from contextlib import contextmanager
from decimal import Decimal

import pytest
from django.urls import reverse
from playwright.sync_api import sync_playwright

from apps.catalog.models import Category, Product
from apps.inventory.models import StockBalance, StockMovement

TEST_PASSWORD = "E2E-Test-Password-2026!"


@pytest.fixture
def catalog_category(tenant):
    """
    Cria uma categoria vinculada à empresa do teste.
    """

    return Category.objects.create(
        tenant=tenant,
        name="Bebidas",
        slug="bebidas",
        is_active=True,
    )


@pytest.fixture
def e2e_page():
    """
    Retorna um gerenciador de contexto para iniciar o Playwright
    somente quando o teste estiver pronto para interagir com o navegador.

    Isso permite executar operações ORM antes e depois do navegador,
    sem manter o loop do Playwright ativo durante essas operações.
    """

    @contextmanager
    def open_page():
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page()

            try:
                yield page
            finally:
                browser.close()

    return open_page


def prepare_user_for_login(user):
    """
    Prepara o usuário antes de iniciar o Playwright.
    """

    user.set_password(TEST_PASSWORD)
    user.is_active = True
    user.save(update_fields=["password", "is_active"])


def login_user(page, live_server, user):
    """
    Autentica o usuário pela tela real de login.
    Não executa operações ORM.
    """

    page.goto(f"{live_server.url}{reverse('login')}")

    page.locator("#id_username").fill(user.email)
    page.locator("#id_password").fill(TEST_PASSWORD)

    page.get_by_role(
        "button",
        name="Entrar na plataforma",
    ).click()

    page.wait_for_url(f"**{reverse('dashboard:home')}")


def prepare_tenant(tenant, membership):
    """
    Garante que a empresa e o vínculo estejam ativos
    durante o teste E2E.
    """

    tenant.status = "active"
    tenant.save(update_fields=["status"])

    membership.is_active = True
    membership.save(update_fields=["is_active"])


def fill_required_product_fields(page, category, name):
    """
    Preenche os campos obrigatórios do produto.
    """

    page.locator("#id_name").fill(name)

    page.locator("#id_category").select_option(str(category.pk))

    unit = page.locator("#id_unit").evaluate("""
        element => {
            const option = Array.from(element.options)
                .find(option => option.value !== "");

            return option ? option.value : "";
        }
        """)

    assert unit, "O formulário não possui unidades disponíveis."

    page.locator("#id_unit").select_option(unit)

    page.locator("#id_price").fill("25.90")
    page.locator("#id_minimum_quantity").fill("1.000")
    page.locator("#id_quantity_multiple").fill("1.000")


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
def test_product_create_with_automatic_code_and_initial_stock(
    live_server,
    user,
    tenant,
    membership,
    catalog_category,
    e2e_page,
):
    """
    Testa o cadastro completo de um produto com:
    - Código automático;
    - Categoria;
    - Informações comerciais;
    - Estoque inicial;
    - Movimentação de entrada.
    """

    prepare_tenant(tenant, membership)
    prepare_user_for_login(user)

    catalog_category.is_active = True
    catalog_category.save(update_fields=["is_active"])

    with e2e_page() as page:
        login_user(page, live_server, user)

        page.goto(f"{live_server.url}{reverse('catalog:product-create')}")

        page.get_by_role(
            "heading",
            name="Novo produto",
        ).wait_for()

        page.locator('input[name="code_mode"][value="auto"]').check()

        fill_required_product_fields(
            page,
            catalog_category,
            "Produto E2E Automático",
        )

        page.locator("#id_initial_stock").fill("15.000")

        page.get_by_role(
            "button",
            name="Salvar produto",
        ).click()

        page.wait_for_url(f"**{reverse('catalog:product-list')}")

        page.get_by_text(
            "Produto PROD-000001 cadastrado com sucesso!",
            exact=True,
        ).wait_for()

    # Consultas ao banco somente depois de fechar o Playwright.
    product = Product.objects.get(
        tenant=tenant,
        name="Produto E2E Automático",
    )

    assert product.code == "PROD-000001"
    assert product.category == catalog_category
    assert product.price == Decimal("25.90")

    balance = StockBalance.objects.get(
        tenant=tenant,
        product=product,
    )

    assert balance.physical_quantity == Decimal("15.000")
    assert balance.reserved_quantity == Decimal("0.000")

    movement = StockMovement.objects.get(
        tenant=tenant,
        product=product,
        reference="ESTOQUE_INICIAL",
    )

    assert movement.quantity == Decimal("15.000")


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
def test_product_create_with_manual_code(
    live_server,
    user,
    tenant,
    membership,
    catalog_category,
    e2e_page,
):
    """
    Testa o cadastro de produto com código manual.
    """

    prepare_tenant(tenant, membership)
    prepare_user_for_login(user)

    catalog_category.is_active = True
    catalog_category.save(update_fields=["is_active"])

    with e2e_page() as page:
        login_user(page, live_server, user)

        page.goto(f"{live_server.url}{reverse('catalog:product-create')}")

        page.locator('input[name="code_mode"][value="manual"]').check()

        manual_code = page.locator("#id_manual_code")

        manual_code.wait_for(state="visible")
        manual_code.fill("meu-produto-001")

        fill_required_product_fields(
            page,
            catalog_category,
            "Produto E2E Manual",
        )

        page.locator("#id_initial_stock").fill("5.000")

        page.get_by_role(
            "button",
            name="Salvar produto",
        ).click()

        page.wait_for_url(f"**{reverse('catalog:product-list')}")

        page.get_by_text(
            "Produto MEU-PRODUTO-001 cadastrado com sucesso!",
            exact=True,
        ).wait_for()

    product = Product.objects.get(
        tenant=tenant,
        name="Produto E2E Manual",
    )

    assert product.code == "MEU-PRODUTO-001"


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
def test_product_create_rejects_duplicate_manual_code(
    live_server,
    user,
    tenant,
    membership,
    catalog_category,
    product,
    e2e_page,
):
    """
    Testa a validação de código manual duplicado.
    """

    prepare_tenant(tenant, membership)
    prepare_user_for_login(user)

    catalog_category.is_active = True
    catalog_category.save(update_fields=["is_active"])

    with e2e_page() as page:
        login_user(page, live_server, user)

        page.goto(f"{live_server.url}{reverse('catalog:product-create')}")

        page.locator('input[name="code_mode"][value="manual"]').check()

        page.locator("#id_manual_code").fill(product.code)

        fill_required_product_fields(
            page,
            catalog_category,
            "Produto com Código Duplicado",
        )

        page.locator("#id_initial_stock").fill("0")

        page.get_by_role(
            "button",
            name="Salvar produto",
        ).click()

        page.get_by_text(
            "Já existe um produto com esse código na sua empresa.",
            exact=True,
        ).wait_for()

    assert not Product.objects.filter(
        tenant=tenant,
        name="Produto com Código Duplicado",
    ).exists()


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
def test_product_update_preserves_code(
    live_server,
    user,
    tenant,
    membership,
    product,
    catalog_category,
    e2e_page,
):
    """
    Testa a edição de produto pelo navegador.
    O código original deve permanecer inalterado.
    """

    prepare_tenant(tenant, membership)
    prepare_user_for_login(user)

    # A fixture original cria o produto sem categoria.
    # Como a categoria é obrigatória, associamos uma categoria ativa.
    catalog_category.is_active = True
    catalog_category.save(update_fields=["is_active"])

    product.category = catalog_category
    product.save(update_fields=["category"])

    original_code = product.code

    with e2e_page() as page:
        login_user(page, live_server, user)

        page.goto(
            f"{live_server.url}"
            f"{reverse('catalog:product-update', kwargs={'product_id': product.pk})}"
        )

        page.get_by_role(
            "heading",
            name="Editar produto",
        ).wait_for()

        code_field = page.locator("#id_current_code")

        assert code_field.input_value() == original_code
        assert code_field.is_disabled()

        # Atualiza os dados comerciais.
        page.locator("#id_name").fill("Produto E2E Atualizado")

        # Mantém uma categoria válida durante a edição.
        page.locator("#id_category").select_option(str(catalog_category.pk))

        # Ajusta o estoque físico.
        page.locator("#stock_quantity").fill("0.000")

        page.locator("#stock_adjustment_reason").fill(
            "Teste E2E de edição sem alteração de estoque"
        )

        page.get_by_role(
            "button",
            name="Salvar alterações",
        ).click()

        page.wait_for_url(f"**{reverse('catalog:product-list')}")

    # Confere o resultado diretamente no banco.
    product.refresh_from_db()

    assert product.name == "Produto E2E Atualizado"
    assert product.code == original_code
    assert product.category == catalog_category


# =========================================================
# TESTES E2E DE CATEGORIAS
# =========================================================


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
def test_category_create_successfully(live_server, user, tenant, membership, e2e_page):
    """Cadastra uma categoria pela interface e confere o registro no banco."""
    prepare_tenant(tenant, membership)
    prepare_user_for_login(user)

    with e2e_page() as page:
        login_user(page, live_server, user)
        page.goto(f"{live_server.url}{reverse('catalog:category-create')}")
        page.locator("#id_name").fill("Mercearia E2E")
        page.get_by_role("button", name="Cadastrar categoria").click()
        page.wait_for_url(f"**{reverse('catalog:category-list')}")
        page.get_by_text("Mercearia E2E", exact=True).wait_for()
        page.get_by_text("Categoria cadastrada com sucesso!", exact=True).wait_for()

    category = Category.objects.get(tenant=tenant, name="Mercearia E2E")
    assert category.slug == "mercearia-e2e"
    assert category.is_active is True


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
def test_category_create_rejects_duplicate_name(
    live_server, user, tenant, membership, catalog_category, e2e_page
):
    """Impede o cadastro de categoria com nome já utilizado na empresa."""
    prepare_tenant(tenant, membership)
    prepare_user_for_login(user)

    with e2e_page() as page:
        login_user(page, live_server, user)
        page.goto(f"{live_server.url}{reverse('catalog:category-create')}")
        page.locator("#id_name").fill("bebidas")
        page.get_by_role("button", name="Cadastrar categoria").click()
        page.get_by_text(
            "Já existe uma categoria com esse nome.", exact=True
        ).wait_for()

    assert Category.objects.filter(tenant=tenant).count() == 1


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
def test_category_update_successfully(
    live_server, user, tenant, membership, catalog_category, e2e_page
):
    """Altera o nome da categoria pela tela de edição."""
    prepare_tenant(tenant, membership)
    prepare_user_for_login(user)

    with e2e_page() as page:
        login_user(page, live_server, user)
        page.goto(
            f"{live_server.url}{reverse('catalog:category-update', kwargs={'category_id': catalog_category.pk})}"
        )
        page.locator("#id_name").fill("Bebidas e Sucos")
        page.get_by_role("button", name="Salvar alterações").click()
        page.wait_for_url(f"**{reverse('catalog:category-list')}")
        page.get_by_text("Bebidas e Sucos", exact=True).wait_for()

    catalog_category.refresh_from_db()
    assert catalog_category.name == "Bebidas e Sucos"
    assert catalog_category.slug == "bebidas-e-sucos"


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
def test_category_search_by_name(
    live_server, user, tenant, membership, catalog_category, e2e_page
):
    """Pesquisa categorias pelo campo de busca da listagem."""
    prepare_tenant(tenant, membership)
    prepare_user_for_login(user)
    Category.objects.create(tenant=tenant, name="Higiene", slug="higiene")

    with e2e_page() as page:
        login_user(page, live_server, user)
        page.goto(f"{live_server.url}{reverse('catalog:category-list')}")
        page.locator('input[name="q"]').fill("Bebi")
        page.get_by_role("button", name="Filtrar").click()
        page.get_by_text("Bebidas", exact=True).wait_for()
        assert page.get_by_text("Higiene", exact=True).count() == 0


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
def test_category_filter_by_active_status(
    live_server, user, tenant, membership, catalog_category, e2e_page
):
    """Filtra a listagem para exibir somente categorias ativas."""
    prepare_tenant(tenant, membership)
    prepare_user_for_login(user)
    Category.objects.create(
        tenant=tenant, name="Inativa E2E", slug="inativa-e2e", is_active=False
    )

    with e2e_page() as page:
        login_user(page, live_server, user)
        page.goto(f"{live_server.url}{reverse('catalog:category-list')}")
        page.locator('select[name="status"]').select_option("active")
        page.get_by_role("button", name="Filtrar").click()
        page.get_by_text("Bebidas", exact=True).wait_for()
        assert page.get_by_text("Inativa E2E", exact=True).count() == 0


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
def test_category_filter_by_inactive_status(
    live_server, user, tenant, membership, catalog_category, e2e_page
):
    """Filtra a listagem para exibir somente categorias inativas."""
    prepare_tenant(tenant, membership)
    prepare_user_for_login(user)
    catalog_category.is_active = False
    catalog_category.save(update_fields=["is_active"])
    Category.objects.create(
        tenant=tenant, name="Ativa E2E", slug="ativa-e2e", is_active=True
    )

    with e2e_page() as page:
        login_user(page, live_server, user)
        page.goto(f"{live_server.url}{reverse('catalog:category-list')}")
        page.locator('select[name="status"]').select_option("inactive")
        page.get_by_role("button", name="Filtrar").click()
        page.get_by_text("Bebidas", exact=True).wait_for()
        assert page.get_by_text("Ativa E2E", exact=True).count() == 0


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
def test_category_toggle_status_deactivates_and_activates(
    live_server, user, tenant, membership, catalog_category, e2e_page
):
    """Desativa e depois reativa a categoria usando os formulários da listagem."""
    prepare_tenant(tenant, membership)
    prepare_user_for_login(user)

    with e2e_page() as page:
        login_user(page, live_server, user)
        page.goto(f"{live_server.url}{reverse('catalog:category-list')}")
        page.get_by_role("button", name="Desativar").click()
        page.get_by_text("Categoria desativada com sucesso.", exact=True).wait_for()
        page.get_by_role("button", name="Ativar").click()
        page.get_by_text("Categoria ativada com sucesso.", exact=True).wait_for()

    catalog_category.refresh_from_db()
    assert catalog_category.is_active is True


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
def test_category_list_displays_counters_and_product_count(
    live_server, user, tenant, membership, catalog_category, product, e2e_page
):
    """Confere os indicadores e a quantidade de produtos vinculados."""
    prepare_tenant(tenant, membership)
    prepare_user_for_login(user)
    product.category = catalog_category
    product.save(update_fields=["category"])
    Category.objects.create(
        tenant=tenant, name="Inativa E2E", slug="inativa-e2e", is_active=False
    )

    with e2e_page() as page:
        login_user(page, live_server, user)
        page.goto(f"{live_server.url}{reverse('catalog:category-list')}")
        page.get_by_text("Total de categorias", exact=True).wait_for()
        assert (
            page.locator(".product-stat").nth(0).locator("strong").inner_text() == "2"
        )
        assert (
            page.locator(".product-stat").nth(1).locator("strong").inner_text() == "1"
        )
        assert (
            page.locator(".product-stat").nth(2).locator("strong").inner_text() == "1"
        )
        row = page.locator("tbody tr").filter(has_text="Bebidas")
        assert row.locator("td").nth(2).inner_text() == "1"


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
def test_category_list_pagination(live_server, user, tenant, membership, e2e_page):
    """Verifica a navegação entre páginas quando há mais de 12 categorias."""
    prepare_tenant(tenant, membership)
    prepare_user_for_login(user)
    Category.objects.bulk_create(
        [
            Category(
                tenant=tenant,
                name=f"Categoria {number:02d}",
                slug=f"categoria-{number:02d}",
            )
            for number in range(1, 14)
        ]
    )

    with e2e_page() as page:
        login_user(page, live_server, user)
        page.goto(f"{live_server.url}{reverse('catalog:category-list')}")
        page.get_by_text("Página 1 de 2", exact=True).wait_for()
        page.get_by_role("link", name="Próxima").click()
        page.get_by_text("Página 2 de 2", exact=True).wait_for()
        page.get_by_role("link", name="Anterior").click()
        page.get_by_text("Página 1 de 2", exact=True).wait_for()
