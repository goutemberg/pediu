from django import forms


class TenantCreateForm(forms.Form):
    name = forms.CharField(label="Nome da loja", max_length=160, widget=forms.TextInput(attrs={"class": "form-control"}))
    phone = forms.CharField(label="WhatsApp da loja", max_length=30, required=False, widget=forms.TextInput(attrs={"class": "form-control"}))
    description = forms.CharField(label="Descrição", required=False, max_length=500,
                                  widget=forms.Textarea(attrs={"rows": 3, "class": "form-control"}))

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        if not name:
            raise forms.ValidationError("Informe o nome da loja.")
        return name
