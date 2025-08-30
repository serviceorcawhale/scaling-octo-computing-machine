# management/commands/check_expired_deposits.py
from django.core.management.base import BaseCommand
from django.utils import timezone
from investment_app.models import DepositTransaction

class Command(BaseCommand):
    help = 'Check and mark expired deposits'

    def handle(self, *args, **options):
        # Find pending deposits that have expired
        expired_deposits = DepositTransaction.objects.filter(
            status='pending',
            expires_at__lte=timezone.now()
        )
        
        count = expired_deposits.count()
        expired_deposits.update(status='expired')
        
        self.stdout.write(
            self.style.SUCCESS(f'Marked {count} deposits as expired')
        )