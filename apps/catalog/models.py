from decimal import Decimal

from django.db import models

from apps.tenants.models import Tenant


class Category(models.Model):
    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name="categories",
    )
    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=120)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "slug"],
                name="uniq_category_slug_per_tenant",
            ),
        ]
        ordering = ["name"]

    def __str__(self):
        return self.name


class ProductCodeSequence(models.Model):
    """
    Contador independente de códigos de produtos por empresa.

    next_number representa o próximo número disponível
    para geração automática.
    """

    tenant = models.OneToOneField(
        Tenant,
        on_delete=models.CASCADE,
        related_name="product_code_sequence",
    )

    next_number = models.PositiveBigIntegerField(default=1)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(next_number__gte=1),
                name="product_sequence_number_positive",
            ),
        ]

    def __str__(self):
        return f"{self.tenant.name} - PROD-{self.next_number:06d}"


class Product(models.Model):

    UNIT_CHOICES = [
        ("UN", "Unidade"),
        ("KG", "Quilograma (kg)"),
        ("G", "Grama (g)"),
        ("L", "Litro (L)"),
        ("ML", "Mililitro (ml)"),
        ("PCT", "Pacote"),
        ("CX", "Caixa"),
        ("FD", "Fardo"),
        ("SC", "Saco"),
        ("PAR", "Par"),
        ("KIT", "Kit"),
        ("DZ", "Dúzia"),
    ]

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name="products",
    )

    category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="products",
    )

    code = models.CharField(max_length=50)
    name = models.CharField(max_length=180)
    description = models.TextField(blank=True)

    image = models.ImageField(
        upload_to="tenants/%Y/%m/products/",
        blank=True,
    )

    price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
    )

    unit = models.CharField(
        max_length=10,
        choices=UNIT_CHOICES,
        default="UN",
    )

    minimum_quantity = models.DecimalField(
        max_digits=14,
        decimal_places=3,
        default=Decimal("1.000"),
        help_text="Quantidade mínima permitida para o pedido.",
    )

    quantity_multiple = models.DecimalField(
        max_digits=14,
        decimal_places=3,
        default=Decimal("1.000"),
        help_text="Intervalo em que a quantidade pode ser comprada.",
    )

    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "code"],
                name="uniq_product_code_per_tenant",
            ),
            models.CheckConstraint(
                condition=models.Q(price__gte=Decimal("0.00")),
                name="product_price_nonnegative",
            ),
            models.CheckConstraint(
                condition=models.Q(minimum_quantity__gt=Decimal("0.000")),
                name="product_min_qty_positive",
            ),
            models.CheckConstraint(
                condition=models.Q(quantity_multiple__gt=Decimal("0.000")),
                name="product_multiple_positive",
            ),
        ]

        ordering = ["name"]

    def __str__(self):
        return f"{self.code} - {self.name}"
