from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction
from django.shortcuts import redirect, render
from django.utils.text import slugify
from django.views.decorators.http import require_POST

from apps.tenants.forms import TenantCreateForm
from apps.tenants.models import Membership, Tenant


def _unique_slug(name):
    base = slugify(name)[:70].strip("-") or "loja"
    candidate = base
    suffix = 2
    while Tenant.objects.filter(slug=candidate).exists():
        tail = f"-{suffix}"
        candidate = f"{base[:80 - len(tail)]}{tail}"
        suffix += 1
    return candidate


@login_required
def create_tenant(request):
    if request.method == "POST":
        form = TenantCreateForm(request.POST)
        if form.is_valid():
            data = form.cleaned_data
            try:
                with transaction.atomic():
                    tenant = Tenant.objects.create(
                        name=data["name"],
                        slug=_unique_slug(data["name"]),
                        email=request.user.email,
                        phone=data["phone"].strip(),
                        status=Tenant.Status.TRIAL,
                        settings={"storefront": {"description": data["description"].strip()}},
                    )
                    Membership.objects.create(
                        tenant=tenant, user=request.user,
                        role=Membership.Role.OWNER, is_active=True,
                    )
            except IntegrityError:
                form.add_error(None, "Não foi possível criar a loja. Tente novamente.")
            else:
                request.session["active_tenant_id"] = tenant.pk
                messages.success(request, f"A loja {tenant.name} foi criada com sucesso!")
                return redirect("dashboard:home")
    else:
        form = TenantCreateForm()
    return render(request, "tenants/create.html", {"form": form})


@login_required
@require_POST
def switch_tenant(request):
    try:
        tenant_id = int(request.POST.get("tenant_id"))
    except (TypeError, ValueError):
        messages.error(request, "Empresa inválida.")
        return redirect("dashboard:home")

    membership = Membership.objects.select_related("tenant").filter(
        user=request.user, tenant_id=tenant_id, is_active=True,
        tenant__status__in=[Tenant.Status.ACTIVE, Tenant.Status.TRIAL],
    ).first()
    if not membership:
        messages.error(request, "Você não possui acesso ativo a essa empresa.")
        return redirect("dashboard:home")

    request.session["active_tenant_id"] = membership.tenant_id
    messages.success(request, f"Você agora está acessando {membership.tenant.name}.")
    return redirect("dashboard:home")
