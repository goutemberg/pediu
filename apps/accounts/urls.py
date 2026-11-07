from django.urls import path
from apps.accounts.views import RegistrationView

app_name = "accounts"
urlpatterns = [path("cadastro/", RegistrationView.as_view(), name="register")]
