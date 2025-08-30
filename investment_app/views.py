from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
import json
from django.db.models import Sum, Q
from datetime import datetime, timedelta
from decimal import Decimal
import random
from datetime import date
from .forms import ProfileUpdateForm
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.forms import PasswordChangeForm
from django.urls import reverse
from django.views.decorators.http import require_POST
from .models import UserProfile
from django.views import View
from django.utils import timezone
from .models import Referral, ReferralEarning
from django.core.exceptions import ValidationError
from django.utils import timezone
from .models import KYCVerification
from .forms import KYCVerificationForm
from django.core.mail import send_mail
from django.conf import settings
from django.views.generic import TemplateView

from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str
from django.template.loader import render_to_string
from django.urls import reverse
from django.shortcuts import redirect
from django.contrib import messages
from .forms import CustomPasswordResetRequestForm, CustomSetPasswordForm
from django.views.decorators.csrf import csrf_exempt

from .models import (
    UserProfile, InvestmentPlan, CryptoWallet, 
    DepositTransaction, WithdrawalTransaction, YieldCredit, UserInvestment
)
from .forms import CustomUserCreationForm, DepositForm, WithdrawalForm

def index(request):
    plans = InvestmentPlan.objects.all().order_by('min_amount')
    return render(request, 'investment_app/index.html', {'plans': plans})

def login_view(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        
        if user is not None:
            login(request, user)
            return redirect('dashboard')
        else:
            messages.error(request, 'Invalid username or password.')
    
    return render(request, 'investment_app/login.html')

@login_required
def logout_view(request):
    logout(request)
    messages.success(request, 'You have been logged out.')
    return redirect('index')

@login_required
def dashboard(request):
    profile = request.user.userprofile
    recent_transactions = []
    
    # Get recent deposits
    deposits = DepositTransaction.objects.filter(user=request.user).order_by('-created_at')[:5]
    for deposit in deposits:
        recent_transactions.append({
            'type': 'deposit',
            'amount': deposit.amount,
            'currency': deposit.currency,
            'status': deposit.status,
            'date': deposit.created_at
        })
    
    # Get recent withdrawals
    withdrawals = WithdrawalTransaction.objects.filter(user=request.user).order_by('-created_at')[:5]
    for withdrawal in withdrawals:
        recent_transactions.append({
            'type': 'withdrawal',
            'amount': withdrawal.amount,
            'currency': withdrawal.currency,
            'status': withdrawal.status,
            'date': withdrawal.created_at
        })
    
    # Get recent yield credits
    yields = YieldCredit.objects.filter(user=request.user).order_by('-credited_at')[:5]
    for y in yields:
        recent_transactions.append({
            'type': 'yield',
            'amount': y.amount,
            'currency': 'USD',
            'status': 'credited',
            'date': y.credited_at
        })
    
    # Sort by date
    recent_transactions.sort(key=lambda x: x['date'], reverse=True)
    recent_transactions = recent_transactions[:5]
    
    # Get yield data for chart (last 7 days)
    chart_data = []
    today = timezone.now().date()
    
    for i in range(6, -1, -1):
        target_date = today - timedelta(days=i)
        
        daily_yield = YieldCredit.objects.filter(
            user=request.user, 
            credited_at__date=target_date
        ).aggregate(total=Sum('amount'))['total'] or 0
        
        chart_data.append({
            'date': target_date.strftime('%Y-%m-%d'),
            'yield': float(daily_yield)
        })
    
    # Get user's active investments for next yield calculation
    user_investments = UserInvestment.objects.filter(user=request.user, active=True)
    
    # Calculate next yield time (earliest among all investments)
    next_yield_times = []
    for investment in user_investments:
        if investment.next_yield_calculation:
            next_yield_times.append(investment.next_yield_calculation)
    
    next_yield_time = min(next_yield_times) if next_yield_times else None
    
    # Calculate yield progress dynamically (percentage of day passed since last yield)
    yield_progress = 0
    if next_yield_time:
        # Find the most recent yield calculation
        last_yield_time = max([inv.last_yield_calculation for inv in user_investments 
                             if inv.last_yield_calculation] or [None])
        
        if last_yield_time:
            time_since_last_yield = timezone.now() - last_yield_time
            progress_percentage = (time_since_last_yield.total_seconds() / 86400) * 100  # 86400 seconds in 24 hours
            yield_progress = min(100, max(0, int(progress_percentage)))
    
    # Calculate today's yield
    today_yield = YieldCredit.objects.filter(
        user=request.user, 
        credited_at__date=today
    ).aggregate(total=Sum('amount'))['total'] or 0
    
    # Calculate expected daily yield based on active investments
    expected_daily_yield = sum(
        investment.amount * investment.plan.base_daily_yield 
        for investment in user_investments
    )
    
    context = {
        'profile': profile,
        'recent_transactions': recent_transactions,
        'chart_data': json.dumps(chart_data),
        'investments_count': user_investments.count(),
        'active_deposits': DepositTransaction.objects.filter(user=request.user, status='approved').count(),
        'pending_withdrawals': WithdrawalTransaction.objects.filter(user=request.user, status='pending_admin_approval').count(),
        'today_yield': today_yield,
        'expected_daily_yield': expected_daily_yield,
        'yield_progress': yield_progress,
        'next_yield_time': next_yield_time,
        'has_active_investments': user_investments.exists(),
    }
    
    return render(request, 'investment_app/dashboard.html', context)

# views.py
@login_required
def invest_view(request):
    plans = InvestmentPlan.objects.all().order_by('min_amount')
    current_investments = UserInvestment.objects.filter(user=request.user, active=True)
    
    # Calculate total profit for each investment
    investments_with_profit = []
    for investment in current_investments:
        total_profit = YieldCredit.objects.filter(
            investment=investment
        ).aggregate(total=Sum('amount'))['total'] or 0
        investments_with_profit.append({
            'investment': investment,
            'total_profit': total_profit
        })
    
    if request.method == 'POST':
        plan_id = request.POST.get('plan_id')
        amount = Decimal(request.POST.get('amount', 0))
        
        try:
            plan = InvestmentPlan.objects.get(id=plan_id)
            
            if amount < plan.min_amount:
                messages.error(request, f'Minimum investment for {plan.name} is ${plan.min_amount}.')
            elif plan.max_amount and amount > plan.max_amount:
                messages.error(request, f'Maximum investment for {plan.name} is ${plan.max_amount}.')
            else:
                # Check if user has enough principal balance
                if request.user.userprofile.principal_balance >= amount:
                    # Create investment
                    investment = UserInvestment.objects.create(
                        user=request.user,
                        plan=plan,
                        amount=amount
                    )
                    
                    # Deduct from principal balance
                    profile = request.user.userprofile
                    profile.principal_balance -= amount
                    profile.save()
                    
                    # Process referral commission if user was referred
                    try:
                        referral = Referral.objects.get(referred_user=request.user, is_active=True)
                        commission_rate = Decimal('0.0012')  # 0.12%
                        commission = amount * commission_rate
                        
                        ReferralEarning.objects.create(
                            user=referral.referrer,
                            referral=referral,
                            amount=commission,
                            earning_type='investment',
                            description=f"Commission from {request.user.username}'s investment of ${amount}"
                        )
                        
                        # Update referrer's balance
                        referrer_profile = referral.referrer.userprofile
                        referrer_profile.earned_balance += commission
                        referrer_profile.total_referral_earnings += commission
                        referrer_profile.save()
                        
                    except Referral.DoesNotExist:
                        pass  # No referral exists for this user
                    
                    messages.success(request, f'Successfully invested ${amount} in {plan.name} plan.')
                    return redirect('invest')
                else:
                    messages.error(request, 'Insufficient balance. Please deposit funds first.')
        except InvestmentPlan.DoesNotExist:
            messages.error(request, 'Invalid investment plan.')
    
    return render(request, 'investment_app/invest.html', {
        'plans': plans,
        'current_investments': investments_with_profit
    })

@login_required
def deposit_view(request):
    form = DepositForm(request.POST or None)
    deposit_address = None
    selected_currency = None
    selected_wallet = None
    time_remaining = None
    deposit_amount = None
    
    # Get recent deposits for display
    recent_deposits = DepositTransaction.objects.filter(
        user=request.user
    ).order_by('-created_at')[:5]

    if request.method == 'POST' and form.is_valid():
        deposit = form.save(commit=False)
        deposit.user = request.user
        
        # Minimum amount validation - always $50 USD
        if deposit.amount < Decimal('50.0'):
            error_msg = 'Minimum deposit is $50 USD for all payment methods.'
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'error': error_msg})
            messages.error(request, error_msg)
            return render(request, 'investment_app/deposit.html', {
                'form': form,
                'recent_deposits': recent_deposits,
            })
        
        # Get a random active wallet for the selected currency
        wallets = CryptoWallet.objects.filter(
            currency=deposit.currency, 
            is_active=True
        )
        
        if wallets.exists():
            selected_wallet = random.choice(list(wallets))
            deposit.wallet = selected_wallet
            deposit.save()
            
            # Set variables for template
            deposit_address = selected_wallet.address
            selected_currency = deposit.currency
            deposit_amount = deposit.amount
            time_remaining = deposit.time_remaining()
            
            # For AJAX requests, return JSON response
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': True,
                    'address': deposit_address,
                    'currency': selected_currency,
                    'amount': str(deposit_amount),
                    'expires_in': time_remaining.total_seconds(),
                    'transaction_id': deposit.id
                })
            
            messages.success(request, f'Deposit request created. Please send ${deposit.amount} USD worth of {selected_currency} to the provided address. This address expires in 24 hours.')
        else:
            error_msg = 'No wallet available for this currency. Please try again later.'
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'error': error_msg})
            messages.error(request, error_msg)
    
    # For AJAX requests that don't create a deposit
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        # Check for form errors
        if form.errors:
            error_msg = ''
            if 'currency' in form.errors:
                error_msg = 'Please select a payment method.'
            elif 'amount' in form.errors:
                # Use our custom error message instead of the form's
                error_msg = 'Minimum deposit is $50 USD for all payment methods.'
            else:
                error_msg = 'Please check your input and try again.'
            
            return JsonResponse({'success': False, 'error': error_msg})
        
        return JsonResponse({'success': False, 'error': 'Invalid form data'})
    
    context = {
        'form': form,
        'deposit_address': deposit_address,
        'selected_currency': selected_currency,
        'selected_wallet': selected_wallet,
        'recent_deposits': recent_deposits,
        'time_remaining': time_remaining,
        'deposit_amount': deposit_amount,
    }
    
    return render(request, 'investment_app/deposit.html', context)


@login_required
def withdraw_view(request):
    profile = request.user.userprofile
    
    if request.method == 'POST':
        form = WithdrawalForm(request.POST)
        if form.is_valid():
            withdrawal = form.save(commit=False)
            withdrawal.user = request.user
            
            if withdrawal.amount > profile.earned_balance:
                messages.error(request, 'Insufficient earned balance for withdrawal.')
            else:
                withdrawal.save()
                messages.success(request, 'Withdrawal request submitted. It will be processed after admin approval.')
                return redirect('withdraw')
    else:
        form = WithdrawalForm()
    
    return render(request, 'investment_app/withdraw.html', {'form': form, 'profile': profile})

# views.py
@login_required
def transactions_view(request):
    # Get all transactions
    deposits = DepositTransaction.objects.filter(user=request.user).order_by('-created_at')
    withdrawals = WithdrawalTransaction.objects.filter(user=request.user).order_by('-created_at')
    yields = YieldCredit.objects.filter(user=request.user).order_by('-credited_at')
    
    # Combine all transactions into a single list for the template
    all_transactions = []
    
    for deposit in deposits:
        all_transactions.append({
            'type': 'deposit',
            'amount': deposit.amount,
            'currency': deposit.currency,
            'status': deposit.status,
            'date': deposit.created_at,
            # 'txn_hash': deposit.txn_hash,
            'destination_address': deposit.wallet.address if deposit.wallet else None
        })
    
    for withdrawal in withdrawals:
        all_transactions.append({
            'type': 'withdrawal',
            'amount': withdrawal.amount,
            'currency': withdrawal.currency,
            'status': withdrawal.status,
            'date': withdrawal.created_at,
            # 'txn_hash': withdrawal.txn_hash,
            'destination_address': withdrawal.destination_address
        })
    
    for y in yields:
        all_transactions.append({
            'type': 'yield',
            'amount': y.amount,
            'currency': 'USD',
            'status': 'credited',
            'date': y.credited_at,
            # 'txn_hash': None,
            'destination_address': None
        })
    
    # Sort by date (newest first)
    all_transactions.sort(key=lambda x: x['date'], reverse=True)
    
    # Calculate total pages (10 transactions per page)
    transactions_per_page = 10
    total_transactions = len(all_transactions)
    total_pages = max(1, (total_transactions + transactions_per_page - 1) // transactions_per_page)
    
    context = {
        'transactions': all_transactions,
        'total_deposits': deposits.aggregate(total=Sum('amount'))['total'] or 0,
        'total_withdrawn': withdrawals.aggregate(total=Sum('amount'))['total'] or 0,
        'total_yield': yields.aggregate(total=Sum('amount'))['total'] or 0,
        'total_pages': total_pages,
    }
    
    return render(request, 'investment_app/transactions.html', context)


@login_required
def profile_view(request):
    try:
        profile = request.user.userprofile
    except UserProfile.DoesNotExist:
        # Create a user profile if it doesn't exist
        profile = UserProfile.objects.create(user=request.user)
    
    # Get KYC status
    try:
        kyc = KYCVerification.objects.get(user=request.user)
        kyc_status = kyc.status
    except KYCVerification.DoesNotExist:
        kyc_status = None
    
    # Calculate days active
    days_active = (date.today() - request.user.date_joined.date()).days
    
    # Get actual counts from your models - FIXED: Use UserInvestment instead of Investment
    investments_count = UserInvestment.objects.filter(user=request.user).count()
    
    # For transactions, use your actual transaction models
    # Assuming you have DepositTransaction and WithdrawalTransaction models
    completed_deposits = DepositTransaction.objects.filter(
        user=request.user, 
        status='approved'
    ).count()
    completed_withdrawals = WithdrawalTransaction.objects.filter(
        user=request.user, 
        status='approved'
    ).count()
    completed_transactions = completed_deposits + completed_withdrawals
    
    context = {
        'profile': profile,
        'profile': profile,
        'kyc_status': kyc_status,
        'investments_count': investments_count,
        'completed_transactions': completed_transactions,
        'days_active': days_active,
        'has_2fa': profile.two_factor_enabled  # Use your model field
    }
    
    return render(request, 'investment_app/profile.html', context)


@login_required
@require_POST
def enable_2fa(request):
    profile = request.user.userprofile
    profile.two_factor_enabled = True
    profile.save()
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'success': True, 'message': 'Two-factor authentication enabled.'})
    
    messages.success(request, 'Two-factor authentication enabled.')
    return redirect('profile')

@login_required
@require_POST
def disable_2fa(request):
    profile = request.user.userprofile
    profile.two_factor_enabled = False
    profile.save()
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'success': True, 'message': 'Two-factor authentication disabled.'})
    
    messages.success(request, 'Two-factor authentication disabled.')
    return redirect('profile')

@login_required
@require_POST
def delete_account(request):
    password = request.POST.get('confirm_password')
    
    if not request.user.check_password(password):
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({
                'success': False,
                'error': 'Incorrect password'
            })
        messages.error(request, 'Incorrect password. Account deletion failed.')
        return redirect('profile')
    
    # Delete user account
    request.user.delete()
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({
            'success': True,
            'redirect_url': reverse('home')
        })
    
    messages.success(request, 'Your account has been deleted successfully.')
    return redirect('home')


class CustomPasswordResetView(View):
    template_name = 'investment_app/email/password_reset.html'
    form_class = CustomPasswordResetRequestForm
    email_template_name = 'investment_app/email/password_reset_email.html'
    subject_template_name = 'investment_app/email/password_reset_subject.txt'
    
    def get(self, request):
        form = self.form_class()
        return render(request, self.template_name, {'form': form})
    
    def post(self, request):
        form = self.form_class(request.POST)
        
        if form.is_valid():
            email = form.cleaned_data['email']
            User = get_user_model()
            users = User.objects.filter(email=email, is_active=True)
            
            if users.exists():
                user = users.first()
                # Generate password reset token
                token = default_token_generator.make_token(user)
                uid = urlsafe_base64_encode(force_bytes(user.pk))
                
                # Build reset URL
                reset_url = request.build_absolute_uri(
                    reverse('password_reset_confirm', kwargs={'uidb64': uid, 'token': token})
                )
                
                # Send email
                context = {
                    'user': user,
                    'reset_url': reset_url,
                    'protocol': 'https' if request.is_secure() else 'http',
                    'domain': request.get_host(),
                    'uid': uid,
                    'token': token,
                }
                
                subject = render_to_string(self.subject_template_name, context).strip()
                message = render_to_string(self.email_template_name, context)
                
                try:
                    send_mail(
                        subject,
                        '',  # Empty text message since we're using HTML
                        None,  # Use DEFAULT_FROM_EMAIL from settings
                        [email],
                        html_message=message,
                        fail_silently=False,
                    )
                except Exception as e:
                    # Log error but don't show to user (security)
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.error(f"Password reset email error: {str(e)}")
            
            # Always show success message regardless of whether email exists
            # FIX: Redirect to the URL name, not template path
            return redirect('password_reset_done')
        
        return render(request, self.template_name, {'form': form})

class CustomPasswordResetDoneView(View):
    template_name = 'investment_app/email/password_reset_done.html'
    
    def get(self, request):
        return render(request, self.template_name)

class CustomPasswordResetConfirmView(View):
    template_name = 'investment_app/email/password_reset_confirm.html'
    form_class = CustomSetPasswordForm
    
    def get(self, request, uidb64, token):
        try:
            uid = force_str(urlsafe_base64_decode(uidb64))
            user = get_user_model().objects.get(pk=uid, is_active=True)
            
            if default_token_generator.check_token(user, token):
                form = self.form_class()
                return render(request, self.template_name, {
                    'form': form,
                    'validlink': True,
                    'uidb64': uidb64,
                    'token': token
                })
            else:
                return render(request, self.template_name, {'validlink': False})
                
        except (TypeError, ValueError, OverflowError, get_user_model().DoesNotExist):
            return render(request, self.template_name, {'validlink': False})
    
    def post(self, request, uidb64, token):
        try:
            uid = force_str(urlsafe_base64_decode(uidb64))
            user = get_user_model().objects.get(pk=uid, is_active=True)
            
            if default_token_generator.check_token(user, token):
                form = self.form_class(request.POST)
                
                if form.is_valid():
                    # Set new password
                    new_password = form.cleaned_data['new_password1']
                    user.set_password(new_password)
                    user.save()
                    
                    messages.success(request, 'Your password has been reset successfully.')
                    return redirect('password_reset_complete')
                
                return render(request, self.template_name, {
                    'form': form,
                    'validlink': True,
                    'uidb64': uidb64,
                    'token': token
                })
            else:
                return render(request, self.template_name, {'validlink': False})
                
        except (TypeError, ValueError, OverflowError, get_user_model().DoesNotExist):
            return render(request, self.template_name, {'validlink': False})

class CustomPasswordResetCompleteView(View):
    template_name = 'investment_app/email/password_reset_complete.html'
    
    def get(self, request):
        return render(request, self.template_name)
    
    
    

# Update register_view to handle referrals
def register_view(request):
    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            
            # Handle referral if referral code is provided
            referral_code = request.POST.get('referral_code', '')
            if referral_code:
                try:
                    referrer_profile = UserProfile.objects.get(referral_code=referral_code)
                    referral = Referral.objects.create(
                        referrer=referrer_profile.user,
                        referred_user=user
                    )
                    
                    # Create signup bonus for referrer
                    signup_bonus = Decimal('0.50')
                    ReferralEarning.objects.create(
                        user=referrer_profile.user,
                        referral=referral,
                        amount=signup_bonus,
                        earning_type='signup',
                        description=f"Signup bonus for referring {user.username}"
                    )
                    
                    # Update referrer's balance
                    referrer_profile.earned_balance += signup_bonus
                    referrer_profile.total_referral_earnings += signup_bonus
                    referrer_profile.save()
                    
                except UserProfile.DoesNotExist:
                    pass  # Invalid referral code, just continue with registration
            
            # Authenticate and login the user
            username = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password1')
            user = authenticate(username=username, password=password)
            
            if user is not None:
                login(request, user)
                messages.success(request, 'Registration successful!')
                return redirect('dashboard')
    else:
        form = CustomUserCreationForm()
    
    return render(request, 'investment_app/register.html', {'form': form})


@login_required
def referral_view(request):
    profile = request.user.userprofile
    referrals = Referral.objects.filter(referrer=request.user)
    referral_earnings = ReferralEarning.objects.filter(user=request.user)
    
    # Statistics
    total_referrals = referrals.count()
    active_referrals = referrals.filter(is_active=True).count()
    total_earnings = referral_earnings.aggregate(total=Sum('amount'))['total'] or 0
    pending_earnings = referral_earnings.filter(is_paid=False).aggregate(total=Sum('amount'))['total'] or 0
    
    context = {
        'profile': profile,
        'referrals': referrals,
        'referral_earnings': referral_earnings,
        'total_referrals': total_referrals,
        'active_referrals': active_referrals,
        'total_earnings': total_earnings,
        'pending_earnings': pending_earnings,
    }
    return render(request, 'investment_app/referral.html', context)

# Add view to handle referral link sharing
@login_required
def referral_share_view(request):
    profile = request.user.userprofile
    base_url = request.build_absolute_uri('/')[:-1]  # Remove trailing slash
    referral_url = f"{base_url}/register?ref={profile.referral_code}"
    
    return JsonResponse({
        'success': True,
        'referral_url': referral_url,
        'referral_code': profile.referral_code
    })
    
    
    



@login_required
def kyc_verification(request):
    try:
        kyc = KYCVerification.objects.get(user=request.user)
    except KYCVerification.DoesNotExist:
        kyc = None
    
    # If KYC already exists and is approved, redirect to profile
    if kyc and kyc.status == 'approved':
        messages.info(request, 'Your KYC is already verified.')
        return redirect('profile')
    
    if request.method == 'POST':
        form = KYCVerificationForm(request.POST, request.FILES, instance=kyc)
        if form.is_valid():
            kyc_instance = form.save(commit=False)
            kyc_instance.user = request.user
            kyc_instance.status = 'pending'
            kyc_instance.save()
            
            messages.success(request, 'KYC verification submitted successfully. It will be reviewed within 24-48 hours.')
            return redirect('profile')
    else:
        form = KYCVerificationForm(instance=kyc)
    
    context = {
        'form': form,
        'kyc': kyc,
    }
    return render(request, 'investment_app/kyc/verification.html', context)

@login_required
def kyc_status(request):
    try:
        kyc = KYCVerification.objects.get(user=request.user)
    except KYCVerification.DoesNotExist:
        return redirect('kyc_verification')
    
    context = {
        'kyc': kyc,
    }
    return render(request, 'investment_app/kyc/status.html', context)

# Admin views (if needed)
@login_required
def kyc_list(request):
    if not request.user.is_staff:
        messages.error(request, 'You do not have permission to access this page.')
        return redirect('profile')
    
    status_filter = request.GET.get('status', '')
    
    kycs = KYCVerification.objects.all()
    
    if status_filter:
        kycs = kycs.filter(status=status_filter)
    
    context = {
        'kycs': kycs,
        'status_filter': status_filter,
    }
    return render(request, 'kyc/admin/list.html', context)

@login_required
def kyc_review(request, kyc_id):
    if not request.user.is_staff:
        messages.error(request, 'You do not have permission to access this page.')
        return redirect('profile')
    
    kyc = get_object_or_404(KYCVerification, id=kyc_id)
    
    if request.method == 'POST':
        action = request.POST.get('action')
        reason = request.POST.get('reason', '')
        
        if action == 'approve':
            kyc.status = 'approved'
            messages.success(request, f'KYC for {kyc.user.username} has been approved.')
        elif action == 'reject':
            kyc.status = 'rejected'
            kyc.rejection_reason = reason
            messages.success(request, f'KYC for {kyc.user.username} has been rejected.')
        elif action == 'request_info':
            kyc.status = 'additional_info'
            kyc.rejection_reason = reason
            messages.success(request, f'Additional information requested for {kyc.user.username}.')
        
        kyc.reviewed_by = request.user
        kyc.save()
        
        return redirect('kyc_list')
    
    context = {
        'kyc': kyc,
    }
    return render(request, 'kyc/admin/review.html', context)
    
    
    
    
@login_required
def edit_account(request):
    try:
        # Get or create profile
        profile, created = UserProfile.objects.get_or_create(user=request.user)
        
        if request.method == 'POST':
            # Handle form submission
            user = request.user
            
            # Update user fields
            user.first_name = request.POST.get('first_name', user.first_name)
            user.last_name = request.POST.get('last_name', user.last_name)
            user.email = request.POST.get('email', user.email)
            
            # Update profile fields
            profile.phone_number = request.POST.get('phone_number', profile.phone_number)
            
            # Handle date conversion
            date_of_birth = request.POST.get('date_of_birth')
            if date_of_birth:
                profile.date_of_birth = date_of_birth
                
            profile.address = request.POST.get('address', profile.address)
            profile.city = request.POST.get('city', profile.city)
            profile.country = request.POST.get('country', profile.country)
            profile.postal_code = request.POST.get('postal_code', profile.postal_code)
            
            # Save changes
            user.save()
            profile.save()
            
            messages.success(request, 'Your account information has been updated successfully.')
            return redirect('profile')
        
        return render(request, 'investment_app/edit_account.html', {
            'user': request.user,
            'profile': profile
        })
    
    except Exception as e:
        messages.error(request, f'An error occurred: {str(e)}')
        return redirect('profile')

@login_required
def change_password(request):
    if request.method == 'POST':
        # Handle password change form submission
        user = request.user
        current_password = request.POST.get('current_password')
        new_password = request.POST.get('new_password')
        confirm_password = request.POST.get('confirm_password')
        
        # Debug information
        print("=== PASSWORD CHANGE DEBUG ===")
        print(f"User: {user.username}")
        print(f"Current password provided: {current_password}")
        print(f"Password check result: {user.check_password(current_password)}")
        print(f"New password: {new_password}")
        print(f"Confirm password: {confirm_password}")
        print(f"Passwords match: {new_password == confirm_password}")
        print(f"Password length: {len(new_password) if new_password else 0}")
        print("=============================")
        
        # Validate current password
        if not user.check_password(current_password):
            messages.error(request, 'Your current password is incorrect.')
            return render(request, 'investment_app/change_password.html')
        
        # Validate new password
        if new_password != confirm_password:
            messages.error(request, 'New passwords do not match.')
            return render(request, 'investment_app/change_password.html')
        
        # Check password strength
        if len(new_password) < 8:
            messages.error(request, 'Password must be at least 8 characters long.')
            return render(request, 'investment_app/change_password.html')
        
        # Change password
        user.set_password(new_password)
        user.save()
        
        # Update session auth hash to keep user logged in
        from django.contrib.auth import update_session_auth_hash
        update_session_auth_hash(request, user)
        
        # Verify the change worked
        user.refresh_from_db()
        print(f"Password changed successfully: {user.check_password(new_password)}")
        
        messages.success(request, 'Your password has been changed successfully.')
        return redirect('profile')
    
    return render(request, 'investment_app/change_password.html')




class TermsView(TemplateView):
    template_name = 'investment_app/terms.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = 'Terms of Service - Orca Whale Investment'
        return context


class PrivacyView(TemplateView):
    template_name = 'investment_app/privacy.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = 'Privacy Policy - Orca Whale Investment'
        return context