from apps.tenants.models import Membership


def available_tenants(request):
    if not request.user.is_authenticated:
        return {"available_tenant_memberships": []}

    memberships = (
        Membership.objects.select_related("tenant")
        .filter(
            user=request.user,
            is_active=True,
            tenant__status__in=["active", "trial"],
        )
        .order_by("tenant__name")
    )

    return {"available_tenant_memberships": memberships}
