from django.urls import path
from . import views

app_name = "storefront"

urlpatterns = [
    path("loja/<slug:slug>/", views.store, name="store"),
    path("loja/<slug:slug>/carrinho/", views.cart, name="cart"),
    path("loja/<slug:slug>/carrinho/adicionar/", views.cart_add, name="cart-add"),
    path("loja/<slug:slug>/carrinho/remover/", views.cart_remove, name="cart-remove"),
    path("loja/<slug:slug>/carrinho/atualizar/", views.cart_update, name="cart-update"),
    path("loja/<slug:slug>/checkout/", views.checkout, name="checkout"),
    path(
        "loja/<slug:slug>/pedido/<uuid:public_id>/",
        views.order_confirmation,
        name="order-confirmation",
    ),
    path(
        "loja/<slug:slug>/pedido/<uuid:public_id>/status/",
        views.order_status,
        name="order-status",
    ),
    path(
        "loja/<slug:slug>/pedido/<uuid:public_id>/acompanhar/",
        views.order_tracking,
        name="order-tracking",
    ),
    path("pedidos/", views.merchant_orders, name="merchant-orders"),
    path(
        "pedidos/<int:order_id>/",
        views.merchant_order_detail,
        name="merchant-order-detail",
    ),
]
