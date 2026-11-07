# Pediu. — pacote consolidado

Este pacote usa `pediu-saas-onboarding-v1` como base funcional porque contém o fluxo de cadastro de usuários e criação de lojas que faltava nas cópias anteriores.

Foram preservados também:
- os arquivos de mídia de produtos encontrados no pacote `pediu-saas(2)`;
- o `.env` e o `.env.test` da cópia `pediu-saas(2)` para desenvolvimento local;
- os arquivos de aplicação, templates, migrações e testes da base de onboarding.

## Atenção antes de iniciar

- O `.env` incluído contém configuração de desenvolvimento local. Não publique esse arquivo nem o envie para repositórios públicos.
- O banco PostgreSQL não está dentro deste ZIP. Os dados permanecem no volume Docker existente; não execute `docker compose down -v`.
- Ao iniciar com um banco existente, aplique as migrações com `python manage.py migrate`. Não apague o volume para recriar o banco.
- O pacote foi consolidado por comparação dos arquivos. Isso não significa que toda a suíte de testes foi executada neste ambiente.
