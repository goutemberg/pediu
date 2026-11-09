# Migração das imagens PRESERVA PET no Render

A migração roda na inicialização do container, sem acesso ao Shell.

## Configuração
1. Faça deploy desta versão.
2. No Render, defina `RUN_PRESERVA_PET_IMAGE_IMPORT=true`.
3. Mantenha `CLOUDINARY_CLOUD_NAME`, `CLOUDINARY_API_KEY` e `CLOUDINARY_API_SECRET` configuradas.
4. O próximo início executará `migrar_imagens_preserva_pet --once` antes do Gunicorn.

## Comportamento
- Lê `seed_data/preserva_pet/PRODUCTS.json`.
- Usa as imagens em `carga-ampliada-preserva-pet-pediu/seed_data/preserva_pet/images/`.
- Envia imagens ao Cloudinary.
- Preenche imagens vazias e reenvia referências antigas cujo nome corresponda ao arquivo do catálogo.
- Preserva fotos personalizadas com nomes diferentes.
- Não cria nem atualiza produtos, categorias, estoques ou pedidos.
- Registra a conclusão em `Tenant.settings.catalog_imports.preserva_pet_images_346_v1`.
- Só grava a trava após todos os envios terminarem. Em caso de falha, uma nova inicialização pode tentar novamente.

## Após a execução
Confira os logs do deploy. Quando aparecer `Migração das imagens PRESERVA PET concluída`, altere `RUN_PRESERVA_PET_IMAGE_IMPORT` para `false`. A trava no banco impede repetição mesmo se a variável permanecer `true`.

A loja `preserva-pet` e os produtos correspondentes precisam existir no banco. Se o catálogo ainda não foi importado, configure também `RUN_PRESERVA_PET_IMPORT=true`: a inicialização executa primeiro a importação do catálogo e depois as imagens.
