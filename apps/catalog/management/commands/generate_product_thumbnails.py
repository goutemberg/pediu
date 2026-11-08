from django.core.management.base import BaseCommand

from apps.catalog.models import Product
from apps.catalog.signals import create_product_thumbnail


class Command(BaseCommand):
    help = "Gera miniaturas WebP para imagens de produtos já cadastrados."

    def handle(self, *args, **options):
        total = Product.objects.exclude(image="").count()
        generated = 0
        failed = 0
        for product in Product.objects.exclude(image="").iterator():
            if create_product_thumbnail(product):
                generated += 1
            else:
                failed += 1
        self.stdout.write(self.style.SUCCESS(
            f"Processadas {total} imagens: {generated} disponíveis, {failed} sem miniatura."
        ))
