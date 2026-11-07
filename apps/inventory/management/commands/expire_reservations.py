from django.core.management.base import BaseCommand, CommandError

from apps.inventory.services import expire_reservations


class Command(BaseCommand):
    help = "Expira pedidos pendentes com reservas de estoque vencidas."

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=100,
            help="Quantidade máxima de pedidos processados por execução.",
        )

    def handle(self, *args, **options):
        limit = options["limit"]

        if limit <= 0:
            raise CommandError("O limite deve ser maior que zero.")

        expired_count = expire_reservations(limit=limit)

        if expired_count:
            self.stdout.write(
                self.style.SUCCESS(
                    f"{expired_count} reserva(s) expirada(s) com sucesso."
                )
            )
        else:
            self.stdout.write("Nenhuma reserva vencida encontrada.")
