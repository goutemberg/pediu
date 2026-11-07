# Carga ampliada — PRESERVA PET (pediu.)

Catálogo extraído do PDF PRESERVA PET de 17 páginas.

- Produtos extraídos: 346
- Categorias sugeridas: 5
- Imagens recortadas do catálogo: 346
- Destino previsto: loja `preserva-pet` (slug confirmado pelo usuário)

## Conteúdo

- `PRODUCTS.json`: produtos, códigos, preços, unidade comercial, categoria sugerida e página de origem.
- `apps/catalog/management/commands/importar_catalogo_preserva_pet.py`: comando Django de importação, com modo de simulação.
- `seed_data/preserva_pet/images/`: recortes de imagens do catálogo para os produtos que têm foto identificável.
- `docs/REVISAO_CATALOGO.md`: observações de conferência.

## Instalação no repositório

Extraia o ZIP na raiz do projeto Django e mescle as pastas `apps/` e `seed_data/`. Não substitua `apps/catalog/models.py`, migrations, settings, Dockerfile ou qualquer arquivo existente.

## Primeiro: simular sem gravar

```bash
python manage.py importar_catalogo_preserva_pet --tenant-slug preserva-pet --dry-run
```

Em produção, abra o Shell do serviço Web no Render e execute o mesmo comando de simulação. Confirme loja, contagem e imagens antes de importar.

## Importar em produção

```bash
python manage.py importar_catalogo_preserva_pet --tenant-slug preserva-pet
```

Depois de configurar armazenamento persistente de mídia, para importar também as fotos:

```bash
python manage.py importar_catalogo_preserva_pet --tenant-slug preserva-pet --incluir-imagens
```

Por segurança, o estoque inicial padrão é **zero**. Não informe estoque fictício. Se houver inventário real conferido, pode informar `--estoque-inicial 5`, por exemplo.

As imagens ficam desativadas por padrão. O Render em disco efêmero pode perder arquivos de mídia após reinicialização ou novo deploy. Configure primeiro armazenamento persistente (S3/Cloudinary ou disco persistente compatível) e então execute com `--incluir-imagens`.

## Reexecução segura

- Atua somente no tenant indicado por `--tenant-slug`.
- Produtos com mesmo código na loja são atualizados, não duplicados.
- Produtos existentes com estoque não têm saldo alterado.
- Imagens já cadastradas não são substituídas.
- Não apaga pedidos, produtos, categorias ou movimentos.
- Toda a gravação é transacional.

## Conferência necessária

Os códigos, nomes e preços foram extraídos do PDF. Categorias foram sugeridas automaticamente pelo tipo de produto e devem ser revisadas no painel. O PDF contém alguns códigos com formatos semelhantes e uma repetição aparente; o pacote torna os códigos repetidos distintos com sufixo para evitar sobrescrita. Verifique esses casos antes da carga definitiva.
