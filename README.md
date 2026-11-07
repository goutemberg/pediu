# Pediu — plataforma SaaS de pedidos

Fundação modular multitenant para catálogo público, pedidos com aprovação e estoque. Preserva Pet é a primeira empresa piloto; a arquitetura é multissegmento.

## Incluído
- Django 5.2, DRF, PostgreSQL e Docker Compose.
- Domínios: tenants, accounts, catalog, customers, inventory, orders, notifications, subscriptions e dashboard.
- Pytest, pytest-django, pytest-cov, pytest-xdist, Factory Boy, Ruff e Playwright.
- Serviço Docker de testes opcional, GitHub Actions e testes iniciais de modelos/estoque/isolamento por tenant.
- Documentação técnica e de testes.

## Testes parametrizáveis
O `docker compose up` normal NÃO executa testes. Rode quando quiser:
```bash
make test
# ou docker compose --profile test run --rm tests
```
E2E opcional: `make test-e2e`. Cobertura: `make coverage`.

## Inicialização
```bash
cp .env.example .env
docker compose up --build
```
App: http://localhost:8000 | Admin: `/django-admin/` | Health: `/health/`.
Criar administrador: `docker compose exec web python manage.py createsuperuser`.

## Estado
É uma fundação técnica, não um SaaS pronto para produção. Checkout, reserva atômica, aprovação/rejeição, idempotência, autorização tenant-aware, importação, UI e WhatsApp ainda precisam ser implementados. Os testes incluídos cobrem apenas a base existente.

Consulte `docs/TESTING.md` e `docs/DEVELOPMENT.md`.

## Loja online (MVP)

A vitrine pública fica disponível em `/loja/<slug-da-empresa>/`, sem exigir login do comprador. O fluxo inclui catálogo, carrinho por sessão, checkout, escolha de entrega ou retirada, confirmação pública por identificador UUID e reserva de estoque pelo serviço de pedidos existente.

A gestão de pedidos fica no painel autenticado em `/pedidos/`. A loja pode aprovar/rejeitar pedidos pendentes, iniciar a separação, marcar como pronto, concluir (baixando o estoque) ou cancelar conforme as regras do serviço de pedidos.

Após atualizar o código, execute as migrações:

```bash
sudo docker compose exec web python manage.py migrate
```

Para executar a suíte funcional:

```bash
sudo docker compose --profile test run --rm tests
```

A configuração opcional da vitrine pode ser informada no JSON `Tenant.settings`, preservando as demais chaves existentes:

```json
{
  "storefront": {
    "description": "Rações, acessórios e muito mais.",
    "primary_color": "#635bff"
  }
}
```

O frete e o pagamento são combinados diretamente entre a loja e o cliente; não há cálculo de frete nem processamento financeiro nesta versão.
# pediu
