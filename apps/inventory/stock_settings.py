from decimal import Decimal, InvalidOperation

DEFAULT_MINIMUM_STOCK = Decimal("5.000")
SETTING_KEY = "inventory_minimum_stock"


def get_minimum_stock(tenant):
    """Retorna o estoque mínimo padrão configurado para a empresa."""
    settings = tenant.settings if isinstance(tenant.settings, dict) else {}
    value = settings.get(SETTING_KEY, str(DEFAULT_MINIMUM_STOCK))
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return DEFAULT_MINIMUM_STOCK
    if not result.is_finite() or result < 0:
        return DEFAULT_MINIMUM_STOCK
    return result.quantize(Decimal("0.001"))


def set_minimum_stock(tenant, value):
    """Valida e persiste o limite padrão sem sobrescrever outras configurações."""
    try:
        result = Decimal(str(value).replace(",", "."))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError("Informe um estoque mínimo válido.")

    if not result.is_finite() or result < 0:
        raise ValueError("O estoque mínimo não pode ser negativo.")
    if result != result.quantize(Decimal("0.001")):
        raise ValueError("Utilize no máximo três casas decimais.")

    settings = dict(tenant.settings) if isinstance(tenant.settings, dict) else {}
    settings[SETTING_KEY] = format(result, ".3f")
    tenant.settings = settings
    tenant.save(update_fields=["settings", "updated_at"])
    return result
