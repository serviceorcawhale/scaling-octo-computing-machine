from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver
from decimal import Decimal
import secrets
import string
import uuid
from django.utils.text import slugify
from django.utils import timezone
from datetime import timedelta
from django.core.validators import MinValueValidator

class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    principal_balance = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    earned_balance = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    total_withdrawn = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    email_verified = models.BooleanField(default=False)
    verification_token = models.CharField(max_length=100, blank=True)
    referral_code = models.CharField(max_length=100, unique=True, blank=True, null=True)
    total_referral_earnings = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    phone_number = models.CharField(max_length=20, blank=True, null=True)
    date_of_birth = models.DateField(blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    city = models.CharField(max_length=100, blank=True, null=True)
    country = models.CharField(max_length=100, blank=True, null=True)
    postal_code = models.CharField(max_length=20, blank=True, null=True)
    profile_picture = models.ImageField(upload_to='profile_pictures/', blank=True, null=True)
    two_factor_enabled = models.BooleanField(default=False)
    
    
    
        
    def save(self, *args, **kwargs):
        if not self.referral_code:
            self.referral_code = self.generate_hybrid_referral_code()
        super().save(*args, **kwargs)
    
    def generate_hybrid_referral_code(self):
        """
        Generate a referral code that's partly based on username
        and partly random for uniqueness
        """
        # Get first 4 characters from username (cleaned)
        username_part = slugify(self.user.username).replace('-', '').upper()[:4]
        
        # If username is too short, pad it
        if len(username_part) < 4:
            username_part = username_part.ljust(4, 'X')
        
        # Generate random part (4 characters)
        random_part = ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(4))
        
        code = f"{username_part}{random_part}"
        
        # Ensure uniqueness with retry logic
        max_retries = 20
        for i in range(max_retries):
            if not UserProfile.objects.filter(referral_code=code).exists():
                return code
            # If code exists, generate a new random part
            random_part = ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(4))
            code = f"{username_part}{random_part}"
        
        # Final fallback - pure random code
        for i in range(max_retries):
            code = ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(8))
            if not UserProfile.objects.filter(referral_code=code).exists():
                return code
                
        # Ultimate fallback - UUID
        return str(uuid.uuid4()).replace('-', '')[:8].upper()
    
    # In models.py, add to UserProfile class
    @property
    def total_balance(self):
        return self.principal_balance + self.earned_balance
    
    def __str__(self):
        return f"{self.user.username}'s Profile"

class InvestmentPlan(models.Model):
    name = models.CharField(max_length=100)
    min_amount = models.DecimalField(max_digits=20, decimal_places=4)
    max_amount = models.DecimalField(max_digits=20, decimal_places=4, null=True, blank=True)
    base_daily_yield = models.DecimalField(max_digits=5, decimal_places=4)  # 0.0065 for 0.65%
    duration_days = models.IntegerField(null=True, blank=True)  # Optional: plan duration
    
    def __str__(self):
        return self.name

class UserInvestment(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    plan = models.ForeignKey(InvestmentPlan, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=20, decimal_places=8)
    start_date = models.DateTimeField(auto_now_add=True)
    end_date = models.DateTimeField(null=True, blank=True)
    last_yield_calculation = models.DateTimeField(null=True, blank=True)  # ADD THIS
    next_yield_calculation = models.DateTimeField(null=True, blank=True)  # ADD THIS
    active = models.BooleanField(default=True)  # KEEP THIS
    
    def save(self, *args, **kwargs):
        # Set end date based on plan duration if it exists
        if self.plan.duration_days and not self.end_date:
            self.end_date = timezone.now() + timedelta(days=self.plan.duration_days)
        
        # Set initial next yield calculation time if this is a new investment
        if not self.pk and not self.next_yield_calculation:
            self.next_yield_calculation = timezone.now() + timedelta(hours=24)
            
        super().save(*args, **kwargs)
    
    def is_expired(self):
        if self.end_date and timezone.now() > self.end_date:
            return True
        return False
    
    def should_calculate_yield(self):
        """Check if it's time to calculate yield for this investment"""
        if not self.active:
            return False
        
            # Check if investment has expired
        if self.is_expired():
            self.active = False
            self.save()
            return False
        
        if self.next_yield_calculation and timezone.now() >= self.next_yield_calculation:
            return True
        
        return False
    
    def calculate_and_credit_yield(self):
        """Calculate and credit yield for this investment"""
        if not self.should_calculate_yield():
            return None
        
        # Calculate daily yield
        daily_yield = self.amount * self.plan.base_daily_yield
        
        # Create yield credit
        yield_credit = YieldCredit.objects.create(
            user=self.user,
            amount=daily_yield,
            investment=self
        )
        
        # Update user's earned balance
        profile = self.user.userprofile
        profile.earned_balance += daily_yield
        profile.save()
        
        # Update calculation times
        self.last_yield_calculation = timezone.now()
        self.next_yield_calculation = self.last_yield_calculation + timedelta(hours=24)
        self.save()
        
        return yield_credit
    
    def __str__(self):
        return f"{self.user.username} - {self.plan.name}"

class CryptoWallet(models.Model):
    CURRENCY_CHOICES = [
        ('USDT', 'Tether USDT(TRC20)'),
        ('BTC', 'Bitcoin (BTC)'),
        ('ETH', 'Ethereum (ETH)'),
    ]
    
    currency = models.CharField(max_length=10, choices=CURRENCY_CHOICES)
    address = models.TextField()
    qr_code = models.ImageField(upload_to='wallet_qrcodes/', null=True, blank=True)
    is_active = models.BooleanField(default=True)
    
    def __str__(self):
        return f"{self.currency} - {self.address[:10]}..."



class DepositTransaction(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('expired', 'Expired'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    amount = models.DecimalField(
        max_digits=20, 
        decimal_places=8,
        validators=[MinValueValidator(Decimal('50.0'))]  # Add minimum amount validator
    )
    currency = models.CharField(max_length=10, choices=CryptoWallet.CURRENCY_CHOICES)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    txn_hash = models.CharField(max_length=100, blank=True)
    wallet = models.ForeignKey(CryptoWallet, on_delete=models.CASCADE, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    
    def __str__(self):
        return f"Deposit: {self.user.username} - {self.amount} {self.currency}"
    
    def save(self, *args, **kwargs):
        # Set expiration time (24 hours from creation) if this is a new deposit
        if not self.pk and not self.expires_at:
            self.expires_at = timezone.now() + timedelta(hours=24)
        super().save(*args, **kwargs)
    
    def is_expired(self):
        if self.expires_at and timezone.now() > self.expires_at:
            return True
        return False
    
    def time_remaining(self):
        if self.expires_at:
            remaining = self.expires_at - timezone.now()
            if remaining.total_seconds() > 0:
                return remaining
        return timedelta(0)

class WithdrawalTransaction(models.Model):
    STATUS_CHOICES = [
        ('pending_admin_approval', 'Pending Admin Approval'),
        ('paid', 'Paid'),
        ('rejected', 'Rejected'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=20, decimal_places=8)
    currency = models.CharField(max_length=10, choices=CryptoWallet.CURRENCY_CHOICES)
    destination_address = models.TextField()
    status = models.CharField(max_length=25, choices=STATUS_CHOICES, default='pending_admin_approval')
    created_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    
    def __str__(self):
        return f"Withdrawal: {self.user.username} - {self.amount} {self.currency}"

class YieldCredit(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=20, decimal_places=8)
    credited_at = models.DateTimeField(auto_now_add=True)
    investment = models.ForeignKey(UserInvestment, on_delete=models.CASCADE, null=True)
    
    def __str__(self):
        return f"Yield: {self.user.username} - {self.amount}"

@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.create(user=instance)

@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    instance.userprofile.save()
    
class Referral(models.Model):
    referrer = models.ForeignKey(User, on_delete=models.CASCADE, related_name='referrals_made')
    referred_user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='referral')
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)
    
    def __str__(self):
        return f"{self.referrer.username} → {self.referred_user.username}"

class ReferralEarning(models.Model):
    EARNING_TYPES = [
        ('signup', 'Signup Bonus'),
        ('investment', 'Investment Commission'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='referral_earnings')
    referral = models.ForeignKey(Referral, on_delete=models.CASCADE, related_name='earnings')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    earning_type = models.CharField(max_length=20, choices=EARNING_TYPES)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    is_paid = models.BooleanField(default=False)
    
    def __str__(self):
        return f"{self.user.username} - {self.earning_type} - ${self.amount}"



def user_kyc_path(instance, filename):
    # File will be uploaded to MEDIA_ROOT/user_<id>/kyc/<filename>
    return f'user_{instance.user.id}/kyc/{filename}'

class KYCVerification(models.Model):
    STATUS_CHOICES = (
        ('pending', 'Pending Review'),
        ('under_review', 'Under Review'),
        ('approved', 'Verified'),
        ('rejected', 'Rejected'),
        ('additional_info', 'Additional Information Required'),
    )
    
    DOCUMENT_TYPES = (
        ('passport', 'Passport'),
        ('id_card', 'National ID Card'),
        ('driving_license', 'Driving License'),
    )
    
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='kyc')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    document_type = models.CharField(max_length=20, choices=DOCUMENT_TYPES)
    document_number = models.CharField(max_length=50)
    document_front = models.ImageField(upload_to=user_kyc_path)
    document_back = models.ImageField(upload_to=user_kyc_path, blank=True, null=True)
    selfie_with_document = models.ImageField(upload_to=user_kyc_path)
    date_of_birth = models.DateField()
    address = models.TextField()
    city = models.CharField(max_length=100)
    country = models.CharField(max_length=100)
    postal_code = models.CharField(max_length=20)
    submitted_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(blank=True, null=True)
    reviewed_by = models.ForeignKey(User, on_delete=models.SET_NULL, blank=True, null=True, related_name='reviewed_kycs')
    rejection_reason = models.TextField(blank=True, null=True)
    
    class Meta:
        verbose_name = 'KYC Verification'
        verbose_name_plural = 'KYC Verifications'
    
    def __str__(self):
        return f'{self.user.username} - {self.get_status_display()}'
    
    def get_status_class(self):
        status_classes = {
            'pending': 'kyc-pending',
            'under_review': 'kyc-pending',
            'approved': 'kyc-verified',
            'rejected': 'kyc-rejected',
            'additional_info': 'kyc-pending',
        }
        return status_classes.get(self.status, '')