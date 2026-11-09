from django.urls import path
from apps.tenants import views

app_name = "tenants"
urlpatterns = [
    path("nova/", views.create_tenant, name="create"),
    path("trocar-empresa/", views.switch_tenant, name="switch"),
    path("configuracoes/", views.order_settings, name="order-settings"),
]
