import logging
from io import BytesIO
from pathlib import PurePosixPath

from django.core.files.base import ContentFile
from django.db.models.signals import post_save
from django.dispatch import receiver
from PIL import Image, ImageOps

from apps.catalog.models import Product

logger = logging.getLogger(__name__)


def create_product_thumbnail(product):
    if not product.image:
        return False

    storage = product.image.storage
    source_name = product.image.name
    source_path = PurePosixPath(source_name)
    thumbnail_name = str(source_path.with_name(f"{source_path.stem}_thumb.webp"))

    try:
        if storage.exists(thumbnail_name):
            return True

        with storage.open(source_name, "rb") as source:
            image = Image.open(source)
            image = ImageOps.exif_transpose(image)
            image.thumbnail((600, 600), Image.Resampling.LANCZOS)
            if image.mode not in ("RGB", "RGBA"):
                image = image.convert("RGBA" if "transparency" in image.info else "RGB")
            output = BytesIO()
            image.save(output, format="WEBP", quality=80, method=5)
            storage.save(thumbnail_name, ContentFile(output.getvalue()))
        return True
    except Exception:
        # A miniatura é otimização; falhas não devem impedir o cadastro do produto.
        logger.exception("Não foi possível gerar miniatura para o produto %s", product.pk)
        return False


@receiver(post_save, sender=Product)
def generate_product_thumbnail(sender, instance, **kwargs):
    create_product_thumbnail(instance)
