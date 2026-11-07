import uuid
from django.db import models
from apps.tenants.models import Tenant
from apps.customers.models import Customer
from apps.catalog.models import Product

class Order(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Aguardando aprovação"
        APPROVED = "approved", "Aprovado"
        PREPARING = "preparing", "Em separação"
        READY = "ready", "Pronto"
        COMPLETED = "completed", "Concluído"
        REJECTED = "rejected", "Rejeitado"
        CANCELLED = "cancelled", "Cancelado"
        EXPIRED = "expired", "Expirado"
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="orders")
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="orders")
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    number = models.CharField(max_length=30)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    customer_name_snapshot = models.CharField(max_length=160)
    customer_phone_snapshot = models.CharField(max_length=30)
    subtotal = models.DecimalField(max_digits=12, decimal_places=2)
    total = models.DecimalField(max_digits=12, decimal_places=2)
    notes = models.TextField(blank=True)
    class Fulfillment(models.TextChoices):
        DELIVERY = "delivery", "Entrega"
        PICKUP = "pickup", "Retirada na loja"
    fulfillment_method = models.CharField(
        max_length=20, choices=Fulfillment.choices, default=Fulfillment.PICKUP
    )
    delivery_address = models.TextField(blank=True)
    payment_instructions = models.CharField(
        max_length=160, default="Pagamento combinado diretamente com a loja"
    )
    idempotency_key = models.UUIDField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=["tenant", "number"], name="uniq_order_number_per_tenant")]
        indexes = [models.Index(fields=["tenant", "status", "created_at"])]

class OrderItem(models.Model):
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT)
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    product_code_snapshot = models.CharField(max_length=50)
    product_name_snapshot = models.CharField(max_length=180)
    unit_snapshot = models.CharField(max_length=30)
    quantity = models.DecimalField(max_digits=14, decimal_places=3)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    line_total = models.DecimalField(max_digits=12, decimal_places=2)
