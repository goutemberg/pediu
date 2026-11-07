from django import forms
from django.contrib.auth import get_user_model, password_validation

TEXT = {"class": "form-control"}
PASSWORD = {"class": "form-control", "autocomplete": "new-password"}

User = get_user_model()


class RegistrationForm(forms.Form):
    first_name = forms.CharField(label="Nome", max_length=150, widget=forms.TextInput(attrs={**TEXT, "autocomplete": "given-name"}))
    last_name = forms.CharField(label="Sobrenome", max_length=150, required=False, widget=forms.TextInput(attrs={**TEXT, "autocomplete": "family-name"}))
    email = forms.EmailField(label="E-mail", widget=forms.EmailInput(attrs={**TEXT, "autocomplete": "email"}))
    password1 = forms.CharField(label="Senha", strip=False, widget=forms.PasswordInput(attrs=PASSWORD))
    password2 = forms.CharField(label="Confirmar senha", strip=False, widget=forms.PasswordInput(attrs=PASSWORD))
    store_name = forms.CharField(label="Nome da loja", max_length=160, widget=forms.TextInput(attrs={**TEXT, "placeholder": "Ex.: Loja de Ração"}))
    store_phone = forms.CharField(label="WhatsApp da loja", max_length=30, required=False, widget=forms.TextInput(attrs={**TEXT, "autocomplete": "tel"}))

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("Já existe uma conta cadastrada com este e-mail.")
        return email

    def clean(self):
        cleaned = super().clean()
        password1 = cleaned.get("password1")
        password2 = cleaned.get("password2")
        if password1 and password2 and password1 != password2:
            self.add_error("password2", "As senhas não conferem.")
        if password1:
            candidate = User(
                email=cleaned.get("email", ""),
                first_name=cleaned.get("first_name", ""),
                last_name=cleaned.get("last_name", ""),
            )
            try:
                password_validation.validate_password(password1, user=candidate)
            except forms.ValidationError as exc:
                self.add_error("password1", exc)
        return cleaned
