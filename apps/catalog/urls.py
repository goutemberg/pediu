from django.urls import path

from apps.catalog import views

app_name = "catalog"

urlpatterns = [
    # Produtos
    path("", views.product_list, name="product-list"),
    path("novo/", views.product_create, name="product-create"),
    path(
        "<int:product_id>/editar/",
        views.product_update,
        name="product-update",
    ),
    path(
        "<int:product_id>/alternar-status/",
        views.product_toggle_status,
        name="product-toggle-status",
    ),
    # Categorias
    path(
        "categorias/",
        views.category_list,
        name="category-list",
    ),
    path(
        "categorias/nova/",
        views.category_create,
        name="category-create",
    ),
    path(
        "categorias/<int:category_id>/editar/",
        views.category_update,
        name="category-update",
    ),
    path(
        "categorias/<int:category_id>/alternar-status/",
        views.category_toggle_status,
        name="category-toggle-status",
    ),
]
