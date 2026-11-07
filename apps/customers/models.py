from django.db import models
from apps.tenants.models import Tenant

class Customer(models.Model):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="customers")
    name = models.CharField(max_length=160)
    phone = models.CharField(max_length=30)
    email = models.EmailField(blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        indexes = [models.Index(fields=["tenant", "phone"])]
        constraints = [models.UniqueConstraint(fields=["tenant", "phone"], name="uniq_customer_phone_per_tenant")]
    def __str__(self): return f"{self.name} ({self.phone})"
