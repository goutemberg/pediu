# Carga demonstrativa — Catálogo Preserva Pet

Este pacote adiciona uma carga inicial de **22 produtos**, distribuídos em categorias, com imagens recortadas do catálogo PDF enviado.

## Conteúdo

- `apps/catalog/management/commands/importar_catalogo_preserva_pet.py`: comando Django.
- `seed_data/preserva_pet/images/`: imagens dos produtos extraídas das páginas do catálogo.

## Instalação

Copie as pastas `apps/` e `seed_data/` para a raiz do projeto Django `pediu-saas`, mesclando a pasta `apps/catalog/management/commands/` com a existente. Não substitua os demais arquivos do projeto.

## Execução

Na raiz do projeto, execute:

```bash
docker compose exec web python manage.py importar_catalogo_preserva_pet --tenant-slug SEU-SLUG
```

Substitua `SEU-SLUG` pelo slug da loja que receberá os produtos. O slug é o identificador que aparece no link público da loja.

Por padrão, o comando cadastra estoque inicial de 10 unidades/embalagens por produto. Para escolher outro valor:

```bash
docker compose exec web python manage.py importar_catalogo_preserva_pet --tenant-slug SEU-SLUG --estoque-inicial 5
```

## Segurança e repetição

- O comando atua somente na loja informada por `--tenant-slug`.
- Os códigos do catálogo são usados como códigos dos produtos.
- Produtos existentes com o mesmo código na mesma loja são atualizados, não duplicados.
- Categorias são criadas apenas quando ainda não existem.
- Estoques já existentes são preservados; o estoque inicial só é aplicado quando o saldo ainda não existe.
- A carga cria movimentação de entrada para os saldos iniciais positivos.
- Não apaga produtos, imagens, pedidos ou registros existentes.

## Observações sobre o catálogo

Os nomes, códigos e preços foram transcritos do catálogo Preserva Pet. Quando o catálogo lista uma embalagem como 5 kg ou 500 g, a embalagem é tratada como uma unidade comercial (`UN`) e o peso é informado na descrição. O preço é o valor exibido no catálogo, não foi recalculado.

As imagens são recortes das fotografias/figuras do PDF; por isso, a qualidade pode variar conforme a resolução original do catálogo. Alguns produtos são vendidos em pacotes ou caixas: a condição de embalagem foi preservada na descrição.
