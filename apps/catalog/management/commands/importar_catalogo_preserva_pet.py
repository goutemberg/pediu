import json
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify

from apps.catalog.models import Category, Product
from apps.inventory.models import StockBalance
from apps.tenants.models import Tenant


IMPORT_KEY = "preserva_pet_catalog_346_v1"
EXPECTED_TENANT_SLUG = "preserva-pet"


class Command(BaseCommand):
    help = (
        "Importa uma única vez o catálogo ampliado da PRESERVA PET. "
        "A carga não altera estoques existentes nem importa imagens."
    )

    def add_arguments(self, parser):
        parser.add_argument("--tenant-slug", required=True)
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Mostra o resumo sem gravar alterações.",
        )
        parser.add_argument(
            "--once",
            action="store_true",
            help="Registra no tenant que a carga foi concluída e impede repetição.",
        )

    def handle(self, *args, **options):
        tenant_slug = options["tenant_slug"].strip()
        if tenant_slug != EXPECTED_TENANT_SLUG:
            raise CommandError(
                f"Esta carga está protegida para a loja '{EXPECTED_TENANT_SLUG}'. "
                f"Slug recebido: '{tenant_slug}'."
            )

        data_path = (
            Path(__file__).resolve().parents[4]
            / "seed_data"
            / "preserva_pet"
            / "PRODUCTS.json"
        )
        if not data_path.is_file():
            raise CommandError(f"Arquivo do catálogo não encontrado: {data_path}")

        try:
            products = json.loads(data_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise CommandError(f"Não foi possível ler PRODUCTS.json: {exc}") from exc

        self._validate_products(products)

        with transaction.atomic():
            try:
                tenant = Tenant.objects.select_for_update().get(slug=tenant_slug)
            except Tenant.DoesNotExist as exc:
                raise CommandError(
                    f"Loja '{tenant_slug}' não encontrada no banco de produção."
                ) from exc

            settings_data = dict(tenant.settings or {})
            imports = dict(settings_data.get("catalog_imports") or {})

            if options["once"] and imports.get(IMPORT_KEY):
                self.stdout.write(
                    self.style.WARNING(
                        "A carga já foi concluída anteriormente. Nenhuma alteração foi feita."
                    )
                )
                self.stdout.write(f"Loja: {tenant.name} ({tenant.slug})")
                self.stdout.write(f"Registro: {imports[IMPORT_KEY]}")
                return

            codes = [str(item["code"]).strip() for item in products]
            existing = Product.objects.filter(
                tenant=tenant,
                code__in=codes,
            ).count()
            new_count = len(products) - existing
            categories = sorted({item["cat"].strip() for item in products})

            if options["dry_run"]:
                self.stdout.write(self.style.WARNING("SIMULAÇÃO — nenhuma alteração gravada."))
                self.stdout.write(f"Loja: {tenant.name} ({tenant.slug})")
                self.stdout.write(f"Produtos no catálogo: {len(products)}")
                self.stdout.write(f"Produtos novos: {new_count}")
                self.stdout.write(f"Produtos existentes que serão atualizados: {existing}")
                self.stdout.write(f"Categorias do catálogo: {len(categories)}")
                self.stdout.write("Imagens: não serão importadas nesta etapa.")
                self.stdout.write("Estoque inicial dos novos produtos: zero.")
                return

            created_products = 0
            updated_products = 0
            created_categories = set()
            created_stocks = 0

            for item in products:
                category_name = item["cat"].strip()
                category, category_created = Category.objects.get_or_create(
                    tenant=tenant,
                    slug=slugify(category_name),
                    defaults={"name": category_name, "is_active": True},
                )
                if category_created:
                    created_categories.add(category.name)

                code = str(item["code"]).strip()
                price = Decimal(str(item["price"])).quantize(Decimal("0.01"))

                product, was_created = Product.objects.update_or_create(
                    tenant=tenant,
                    code=code,
                    defaults={
                        "category": category,
                        "name": item["name"].strip(),
                        "description": item.get("desc", "").strip(),
                        "price": price,
                        "unit": item.get("unit", "UN"),
                        "minimum_quantity": Decimal("1.000"),
                        "quantity_multiple": Decimal("1.000"),
                        "is_active": True,
                    },
                )

                if was_created:
                    created_products += 1
                else:
                    updated_products += 1

                # Não modifica saldo existente. Novos produtos começam zerados.
                _, stock_created = StockBalance.objects.get_or_create(
                    tenant=tenant,
                    product=product,
                    defaults={"physical_quantity": Decimal("0.000")},
                )
                if stock_created:
                    created_stocks += 1

            if options["once"]:
                imports[IMPORT_KEY] = {
                    "completed_at": timezone.now().isoformat(),
                    "products_in_file": len(products),
                    "created": created_products,
                    "updated": updated_products,
                }
                settings_data["catalog_imports"] = imports
                tenant.settings = settings_data
                tenant.save(update_fields=["settings", "updated_at"])

        self.stdout.write(self.style.SUCCESS("Importação PRESERVA PET concluída."))
        self.stdout.write(f"Loja: {tenant.name} ({tenant.slug})")
        self.stdout.write(f"Produtos criados: {created_products}")
        self.stdout.write(f"Produtos atualizados: {updated_products}")
        self.stdout.write(f"Categorias novas: {len(created_categories)}")
        self.stdout.write(f"Estoques novos criados com saldo zero: {created_stocks}")
        self.stdout.write("Estoques, imagens e pedidos existentes foram preservados.")
        if options["once"]:
            self.stdout.write(f"Trava de execução registrada: {IMPORT_KEY}")

    @staticmethod
    def _validate_products(products):
        if not isinstance(products, list) or not products:
            raise CommandError("PRODUCTS.json está vazio ou não contém uma lista.")

        valid_units = {"UN", "KG", "G", "L", "ML", "PCT", "CX", "FD", "SC", "PAR", "KIT", "DZ"}
        seen_codes = set()

        for index, item in enumerate(products, start=1):
            if not isinstance(item, dict):
                raise CommandError(f"Registro {index} não é um objeto válido.")

            for field in ("code", "name", "price", "cat"):
                if not str(item.get(field, "")).strip():
                    raise CommandError(f"Registro {index}: campo '{field}' ausente.")

            code = str(item["code"]).strip()
            name = str(item["name"]).strip()
            if code in seen_codes:
                raise CommandError(f"Código duplicado no catálogo: {code}")
            seen_codes.add(code)

            if len(code) > 50:
                raise CommandError(f"Código excede 50 caracteres: {code}")
            if len(name) > 180:
                raise CommandError(f"Nome excede 180 caracteres: {name}")

            try:
                price = Decimal(str(item["price"]))
            except (InvalidOperation, TypeError, ValueError) as exc:
                raise CommandError(f"Preço inválido no produto {code}.") from exc
            if not price.is_finite() or price < 0 or price.as_tuple().exponent < -2:
                raise CommandError(f"Preço inválido ou com mais de 2 casas decimais: {code}")

            unit = item.get("unit", "UN")
            if unit not in valid_units:
                raise CommandError(f"Unidade inválida no produto {code}: {unit}")
