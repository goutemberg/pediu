import json
from pathlib import Path, PurePosixPath

from django.conf import settings
from django.core.files import File
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.catalog.models import Product
from apps.tenants.models import Tenant


IMPORT_KEY = "preserva_pet_images_346_v1"
TENANT_SLUG = "preserva-pet"


class Command(BaseCommand):
    help = "Envia as imagens do catálogo PRESERVA PET ao Cloudinary e associa aos produtos existentes."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--once", action="store_true")

    def handle(self, *args, **options):
        if not getattr(settings, "CLOUDINARY_CONFIGURED", False):
            raise CommandError("Cloudinary não está configurado. Verifique as três variáveis CLOUDINARY_*.")

        base_dir = Path(settings.BASE_DIR)
        manifest_path = base_dir / "seed_data" / "preserva_pet" / "PRODUCTS.json"
        images_dir = (
            base_dir / "carga-ampliada-preserva-pet-pediu"
            / "seed_data" / "preserva_pet" / "images"
        )
        if not manifest_path.is_file():
            raise CommandError(f"Manifesto não encontrado: {manifest_path}")
        if not images_dir.is_dir():
            raise CommandError(f"Pasta de imagens não encontrada: {images_dir}")

        try:
            items = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise CommandError(f"Não foi possível ler PRODUCTS.json: {exc}") from exc
        if not isinstance(items, list) or not items:
            raise CommandError("PRODUCTS.json está vazio ou possui formato inválido.")

        validated, missing_files = [], []
        for item in items:
            code = str(item.get("code", "")).strip()
            filename = str(item.get("image", "")).strip()
            if not code or not filename or PurePosixPath(filename).name != filename:
                raise CommandError(f"Registro inválido no catálogo: {item!r}")
            path = images_dir / filename
            if not path.is_file():
                missing_files.append(filename)
            else:
                validated.append((code, filename, path))
        if missing_files:
            raise CommandError(
                f"Faltam {len(missing_files)} imagens. Exemplos: {', '.join(missing_files[:10])}"
            )

        try:
            tenant = Tenant.objects.get(slug=TENANT_SLUG)
        except Tenant.DoesNotExist as exc:
            raise CommandError(f"Loja '{TENANT_SLUG}' não encontrada no banco.") from exc

        imports = dict((tenant.settings or {}).get("catalog_imports") or {})
        if options["once"] and imports.get(IMPORT_KEY):
            self.stdout.write(self.style.WARNING("Migração já concluída. Nenhuma alteração feita."))
            self.stdout.write(f"Registro: {imports[IMPORT_KEY]}")
            return

        codes = [code for code, _, _ in validated]
        products = {
            product.code: product
            for product in Product.objects.filter(tenant=tenant, code__in=codes)
        }

        missing_products = 0
        custom_preserved = 0
        to_upload = []
        for code, filename, path in validated:
            product = products.get(code)
            if product is None:
                missing_products += 1
                continue
            current_name = product.image.name if product.image else ""
            if current_name and PurePosixPath(current_name).name != filename:
                custom_preserved += 1
                continue
            # Campo vazio: preencher. Mesmo basename do catálogo: reenvia para
            # corrigir eventual referência ao disco efêmero antigo do Render.
            to_upload.append((product, filename, path))

        self.stdout.write(f"Loja: {tenant.name} ({tenant.slug})")
        self.stdout.write(f"Imagens no manifesto: {len(validated)}")
        self.stdout.write(f"Produtos encontrados: {len(products)}")
        self.stdout.write(f"Imagens a enviar/regularizar: {len(to_upload)}")
        self.stdout.write(f"Fotos personalizadas preservadas: {custom_preserved}")
        self.stdout.write(f"Produtos não encontrados: {missing_products}")

        if options["dry_run"]:
            self.stdout.write(self.style.WARNING("SIMULAÇÃO: nenhum arquivo enviado ou registro alterado."))
            return

        uploaded = 0
        failures = []
        for product, filename, path in to_upload:
            try:
                with path.open("rb") as source:
                    product.image.save(filename, File(source), save=True)
                uploaded += 1
                if uploaded % 25 == 0:
                    self.stdout.write(f"Imagens processadas: {uploaded}/{len(to_upload)}")
            except Exception as exc:
                failures.append(f"{product.code} ({filename}): {exc}")
                self.stderr.write(self.style.ERROR(f"Falha no produto {product.code}: {exc}"))

        if failures:
            raise CommandError(
                f"Envio incompleto: {uploaded} enviadas e {len(failures)} falhas. "
                "A execução pode ser repetida; produtos já atualizados serão ignorados."
            )

        if options["once"]:
            with transaction.atomic():
                locked = Tenant.objects.select_for_update().get(pk=tenant.pk)
                data = dict(locked.settings or {})
                catalog_imports = dict(data.get("catalog_imports") or {})
                catalog_imports[IMPORT_KEY] = {
                    "completed_at": timezone.now().isoformat(),
                    "manifest_images": len(validated),
                    "uploaded": uploaded,
                    "custom_images_preserved": custom_preserved,
                    "products_not_found": missing_products,
                }
                data["catalog_imports"] = catalog_imports
                locked.settings = data
                locked.save(update_fields=["settings", "updated_at"])

        self.stdout.write(self.style.SUCCESS("Migração das imagens PRESERVA PET concluída."))
        self.stdout.write(f"Imagens enviadas: {uploaded}")
        self.stdout.write(f"Fotos personalizadas preservadas: {custom_preserved}")
        self.stdout.write(f"Produtos sem correspondência: {missing_products}")
        if options["once"]:
            self.stdout.write(f"Trava registrada: {IMPORT_KEY}")
