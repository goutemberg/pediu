from django.db import models
from apps.tenants.models import Tenant

class NotificationLog(models.Model):
    class Channel(models.TextChoices):
        IN_APP = "in_app", "Painel"
        WHATSAPP = "whatsapp", "WhatsApp"
        EMAIL = "email", "E-mail"
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    channel = models.CharField(max_length=20, choices=Channel.choices)
    event = models.CharField(max_length=80)
    recipient = models.CharField(max_length=180, blank=True)
    status = models.CharField(max_length=30, default="queued")
    provider_reference = models.CharField(max_length=180, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
