# Estratégia de testes

## Execução sob demanda
A suíte não roda no `docker compose up` padrão. `tests` e `e2e` usam profiles opt-in:
```bash
make test
make test-unit
make test-integration
make test-api
make coverage
make lint
make check
make test-e2e
```
Ou:
```bash
docker compose --profile test run --rm tests
docker compose --profile test run --rm tests pytest apps/orders/tests.py -q
docker compose --profile test run --rm tests pytest --cov=apps --cov-report=html
```

## Tipos
- `unit`: regra isolada.
- `integration`: integração com ORM/serviços.
- `api`: endpoints e contratos.
- `e2e`: jornadas no navegador.
- `slow`: cenários demorados.

## Banco
O Docker aponta para PostgreSQL. Transações, constraints, `select_for_update` e concorrência devem ser testados em PostgreSQL; SQLite não substitui esses cenários.

## CI e cobertura
GitHub Actions executa Ruff, migrações e pytest em push e pull request. Configure proteção da branch para exigir o job `tests`.
Cobertura é indicador, não garantia. Metas iniciais: 95% em serviços críticos de pedido/estoque, 90% em regras de negócio e 85% global. Não imponha limite rígido antes de consolidar a suíte.
