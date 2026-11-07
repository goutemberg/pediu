from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.core.files.base import ContentFile
from django.db import transaction
from django.utils.text import slugify

from apps.catalog.models import Category, Product
from apps.inventory.models import StockBalance, StockMovement
from apps.tenants.models import Tenant


PRODUCTS = [
    {
        "code": "101142",
        "name": "Alpiste Canadense 5kg",
        "price": "49.90",
        "unit": "UN",
        "cat": "Sementes",
        "desc": "Alpiste canadense. Embalagem de 5 kg, conforme catálogo Preserva Pet.",
        "image": "101142.jpg"
    },
    {
        "code": "101575",
        "name": "Girassol Miúdo 5kg",
        "price": "44.90",
        "unit": "UN",
        "cat": "Sementes",
        "desc": "Girassol miúdo. Embalagem de 5 kg, conforme catálogo Preserva Pet.",
        "image": "101575.jpg"
    },
    {
        "code": "101572",
        "name": "Painço Comum 5kg",
        "price": "37.50",
        "unit": "UN",
        "cat": "Sementes",
        "desc": "Painço comum. Embalagem de 5 kg, conforme catálogo Preserva Pet.",
        "image": "101572.jpg"
    },
    {
        "code": "101584",
        "name": "Painço Preto 5kg",
        "price": "44.90",
        "unit": "UN",
        "cat": "Sementes",
        "desc": "Painço preto. Embalagem de 5 kg, conforme catálogo Preserva Pet.",
        "image": "101584.jpg"
    },
    {
        "code": "1751",
        "name": "Sellecta Sabores 500g",
        "price": "11.99",
        "unit": "UN",
        "cat": "Alimentos e rações",
        "desc": "Ração Sellecta Sabores, embalagem de 500 g.",
        "image": "1751.jpg"
    },
    {
        "code": "2485",
        "name": "Sellecta Extrusado Canário 180g",
        "price": "11.99",
        "unit": "UN",
        "cat": "Alimentos e rações",
        "desc": "Alimento extrusado Sellecta para canário, embalagem de 180 g.",
        "image": "2485.jpg"
    },
    {
        "code": "605",
        "name": "Nutrópica Curió 300g",
        "price": "33.00",
        "unit": "UN",
        "cat": "Alimentos e rações",
        "desc": "Alimento Nutrópica para curió, embalagem de 300 g.",
        "image": "605.jpg"
    },
    {
        "code": "608",
        "name": "Nutrópica Egg Max 300g",
        "price": "59.90",
        "unit": "UN",
        "cat": "Alimentos e rações",
        "desc": "Nutrópica Egg Max, embalagem de 300 g.",
        "image": "608.jpg"
    },
    {
        "code": "3303",
        "name": "Biotron Curió, Bicudo e Azulão 500g",
        "price": "17.99",
        "unit": "UN",
        "cat": "Alimentos e rações",
        "desc": "Mistura Biotron para curió, bicudo e azulão, embalagem de 500 g.",
        "image": "3303.jpg"
    },
    {
        "code": "703",
        "name": "Biotron CC Fruta Mix 500g",
        "price": "19.90",
        "unit": "UN",
        "cat": "Alimentos e rações",
        "desc": "Mistura Biotron CC Fruta Mix, embalagem de 500 g.",
        "image": "703.jpg"
    },
    {
        "code": "CB01",
        "name": "Cálcio Bloco Natural",
        "price": "15.99",
        "unit": "CX",
        "cat": "Suplementos e minerais",
        "desc": "Cálcio em bloco natural. O catálogo informa caixa com 20 unidades.",
        "image": "CB01.jpg"
    },
    {
        "code": "288",
        "name": "Canto Lindo Cálcio 20ml",
        "price": "8.99",
        "unit": "UN",
        "cat": "Vitaminas e cuidados",
        "desc": "Canto Lindo Cálcio, frasco de 20 ml.",
        "image": "288.jpg"
    },
    {
        "code": "6708",
        "name": "Biotrin Complexo Vitamínico 20ml",
        "price": "9.99",
        "unit": "UN",
        "cat": "Vitaminas e cuidados",
        "desc": "Biotrin Complexo Vitamínico, frasco de 20 ml.",
        "image": "6708.jpg"
    },
    {
        "code": "428",
        "name": "Avitop Aarão Vitamínico 15ml",
        "price": "11.99",
        "unit": "UN",
        "cat": "Vitaminas e cuidados",
        "desc": "Avitop Aarão Vitamínico, frasco de 15 ml.",
        "image": "428.jpg"
    },
    {
        "code": "721",
        "name": "Seta Iodo 15ml",
        "price": "14.99",
        "unit": "UN",
        "cat": "Vitaminas e cuidados",
        "desc": "Suplemento Seta Iodo, frasco de 15 ml.",
        "image": "721.jpg"
    },
    {
        "code": "61",
        "name": "Banheira com Gancho Cristal 90ml",
        "price": "31.90",
        "unit": "UN",
        "cat": "Acessórios",
        "desc": "Banheira com gancho cristal, capacidade de 90 ml. O catálogo informa pacote com 12 unidades.",
        "image": "61.jpg"
    },
    {
        "code": "73",
        "name": "Bebedouro Original Curió 45ml",
        "price": "25.90",
        "unit": "UN",
        "cat": "Acessórios",
        "desc": "Bebedouro original para curió, capacidade de 45 ml. O catálogo informa pacote com 12 unidades.",
        "image": "73.jpg"
    },
    {
        "code": "660",
        "name": "Comedouro Tamanho G",
        "price": "6.49",
        "unit": "UN",
        "cat": "Acessórios",
        "desc": "Comedouro tamanho G.",
        "image": "660.jpg"
    },
    {
        "code": "1000",
        "name": "Ninho Bola Luxo",
        "price": "6.99",
        "unit": "UN",
        "cat": "Ninhos e acomodação",
        "desc": "Ninho modelo bola luxo.",
        "image": "1000.jpg"
    },
    {
        "code": "1009",
        "name": "Osso Siba Caixa com 20 unidades",
        "price": "45.00",
        "unit": "CX",
        "cat": "Acessórios",
        "desc": "Osso de siba. Caixa com 20 unidades, conforme catálogo Preserva Pet.",
        "image": "1009.jpg"
    },
    {
        "code": "400",
        "name": "Areia Mineral Fina 700g",
        "price": "8.99",
        "unit": "UN",
        "cat": "Higiene e minerais",
        "desc": "Areia mineral fina Tal Pássaros, embalagem de 700 g.",
        "image": "400.jpg"
    },
    {
        "code": "431",
        "name": "Argila Mix Tal Pássaros",
        "price": "11.00",
        "unit": "UN",
        "cat": "Suplementos e minerais",
        "desc": "Argila Mix Tal Pássaros.",
        "image": "431.jpg"
    }
]


class Command(BaseCommand):
    help = "Importa produtos demonstrativos do catálogo Preserva Pet para uma loja."

    def add_arguments(self, parser):
        parser.add_argument(
            "--tenant-slug",
            required=True,
            help="Slug da loja que receberá os produtos.",
        )
        parser.add_argument(
            "--estoque-inicial",
            default="10",
            help="Estoque inicial por produto (padrão: 10 unidades/embalagens).",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        tenant_slug = options["tenant_slug"]
        try:
            initial_stock = Decimal(options["estoque_inicial"]).quantize(Decimal("0.001"))
        except (InvalidOperation, TypeError, ValueError):
            raise CommandError("Estoque inicial inválido. Informe um número, por exemplo 10.")

        if initial_stock < 0:
            raise CommandError("O estoque inicial não pode ser negativo.")

        try:
            tenant = Tenant.objects.get(slug=tenant_slug)
        except Tenant.DoesNotExist:
            raise CommandError(
                f'Não encontrei uma loja com slug "{tenant_slug}". '
                "Confira o slug no painel do pediu."
            )

        image_dir = (
            Path(settings.BASE_DIR)
            / "seed_data"
            / "preserva_pet"
            / "images"
        )

        created_products = 0
        updated_products = 0
        created_categories = set()
        attached_images = 0
        created_stocks = 0

        for item in PRODUCTS:
            category_slug = slugify(item["cat"])

            category, category_created = Category.objects.get_or_create(
                tenant=tenant,
                slug=category_slug,
                defaults={
                    "name": item["cat"],
                    "is_active": True,
                },
            )
            if category_created:
                created_categories.add(category.name)

            product, product_created = Product.objects.update_or_create(
                tenant=tenant,
                code=item["code"],
                defaults={
                    "category": category,
                    "name": item["name"],
                    "description": item["desc"],
                    "price": Decimal(item["price"]),
                    "unit": item["unit"],
                    "minimum_quantity": Decimal("1.000"),
                    "quantity_multiple": Decimal("1.000"),
                    "is_active": True,
                },
            )

            if product_created:
                created_products += 1
            else:
                updated_products += 1

            image_path = image_dir / item["image"]
            if not product.image and image_path.is_file():
                product.image.save(
                    item["image"],
                    ContentFile(image_path.read_bytes()),
                    save=True,
                )
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
                        note="Estoque inicial da carga demonstrativa Preserva Pet.",
                    )

        self.stdout.write(self.style.SUCCESS("Carga Preserva Pet concluída!"))
        self.stdout.write(f"Loja: {tenant.name} ({tenant.slug})")
        self.stdout.write(f"Categorias novas: {len(created_categories)}")
        self.stdout.write(f"Produtos criados: {created_products}")
        self.stdout.write(f"Produtos atualizados: {updated_products}")
        self.stdout.write(f"Imagens anexadas: {attached_images}")
        self.stdout.write(f"Estoques criados: {created_stocks}")
        self.stdout.write(
            "Observação: estoques já existentes foram preservados; "
            "a execução pode ser repetida sem duplicar produtos."
        )
