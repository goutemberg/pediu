from decimal import Decimal

from django import forms
from django.utils.text import slugify
from PIL import Image, UnidentifiedImageError

from apps.catalog.models import Category, Product


class ProductForm(forms.ModelForm):
    MAX_IMAGE_SIZE = 5 * 1024 * 1024  # 5 MB
    MAX_IMAGE_DIMENSION = 4000
    ALLOWED_IMAGE_FORMATS = {"JPEG", "PNG", "WEBP"}

    CODE_MODE_CHOICES = [
        ("auto", "Gerar código automaticamente"),
        ("manual", "Informar código manualmente"),
    ]

    code_mode = forms.ChoiceField(
        label="Como deseja definir o código?",
        choices=CODE_MODE_CHOICES,
        initial="auto",
        required=True,
        widget=forms.RadioSelect,
    )

    manual_code = forms.CharField(
        label="Código do produto",
        required=False,
        max_length=50,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Ex.: PROD-001",
                "maxlength": "50",
            }
        ),
        help_text="Informe um código único para este produto.",
    )

    initial_stock = forms.DecimalField(
        label="Estoque inicial",
        required=False,
        initial=Decimal("0.000"),
        min_value=Decimal("0"),
        max_digits=14,
        decimal_places=3,
        widget=forms.NumberInput(
            attrs={
                "class": "form-control",
                "step": "0.001",
                "min": "0",
                "placeholder": "Ex.: 10",
            }
        ),
    )

    class Meta:
        model = Product
        # O código é tratado separadamente para permitir geração automática.
        fields = [
            "name",
            "category",
            "description",
            "price",
            "unit",
            "minimum_quantity",
            "quantity_multiple",
            "image",
            "is_active",
        ]

        widgets = {
            "name": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Nome do produto",
                }
            ),
            "category": forms.Select(attrs={"class": "form-control"}),
            "description": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 4,
                    "placeholder": "Descrição ou informações adicionais",
                }
            ),
            "price": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "step": "0.01",
                    "min": "0",
                    "placeholder": "0,00",
                }
            ),
            "unit": forms.Select(attrs={"class": "form-control"}),
            "minimum_quantity": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "step": "0.001",
                    "min": "0.001",
                    "placeholder": "Ex.: 0,500",
                }
            ),
            "quantity_multiple": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "step": "0.001",
                    "min": "0.001",
                    "placeholder": "Ex.: 0,250",
                }
            ),
            "image": forms.ClearableFileInput(
                attrs={
                    "class": "form-control",
                    "accept": ".jpg,.jpeg,.png,.webp",
                }
            ),
            "is_active": forms.CheckboxInput(attrs={"class": "form-checkbox"}),
        }

        labels = {
            "name": "Nome do produto",
            "category": "Categoria",
            "description": "Descrição",
            "price": "Preço de venda",
            "unit": "Unidade de venda",
            "minimum_quantity": "Quantidade mínima por pedido",
            "quantity_multiple": "Múltiplo de quantidade",
            "image": "Imagem do produto",
            "is_active": "Produto ativo",
        }

        help_texts = {
            "unit": "Selecione como este produto será vendido.",
            "minimum_quantity": (
                "Menor quantidade que o cliente poderá solicitar. " "Ex.: 0,500 kg."
            ),
            "quantity_multiple": (
                "Define os intervalos permitidos para compra. "
                "Ex.: 0,250 permite 0,250, 0,500, 0,750..."
            ),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)

        self.tenant = tenant

        if tenant:
            self.fields["category"].queryset = Category.objects.filter(
                tenant=tenant,
                is_active=True,
            ).order_by("name")
        else:
            self.fields["category"].queryset = Category.objects.none()

        self.fields["category"].required = True
        self.fields["description"].required = False
        self.fields["image"].required = False
        self.fields["initial_stock"].required = False

        self.fields["minimum_quantity"].min_value = Decimal("0.001")
        self.fields["minimum_quantity"].max_digits = 14
        self.fields["minimum_quantity"].decimal_places = 3

        self.fields["quantity_multiple"].min_value = Decimal("0.001")
        self.fields["quantity_multiple"].max_digits = 14
        self.fields["quantity_multiple"].decimal_places = 3

        # Na edição, o código existente é preservado e não pode ser alterado.
        if self.instance and self.instance.pk:
            self.fields.pop("code_mode")
            self.fields.pop("manual_code")
            self.fields["current_code"] = forms.CharField(
                label="Código do produto",
                initial=self.instance.code,
                required=False,
                disabled=True,
                widget=forms.TextInput(attrs={"class": "form-control"}),
                help_text="O código não pode ser alterado após o cadastro.",
            )

    def clean_manual_code(self):
        code = self.cleaned_data.get("manual_code", "").strip()

        if self.instance and self.instance.pk:
            return code

        mode = self.cleaned_data.get("code_mode", "auto")

        if mode == "auto":
            return ""

        if not code:
            raise forms.ValidationError(
                "Informe o código do produto ou escolha a geração automática."
            )

        if not self.tenant:
            raise forms.ValidationError("Não foi possível identificar sua empresa.")

        duplicate = Product.objects.filter(
            tenant=self.tenant,
            code__iexact=code,
        )

        if duplicate.exists():
            raise forms.ValidationError(
                "Já existe um produto com esse código na sua empresa."
            )

        # Padroniza os códigos manuais em letras maiúsculas.
        return code.upper()

    def clean_category(self):
        category = self.cleaned_data.get("category")

        if not category:
            raise forms.ValidationError("Selecione uma categoria para o produto.")

        if not self.tenant:
            raise forms.ValidationError("Não foi possível identificar sua empresa.")

        if category.tenant_id != self.tenant.id:
            raise forms.ValidationError(
                "A categoria selecionada não pertence à sua empresa."
            )

        if not category.is_active:
            raise forms.ValidationError("A categoria selecionada está inativa.")

        return category

    def clean_minimum_quantity(self):
        quantity = self.cleaned_data.get("minimum_quantity")

        if quantity is None or quantity <= Decimal("0"):
            raise forms.ValidationError("A quantidade mínima deve ser maior que zero.")

        return quantity

    def clean_quantity_multiple(self):
        multiple = self.cleaned_data.get("quantity_multiple")

        if multiple is None or multiple <= Decimal("0"):
            raise forms.ValidationError(
                "O múltiplo de quantidade deve ser maior que zero."
            )

        return multiple

    def clean_image(self):
        uploaded_image = self.cleaned_data.get("image")

        if not uploaded_image:
            return uploaded_image

        if getattr(uploaded_image, "_committed", False):
            return uploaded_image

        if uploaded_image.size > self.MAX_IMAGE_SIZE:
            raise forms.ValidationError("A imagem não pode ultrapassar 5 MB.")

        try:
            uploaded_image.seek(0)

            with Image.open(uploaded_image) as image:
                if image.format not in self.ALLOWED_IMAGE_FORMATS:
                    raise forms.ValidationError(
                        "Formato inválido. Envie uma imagem JPG, PNG ou WebP."
                    )

                width, height = image.size

                if (
                    width > self.MAX_IMAGE_DIMENSION
                    or height > self.MAX_IMAGE_DIMENSION
                ):
                    raise forms.ValidationError(
                        "A imagem não pode ultrapassar 4000 pixels "
                        "de largura ou altura."
                    )

                image.verify()

            uploaded_image.seek(0)

            with Image.open(uploaded_image) as image:
                image.load()

            uploaded_image.seek(0)

        except forms.ValidationError:
            raise

        except (
            UnidentifiedImageError,
            OSError,
            ValueError,
            Image.DecompressionBombError,
        ):
            raise forms.ValidationError(
                "O arquivo enviado não é uma imagem válida ou está corrompido."
            )

        finally:
            uploaded_image.seek(0)

        return uploaded_image

    def clean_initial_stock(self):
        return self.cleaned_data.get("initial_stock") or Decimal("0.000")

    def save(self, commit=True):
        product = super().save(commit=False)

        # Código manual: atribui o código informado pelo usuário.
        # Código automático: será atribuído pela view/service antes do save.
        if not (self.instance and self.instance.pk):
            if self.cleaned_data.get("code_mode") == "manual":
                product.code = self.cleaned_data["manual_code"]

        if commit:
            product.save()
            self.save_m2m()

        return product


class CategoryForm(forms.ModelForm):

    class Meta:
        model = Category
        fields = ["name", "is_active"]

        widgets = {
            "name": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Ex.: Alimentos, Bebidas, Limpeza...",
                    "maxlength": "100",
                }
            ),
            "is_active": forms.CheckboxInput(attrs={"class": "form-checkbox"}),
        }

        labels = {
            "name": "Nome da categoria",
            "is_active": "Categoria ativa",
        }

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.tenant = tenant

    def clean_name(self):
        name = self.cleaned_data["name"].strip()

        if not self.tenant:
            raise forms.ValidationError("Não foi possível identificar sua empresa.")

        duplicate = Category.objects.filter(
            tenant=self.tenant,
            name__iexact=name,
        )

        if self.instance.pk:
            duplicate = duplicate.exclude(pk=self.instance.pk)

        if duplicate.exists():
            raise forms.ValidationError("Já existe uma categoria com esse nome.")

        generated_slug = slugify(name)

        if not generated_slug:
            raise forms.ValidationError("Informe um nome válido para a categoria.")

        slug_conflict = Category.objects.filter(
            tenant=self.tenant,
            slug=generated_slug,
        )

        if self.instance.pk:
            slug_conflict = slug_conflict.exclude(pk=self.instance.pk)

        if slug_conflict.exists():
            raise forms.ValidationError(
                "Já existe uma categoria com um nome semelhante."
            )

        return name

    def save(self, commit=True):
        category = super().save(commit=False)
        category.tenant = self.tenant
        category.slug = slugify(self.cleaned_data["name"])

        if commit:
            category.save()

        return category
