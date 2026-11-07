# Importação automática da PRESERVA PET no deploy

Este pacote integra a carga de 346 produtos ao deploy do Render, sem necessidade de Shell.

## Comportamento

- A execução só ocorre quando `RUN_PRESERVA_PET_IMPORT=true`.
- O destino é fixo e validado: `preserva-pet`.
- A carga registra um marcador em `Tenant.settings` (`preserva_pet_catalog_346_v1`).
- Depois de concluída, novas inicializações não repetem a carga, mesmo se a variável continuar `true`.
- A gravação de produtos, categorias, estoques novos e marcador é transacional.
- Produtos com o mesmo código na loja são atualizados; não são duplicados.
- Estoques existentes são preservados; novos produtos recebem saldo zero.
- Imagens não são anexadas nesta etapa porque o serviço Render ainda não tem armazenamento de mídia persistente configurado.

## Arquivos integrados

- `seed_data/preserva_pet/PRODUCTS.json`
- `apps/catalog/management/commands/importar_catalogo_preserva_pet.py`
- `Dockerfile` com execução condicional antes do Gunicorn.

## Como fazer o deploy da carga

1. Faça commit e push do projeto para o GitHub.
2. No Render, adicione a variável `RUN_PRESERVA_PET_IMPORT` com valor `true`.
3. Faça um deploy manual ou aguarde o deploy automático.
4. Nos logs, procure `Importação PRESERVA PET concluída` e confira a contagem.
5. Depois de confirmar o sucesso, altere `RUN_PRESERVA_PET_IMPORT` para `false`. Essa alteração gera um novo deploy, mas a trava no banco impede qualquer repetição mesmo se esquecer de desativar a variável.

## Importante

- Não execute essa carga em um banco diferente do ambiente de produção pretendido.
- Não altere o slug `preserva-pet` sem revisar o comando.
- Faça backup do PostgreSQL antes da importação.
- Os nomes, códigos e preços vieram do catálogo e devem ser conferidos comercialmente.
- Esta etapa não importa as 346 imagens. A mídia precisa de armazenamento persistente/externo e configuração de serving em produção antes de anexar imagens.
