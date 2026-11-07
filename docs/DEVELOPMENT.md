# Desenvolvimento local

```bash
cp .env.example .env
docker compose up --build
```
Aplicação: `http://localhost:8000`; admin: `/django-admin/`; health: `/health/`.

Os testes NÃO rodam ao iniciar o ambiente:
```bash
make test
make coverage
make check
```

Criar administrador:
```bash
docker compose exec web python manage.py createsuperuser
```

O serviço web gera migrações locais e aplica migrações no boot para facilitar o protótipo. Antes de trabalho em equipe, gere, revise e versione migrações. Em produção, nunca gere migrações no startup: aplique apenas migrações versionadas.
