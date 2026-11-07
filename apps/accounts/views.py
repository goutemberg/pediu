import uuid

from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.contrib.auth.views import LoginView as DjangoLoginView
from django.db import IntegrityError, transaction
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.text import slugify
from django.views import View
from django.utils.decorators import method_decorator
from django_ratelimit.decorators import ratelimit

from apps.accounts.forms import RegistrationForm
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


@method_decorator(ratelimit(key="ip", rate="5/m", method="POST", block=True), name="post")
class RegistrationView(View):
    template_name = "registration/register.html"

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            has_membership = Membership.objects.filter(
                user=request.user,
                is_active=True,
                tenant__status__in=[Tenant.Status.ACTIVE, Tenant.Status.TRIAL],
            ).exists()
            destination = "dashboard:home" if has_membership else "tenants:create"
            return redirect(destination)
        return super().dispatch(request, *args, **kwargs)

    def get(self, request):
        return render(request, self.template_name, {"form": RegistrationForm()})

    def post(self, request):
        form = RegistrationForm(request.POST)
        if not form.is_valid():
            return render(request, self.template_name, {"form": form})

        User = get_user_model()
        data = form.cleaned_data
        try:
            with transaction.atomic():
                username_base = slugify(data["email"].split("@", 1)[0])[:100]
                username_base = username_base or "usuario"
                username = f"{username_base}-{uuid.uuid4().hex[:8]}"
                user = User.objects.create_user(
                    username=username,
                    email=data["email"],
                    password=data["password1"],
                    first_name=data["first_name"].strip(),
                    last_name=data["last_name"].strip(),
                )
                tenant = Tenant.objects.create(
                    name=data["store_name"].strip(),
                    slug=_unique_slug(data["store_name"]),
                    email=data["email"],
                    phone=data["store_phone"].strip(),
                    status=Tenant.Status.TRIAL,
                )
                Membership.objects.create(
                    user=user,
                    tenant=tenant,
                    role=Membership.Role.OWNER,
                    is_active=True,
                )
        except IntegrityError:
            form.add_error(
                None,
                "Não foi possível concluir o cadastro. Verifique os dados e tente novamente.",
            )
            return render(request, self.template_name, {"form": form})

        login(request, user)
        request.session["active_tenant_id"] = tenant.pk
        messages.success(
            request,
            "Sua conta e sua loja foram criadas. Configure seu catálogo!",
        )
        return redirect("dashboard:home")


class EmailLoginView(DjangoLoginView):
    def get_success_url(self):
        has_membership = Membership.objects.filter(
            user=self.request.user,
            is_active=True,
            tenant__status__in=[Tenant.Status.ACTIVE, Tenant.Status.TRIAL],
        ).exists()
        if not has_membership:
            return reverse("tenants:create")
        return self.get_redirect_url() or reverse("dashboard:home")
