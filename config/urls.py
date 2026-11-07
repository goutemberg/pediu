from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path
from django_ratelimit.decorators import ratelimit

from apps.core.views import health_check
from apps.accounts.views import EmailLoginView

urlpatterns = [
    path("health/", health_check, name="health-check"),
    path("django-admin/", admin.site.urls),
    path(
        "login/",
        ratelimit(key="ip", rate="10/m", method="POST", block=True)(
            EmailLoginView.as_view(template_name="registration/login.html")
        ),
        name="login",
    ),
    path(
        "logout/",
        auth_views.LogoutView.as_view(),
        name="logout",
    ),
    path("", include("apps.accounts.urls")),
    path("produtos/", include("apps.catalog.urls")),
    path("", include("apps.storefront.urls")),
    path("", include("apps.dashboard.urls")),
    path("api/v1/", include("apps.core.api_urls")),
    path("empresas/", include("apps.tenants.urls")),
]

if settings.DEBUG:
    urlpatterns += static(
        settings.MEDIA_URL,
        document_root=settings.MEDIA_ROOT,
    )
