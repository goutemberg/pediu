# Desempenho do catálogo público

## O que foi otimizado

- A disponibilidade de estoque é calculada por lote: saldos físicos são consultados para os produtos da página e reservas ativas são agregadas por produto em uma única consulta.
- A listagem pública é paginada em 24 produtos por página. O botão **Carregar mais produtos** busca os próximos itens por AJAX.
- A troca de categorias substitui somente o grid, controla requisições concorrentes e mantém um cache em memória de 15 segundos para respostas recentes. A resposta da rede atualiza o conteúdo em cache.
- O carrinho deixa de calcular disponibilidade de estoque que não é exibida naquela tela. A validação efetiva de estoque no fluxo de pedido permanece nos serviços de pedidos/estoque.
- O retorno do carrinho preserva a última categoria e pesquisa visitadas. Quando o navegador ainda tem a loja anterior no histórico, o botão usa o histórico para permitir restauração rápida da página.
- Imagens de produtos ganham miniaturas WebP de até 600 x 600, qualidade 80, mantendo o original intacto. Novas imagens geram miniatura ao salvar o produto.

## Gerar miniaturas para imagens já existentes

Depois de publicar o código, execute uma vez:

```bash
python manage.py generate_product_thumbnails
```

Execute novamente depois de uma importação em massa feita por scripts que gravem imagens sem chamar `Product.save()`.

## Armazenamento persistente em produção

O projeto continua usando armazenamento local quando `AWS_STORAGE_BUCKET_NAME` não está configurado. Em plataformas com disco efêmero, configure um bucket S3 ou compatível e as variáveis:

```env
AWS_STORAGE_BUCKET_NAME=nome-do-bucket
AWS_S3_REGION_NAME=us-east-1
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
# Opcional para S3 compatível:
AWS_S3_ENDPOINT_URL=
AWS_S3_CUSTOM_DOMAIN=
```

A dependência `django-storages[s3]` foi adicionada. O bucket deve permitir leitura pública dos objetos de mídia ou ser servido por um domínio/CDN público. Não coloque as credenciais no repositório.

## Observações

- O cache de HTML das categorias dura apenas 15 segundos; preços e disponibilidade são atualizados pela requisição de revalidação.
- A primeira página carrega até 24 cards. A paginação é aplicada depois dos filtros de pesquisa e categoria.
- O processamento WebP acontece no salvamento do produto, não durante a renderização do catálogo.
- A configuração de bucket é opcional e depende de credenciais e bucket criados no provedor escolhido. Sem essa configuração, o armazenamento local não é persistente em ambientes efêmeros.
