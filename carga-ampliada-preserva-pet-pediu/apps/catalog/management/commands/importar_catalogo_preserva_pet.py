import json
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils.text import slugify

from apps.catalog.models import Category, Product
from apps.inventory.models import StockBalance, StockMovement
from apps.tenants.models import Tenant


class Command(BaseCommand):
    help = "Importa o catálogo Preserva Pet para uma loja específica."

    def add_arguments(self, parser):
        parser.add_argument("--tenant-slug", required=True)
        parser.add_argument("--estoque-inicial", default="0")
        parser.add_argument("--dry-run", action="store_true", help="Valida e mostra o resumo sem gravar alterações.")
        parser.add_argument("--incluir-imagens", action="store_true", help="Anexa as imagens recortadas do catálogo. Use apenas após configurar armazenamento persistente de mídia.")

    def handle(self, *args, **options):
        try:
            initial_stock = Decimal(options["estoque_inicial"]).quantize(Decimal("0.001"))
        except (InvalidOperation, TypeError, ValueError):
            raise CommandError("Estoque inicial inválido.")
        if initial_stock < 0:
            raise CommandError("O estoque inicial não pode ser negativo.")

        data_path = Path(settings.BASE_DIR) / "seed_data" / "preserva_pet" / "PRODUCTS.json"
        image_dir = Path(settings.BASE_DIR) / "seed_data" / "preserva_pet" / "images"
        if not data_path.is_file():
            raise CommandError(f"Arquivo de produtos não encontrado: {data_path}")
        products = json.loads(data_path.read_text(encoding="utf-8"))
        if not isinstance(products, list) or not products:
            raise CommandError("O arquivo PRODUCTS.json está vazio ou inválido.")

        codes = [str(p["code"]) for p in products]
        if len(codes) != len(set(codes)):
            raise CommandError("Há códigos duplicados no catálogo. A carga foi interrompida.")
        for p in products:
            try:
                Decimal(str(p["price"]))
            except (InvalidOperation, KeyError):
                raise CommandError(f"Preço inválido no produto {p.get('code', '?')}.")
            if not p.get("name") or not p.get("cat") or not p.get("code"):
                raise CommandError("Há produto sem código, nome ou categoria.")

        try:
            tenant = Tenant.objects.get(slug=options["tenant_slug"])
        except Tenant.DoesNotExist:
            raise CommandError(f"Loja não encontrada: {options['tenant_slug']}")

        # Preview read-only: não cria categorias, produtos, imagens ou estoque.
        existing = Product.objects.filter(tenant=tenant, code__in=codes).count()
        new_count = len(products) - existing
        categories = sorted({p["cat"] for p in products})
        images = sum(1 for p in products if options["incluir_imagens"] and p.get("image") and (image_dir / p["image"]).is_file())
        if options["dry_run"]:
            self.stdout.write(self.style.WARNING("SIMULAÇÃO — nenhuma alteração foi gravada."))
            self.stdout.write(f"Loja: {tenant.name} ({tenant.slug})")
            self.stdout.write(f"Produtos no catálogo: {len(products)}")
            self.stdout.write(f"Produtos já existentes que serão atualizados: {existing}")
            self.stdout.write(f"Produtos novos: {new_count}")
            self.stdout.write(f"Categorias: {len(categories)}")
            self.stdout.write(f"Imagens disponíveis: {images}")
            self.stdout.write(f"Estoque inicial solicitado: {initial_stock}")
            return

        created_products = updated_products = attached_images = created_stocks = 0
        created_categories = set()
        with transaction.atomic():
            for item in products:
                category, category_created = Category.objects.get_or_create(
                    tenant=tenant,
                    slug=slugify(item["cat"]),
                    defaults={"name": item["cat"], "is_active": True},
                )
                if category_created:
                    created_categories.add(category.name)

                product, was_created = Product.objects.update_or_create(
                    tenant=tenant,
                    code=item["code"],
                    defaults={
                        "category": category,
                        "name": item["name"],
                        "description": item["desc"],
                        "price": Decimal(item["price"]),
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

                image_name = item.get("image") if options["incluir_imagens"] else None
                image_path = image_dir / image_name if image_name else None
                if image_path and image_path.is_file() and not product.image:
                    product.image.save(image_name, ContentFile(image_path.read_bytes()), save=True)
                    attached_images += 1

                stock, stock_created = StockBalance.objects.get_or_create(
                    tenant=tenant,
                    product=product,
                    defaults={"physical_quantity": initial_stock},
                )
                if stock_created:
                    created_stocks += 1
                    if initial_stock > 0:
                        StockMovement.objects.create(
                            tenant=tenant,
                            product=product,
                            kind=StockMovement.Kind.IN,
                            quantity=initial_stock,
                            reference="CARGA_INICIAL_CATALOGO",
                            note="Estoque inicial informado na importação do catálogo Preserva Pet.",
                        )

        self.stdout.write(self.style.SUCCESS("Carga Preserva Pet concluída."))
        self.stdout.write(f"Loja: {tenant.name} ({tenant.slug})")
        self.stdout.write(f"Produtos criados: {created_products}")
        self.stdout.write(f"Produtos atualizados: {updated_products}")
        self.stdout.write(f"Categorias novas: {len(created_categories)}")
        self.stdout.write(f"Imagens anexadas: {attached_images}")
        self.stdout.write(f"Saldos de estoque criados: {created_stocks}")
        self.stdout.write("Saldos existentes e imagens já cadastradas foram preservados.")
