from django.contrib.auth.models import AbstractUser
from django.db import models

class User(AbstractUser):
    """Conta global. A autorização em cada empresa é definida por Membership."""
    email = models.EmailField(unique=True)
    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["username"]
