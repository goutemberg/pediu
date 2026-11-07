from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone

from apps.tenants.models import Tenant
from apps.catalog.models import Product


class StockBalance(models.Model):
    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name="stock_balances",
    )

    product = models.OneToOneField(
        Product,
        on_delete=models.CASCADE,
        related_name="stock_balance",
    )

    physical_quantity = models.DecimalField(
        max_digits=14,
        decimal_places=3,
        default=0,
    )

    updated_at = models.DateTimeField(auto_now=True)

    def clean(self):
        super().clean()

        if self.tenant_id and self.product_id:
            if self.tenant_id != self.product.tenant_id:
                raise ValidationError(
                    {
                        "tenant": (
                            "O estoque e o produto devem pertencer " "à mesma empresa."
                        )
                    }
                )

        if self.physical_quantity is not None and self.physical_quantity < 0:
            raise ValidationError(
                {"physical_quantity": "O estoque físico não pode ser negativo."}
            )

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    @property
    def reserved_quantity(self):
        now = timezone.now()

        # Pedidos pendentes só reservam enquanto o prazo estiver válido.
        # Pedidos aprovados, em preparação ou prontos continuam reservando.
        # Pedidos rejeitados, cancelados ou expirados não comprometem estoque.
        reserving_order_statuses = [
            "approved",
            "preparing",
            "ready",
            "completed",
        ]

        total = (
            StockReservation.objects.filter(
                tenant=self.tenant,
                product=self.product,
                status=StockReservation.Status.ACTIVE,
            )
            .filter(
                Q(
                    order__status="pending",
                    expires_at__gt=now,
                )
                | Q(
                    order__status__in=reserving_order_statuses,
                )
            )
            .aggregate(total=models.Sum("quantity"))["total"]
        )

        return total if total is not None else Decimal("0.000")

    @property
    def available_quantity(self):
        physical = Decimal(str(self.physical_quantity))
        reserved = Decimal(str(self.reserved_quantity))

        return physical - reserved


class StockReservation(models.Model):

    class Status(models.TextChoices):
        ACTIVE = "active", "Ativa"
        CONSUMED = "consumed", "Consumida"
        RELEASED = "released", "Liberada"
        EXPIRED = "expired", "Expirada"

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
    )

    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT,
        related_name="reservations",
    )

    order = models.ForeignKey(
        "orders.Order",
        on_delete=models.CASCADE,
        related_name="reservations",
    )

    quantity = models.DecimalField(
        max_digits=14,
        decimal_places=3,
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
    )

    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    def clean(self):
        super().clean()

        errors = {}

        if self.tenant_id and self.product_id:
            if self.tenant_id != self.product.tenant_id:
                errors["product"] = (
                    "O produto deve pertencer à mesma empresa da reserva."
                )

        if self.tenant_id and self.order_id:
            if self.tenant_id != self.order.tenant_id:
                errors["order"] = "O pedido deve pertencer à mesma empresa da reserva."

        if self.quantity is not None and self.quantity <= 0:
            errors["quantity"] = "A quantidade reservada deve ser positiva."

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)


class StockMovement(models.Model):

    class Kind(models.TextChoices):
        IN = "in", "Entrada"
        OUT = "out", "Saída"
        ADJUSTMENT = "adjustment", "Ajuste"

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
    )

    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT,
    )

    kind = models.CharField(
        max_length=20,
        choices=Kind.choices,
    )

    quantity = models.DecimalField(
        max_digits=14,
        decimal_places=3,
    )

    reference = models.CharField(
        max_length=100,
        blank=True,
    )

    note = models.CharField(
        max_length=255,
        blank=True,
    )

    created_at = models.DateTimeField(auto_now_add=True)

    def clean(self):
        super().clean()

        errors = {}

        if self.tenant_id and self.product_id:
            if self.tenant_id != self.product.tenant_id:
                errors["product"] = (
                    "O produto deve pertencer à mesma empresa " "da movimentação."
                )

        if self.quantity is not None and self.quantity <= 0:
            errors["quantity"] = "A quantidade da movimentação deve ser positiva."

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)
