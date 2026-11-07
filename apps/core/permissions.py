"""Permissões centralizadas por papel dentro da empresa ativa.

As views devem usar @login_required antes de @require_roles(...).
"""
from functools import wraps

from django.core.exceptions import PermissionDenied

from apps.core.tenancy import get_active_tenant
from apps.tenants.models import Membership

OWNER = Membership.Role.OWNER
MANAGER = Membership.Role.MANAGER
STAFF = Membership.Role.STAFF


def require_roles(*allowed_roles):
    """Restringe a view aos membros ativos com um dos papéis informados."""
    allowed = {str(role) for role in allowed_roles}

    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if not request.user.is_authenticated:
                # Normalmente tratado por @login_required; mantém defesa em profundidade.
                raise PermissionDenied

            tenant = get_active_tenant(request)
            has_permission = Membership.objects.filter(
                user=request.user,
                tenant=tenant,
                is_active=True,
                role__in=allowed,
            ).exists()

            if not has_permission:
                raise PermissionDenied(
                    "Você não tem permissão para realizar esta operação."
                )

            return view_func(request, *args, **kwargs)

        return _wrapped_view

    return decorator
