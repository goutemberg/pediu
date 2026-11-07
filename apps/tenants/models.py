from django.conf import settings
from django.db import models
from django.utils.text import slugify

class Tenant(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Ativa"
        SUSPENDED = "suspended", "Suspensa"
        TRIAL = "trial", "Em teste"
    name = models.CharField(max_length=160)
    slug = models.SlugField(max_length=80, unique=True)
    legal_name = models.CharField(max_length=180, blank=True)
    tax_id = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=30, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.TRIAL)
    settings = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        ordering = ["name"]
    def __str__(self): return self.name

class Membership(models.Model):
    class Role(models.TextChoices):
        OWNER = "owner", "Proprietário"
        MANAGER = "manager", "Gerente"
        STAFF = "staff", "Funcionário"
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="memberships")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="memberships")
    role = models.CharField(max_length=20, choices=Role.choices)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=["tenant", "user"], name="uniq_membership_tenant_user")]
