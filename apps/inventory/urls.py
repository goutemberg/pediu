from django.urls import path

from . import views

app_name = "inventory"

urlpatterns = [
    path("", views.stock_list, name="stock-list"),
    path("configuracoes/", views.stock_settings, name="stock-settings"),
    path("<int:product_id>/movimentar/", views.stock_adjust, name="stock-adjust"),
    path("movimentacoes/", views.stock_movements, name="stock-movements"),
    path("<int:product_id>/movimentacoes/", views.stock_movements, name="product-movements"),
]
