from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal
from ...models import UserInvestment, YieldCredit, UserProfile

class Command(BaseCommand):
    help = 'Process yields for investments that are due for calculation (24-hour per investment)'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--force-all',
            action='store_true',
            help='Force process all active investments (ignore timing)',
        )
    
    def handle(self, *args, **options):
        force_all = options['force_all']
        
        if force_all:
            # Process all active investments (for testing or manual override)
            investments = UserInvestment.objects.filter(active=True)
            self.stdout.write(self.style.WARNING('FORCING all active investments to process'))
        else:
            # Only process investments that are due for yield calculation
            investments = UserInvestment.objects.filter(
                active=True,
                next_yield_calculation__lte=timezone.now()
            )
        
        processed_count = 0
        skipped_count = 0
        total_yield = Decimal('0')
        
        for investment in investments:
            try:
                if force_all or investment.should_calculate_yield():
                    # Calculate daily yield
                    base_yield = investment.plan.base_daily_yield
                    
                    # Determine correct calculation method
                    if base_yield > Decimal('0.01'):
                        # Stored as percentage, divide by 100
                        daily_yield = investment.amount * (base_yield / Decimal('100'))
                    else:
                        # Stored as decimal, use directly
                        daily_yield = investment.amount * base_yield
                    
                    # Round to avoid floating point issues
                    daily_yield = daily_yield.quantize(Decimal('0.0001'))
                    
                    # Create yield credit
                    YieldCredit.objects.create(
                        user=investment.user,
                        amount=daily_yield,
                        investment=investment
                    )
                    
                    # Update user's earned balance
                    profile = investment.user.userprofile
                    profile.earned_balance += daily_yield
                    profile.save()
                    
                    # Update calculation times for next yield
                    investment.last_yield_calculation = timezone.now()
                    investment.next_yield_calculation = investment.last_yield_calculation + timedelta(hours=24)
                    investment.save()
                    
                    processed_count += 1
                    total_yield += daily_yield
                    
                    self.stdout.write(
                        self.style.SUCCESS(
                            f'✅ Credited ${daily_yield:.8f} to {investment.user.username} '
                            f'at {timezone.now().strftime("%H:%M:%S")}'
                        )
                    )
                else:
                    skipped_count += 1
                    self.stdout.write(
                        self.style.NOTICE(
                            f'⏰ Skipping {investment.user.username} - '
                            f'next yield at {investment.next_yield_calculation.strftime("%Y-%m-%d %H:%M")}'
                        )
                    )
                    
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(
                        f'❌ Error processing investment {investment.id}: {str(e)}'
                    )
                )
                continue
        
        if processed_count > 0:
            self.stdout.write(
                self.style.SUCCESS(
                    f'🎉 Processed {processed_count} investments, total yield: ${total_yield:.2f}'
                )
            )
        else:
            self.stdout.write(
                self.style.NOTICE(
                    f'ℹ️ No investments due for processing. {skipped_count} investments skipped.'
                )
            )