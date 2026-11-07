from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("orders", "0001_initial")]
    operations = [
        migrations.AddField(
            model_name="order",
            name="fulfillment_method",
            field=models.CharField(
                choices=[("delivery", "Entrega"), ("pickup", "Retirada na loja")],
                default="pickup",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="order",
            name="delivery_address",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="order",
            name="payment_instructions",
            field=models.CharField(
                default="Pagamento combinado diretamente com a loja", max_length=160
            ),
        ),
    ]
