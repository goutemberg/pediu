from .base import *
DEBUG = False
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
SECURE_REFERRER_POLICY = "same-origin"

# Proteções adicionais para HTTPS em produção. HSTS só deve ser habilitado
# depois de confirmar HTTPS funcional em todo o domínio.
SECURE_SSL_REDIRECT = True
SECURE_HSTS_SECONDS = int(env("SECURE_HSTS_SECONDS", default=0))
SECURE_HSTS_INCLUDE_SUBDOMAINS = env.bool("SECURE_HSTS_INCLUDE_SUBDOMAINS", default=False)
SECURE_HSTS_PRELOAD = env.bool("SECURE_HSTS_PRELOAD", default=False)
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"

# Não aceitar hosts genéricos em produção. Defina ALLOWED_HOSTS no ambiente.
if not ALLOWED_HOSTS or ALLOWED_HOSTS == ["localhost", "127.0.0.1"]:
    raise RuntimeError("Configure ALLOWED_HOSTS com os domínios reais em produção.")

if SECRET_KEY == "unsafe-dev-key-change-me":
    raise RuntimeError("Defina SECRET_KEY forte e exclusiva no ambiente de produção.")
