from django.urls import path

from . import views

app_name = "customers"

urlpatterns = [
    path("clientes/", views.customer_list, name="customer-list"),
    path("clientes/novo/", views.customer_create, name="customer-create"),
    path("clientes/<int:customer_id>/", views.customer_detail, name="customer-detail"),
    path("clientes/<int:customer_id>/editar/", views.customer_update, name="customer-update"),
]
