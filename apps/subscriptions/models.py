from django.db import models
from apps.tenants.models import Tenant

class Plan(models.Model):
    name = models.CharField(max_length=80, unique=True)
    monthly_price = models.DecimalField(max_digits=10, decimal_places=2)
    is_active = models.BooleanField(default=True)
    limits = models.JSONField(default=dict, blank=True)

class Subscription(models.Model):
    class Status(models.TextChoices):
        TRIAL = "trial", "Teste"
        ACTIVE = "active", "Ativa"
        PAST_DUE = "past_due", "Em atraso"
        CANCELLED = "cancelled", "Cancelada"
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="subscriptions")
    plan = models.ForeignKey(Plan, on_delete=models.PROTECT)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.TRIAL)
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField(null=True, blank=True)
    external_reference = models.CharField(max_length=180, blank=True)
