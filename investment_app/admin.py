from django.contrib import admin
from .models import (
    UserProfile, InvestmentPlan, UserInvestment, 
    CryptoWallet, DepositTransaction, WithdrawalTransaction, YieldCredit
)
from .models import KYCVerification


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'principal_balance', 'earned_balance', 'total_withdrawn', 'email_verified']
    search_fields = ['user__username', 'user__email']

@admin.register(InvestmentPlan)
class InvestmentPlanAdmin(admin.ModelAdmin):
    list_display = ['name', 'min_amount', 'max_amount', 'base_daily_yield', 'duration_days']
    list_editable = ['min_amount', 'max_amount', 'base_daily_yield']

@admin.register(UserInvestment)
class UserInvestmentAdmin(admin.ModelAdmin):
    list_display = ['user', 'plan', 'amount', 'start_date', 'active']
    list_filter = ['active', 'plan', 'start_date']
    search_fields = ['user__username']

@admin.register(CryptoWallet)
class CryptoWalletAdmin(admin.ModelAdmin):
    list_display = ['currency', 'address', 'is_active']
    list_filter = ['currency', 'is_active']
    list_editable = ['is_active']

@admin.register(DepositTransaction)
class DepositTransactionAdmin(admin.ModelAdmin):
    list_display = ['user', 'amount', 'currency', 'status', 'created_at', 'expires_at', 'approved_at']
    list_filter = ['status', 'currency', 'created_at']
    search_fields = ['user__username', 'txn_hash']
    readonly_fields = ['expires_at']  # Make expires_at read-only
    actions = ['approve_deposits', 'reject_deposits', 'mark_expired']
    
    def mark_expired(self, request, queryset):
        expired_count = 0
        for deposit in queryset:
            if deposit.is_expired() and deposit.status == 'pending':
                deposit.status = 'expired'
                deposit.save()
                expired_count += 1
        self.message_user(request, f"Marked {expired_count} deposits as expired.")
    mark_expired.short_description = "Mark selected as expired"

@admin.register(WithdrawalTransaction)
class WithdrawalTransactionAdmin(admin.ModelAdmin):
    list_display = ['user', 'amount', 'currency', 'status', 'created_at', 'processed_at']
    list_filter = ['status', 'currency', 'created_at']
    search_fields = ['user__username', 'destination_address']
    actions = ['approve_withdrawals', 'reject_withdrawals']
    
    def approve_withdrawals(self, request, queryset):
        for withdrawal in queryset:
            if withdrawal.status == 'pending_admin_approval':
                withdrawal.status = 'paid'
                withdrawal.save()
                # Deduct from user's earned balance
                profile = withdrawal.user.userprofile
                profile.earned_balance -= withdrawal.amount
                profile.total_withdrawn += withdrawal.amount
                profile.save()
        self.message_user(request, "Selected withdrawals have been approved and marked as paid.")
    
    def reject_withdrawals(self, request, queryset):
        queryset.update(status='rejected')
        self.message_user(request, "Selected withdrawals have been rejected.")

from .models import Referral, ReferralEarning

@admin.register(Referral)
class ReferralAdmin(admin.ModelAdmin):
    list_display = ['referrer', 'referred_user', 'created_at', 'is_active']
    list_filter = ['is_active', 'created_at']
    search_fields = ['referrer__username', 'referred_user__username']

@admin.register(ReferralEarning)
class ReferralEarningAdmin(admin.ModelAdmin):
    list_display = ['user', 'earning_type', 'amount', 'is_paid', 'created_at']
    list_filter = ['earning_type', 'is_paid', 'created_at']
    search_fields = ['user__username', 'description']
    actions = ['mark_as_paid']

    def mark_as_paid(self, request, queryset):
        queryset.update(is_paid=True)
        self.message_user(request, "Selected earnings marked as paid.")

@admin.register(YieldCredit)
class YieldCreditAdmin(admin.ModelAdmin):
    list_display = ['user', 'amount', 'credited_at']
    list_filter = ['credited_at']
    search_fields = ['user__username']

@admin.register(KYCVerification)
class KYCVerificationAdmin(admin.ModelAdmin):
    list_display = ('user', 'document_type', 'status', 'submitted_at', 'reviewed_at')
    list_filter = ('status', 'document_type', 'submitted_at')
    search_fields = ('user__username', 'user__email', 'document_number')
    readonly_fields = ('submitted_at',)
    
    fieldsets = (
        ('User Information', {
            'fields': ('user', 'status')
        }),
        ('Document Details', {
            'fields': ('document_type', 'document_number', 'date_of_birth')
        }),
        ('Address Information', {
            'fields': ('address', 'city', 'country', 'postal_code')
        }),
        ('Document Images', {
            'fields': ('document_front', 'document_back', 'selfie_with_document')
        }),
        ('Review Information', {
            'fields': ('submitted_at', 'reviewed_at', 'reviewed_by', 'rejection_reason')
        }),
    )


admin.site.site_header = "Crypto Investment Platform Administration"
admin.site.site_title = "Crypto Investment Admin"
admin.site.index_title = "Welcome to Crypto Investment Platform Admin"