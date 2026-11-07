from django.core.exceptions import PermissionDenied

from apps.tenants.models import Membership


def get_active_tenant(request):
    """
    Retorna a última empresa selecionada pelo usuário.
    Caso não exista uma seleção válida, utiliza a primeira
    empresa disponível.
    """

    memberships = Membership.objects.select_related("tenant").filter(
        user=request.user,
        is_active=True,
        tenant__status__in=["active", "trial"],
    )

    selected_tenant_id = request.session.get("active_tenant_id")

    if selected_tenant_id:
        membership = memberships.filter(tenant_id=selected_tenant_id).first()

        if membership:
            return membership.tenant

    membership = memberships.order_by("created_at").first()

    if not membership:
        raise PermissionDenied("Você não possui acesso a nenhuma empresa disponível.")

    request.session["active_tenant_id"] = membership.tenant_id

    return membership.tenant
