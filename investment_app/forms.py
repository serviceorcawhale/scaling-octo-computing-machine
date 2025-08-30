# forms.py
from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator
from decimal import Decimal
from .models import DepositTransaction, WithdrawalTransaction, UserProfile
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import SetPasswordForm as DjangoSetPasswordForm
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_decode
from django.utils.encoding import force_str


class CustomUserCreationForm(UserCreationForm):
    email = forms.EmailField(required=True)
    terms_accepted = forms.BooleanField(required=True, error_messages={'required': 'You must accept the terms and conditions'})
    
    class Meta:
        model = User
        fields = ("username", "email", "password1", "password2", "terms_accepted")
    
    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"]
        if commit:
            user.save()
        return user

class DepositForm(forms.ModelForm):
    CURRENCY_CHOICES = [
        ('USDT', 'Tether USDT(TRC20)'),
        ('BTC', 'Bitcoin (BTC)'),
        ('ETH', 'Ethereum (ETH)'),
    ]
    
    currency = forms.ChoiceField(
        choices=CURRENCY_CHOICES, 
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    
    amount = forms.DecimalField(
        max_digits=20, 
        decimal_places=8, 
        validators=[MinValueValidator(Decimal('50.0'))],
        widget=forms.NumberInput(attrs={
            'class': 'form-control', 
            'placeholder': 'Amount in USD',
            'min': '50',
            'step': '0.01'
        })
    )
    
    txn_hash = forms.CharField(
        required=False, 
        widget=forms.TextInput(attrs={
            'class': 'form-control', 
            'placeholder': 'Transaction Hash (Optional)'
        })
    )
    
    class Meta:
        model = DepositTransaction
        fields = ['currency', 'amount', 'txn_hash']
    
    def clean_amount(self):
        amount = self.cleaned_data.get('amount')
        if amount is not None and amount < Decimal('50.0'):
            raise forms.ValidationError("Minimum deposit is $50 USD for all payment methods.")
        return amount
    
    def clean(self):
        cleaned_data = super().clean()
        # Additional validation if needed
        return cleaned_data

class WithdrawalForm(forms.ModelForm):
    CURRENCY_CHOICES = [
        ('USDT', 'Tether USDT(TRC20)'),
        ('BTC', 'Bitcoin (BTC)'),
        ('ETH', 'Ethereum (ETH)'),
    ]
    
    currency = forms.ChoiceField(
        choices=CURRENCY_CHOICES, 
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    
    amount = forms.DecimalField(
        max_digits=20, 
        decimal_places=8, 
        widget=forms.NumberInput(attrs={
            'class': 'form-control', 
            'placeholder': 'Amount'
        })
    )
    
    destination_address = forms.CharField(
        widget=forms.TextInput(attrs={
            'class': 'form-control', 
            'placeholder': 'Destination Wallet Address'
        })
    )
    
    class Meta:
        model = WithdrawalTransaction
        fields = ['currency', 'amount', 'destination_address']
    
    def clean_amount(self):
        amount = self.cleaned_data.get('amount')
        if amount < 5:
            raise forms.ValidationError("Minimum withdrawal amount is $5 equivalent.")
        return amount



class UserProfileForm(forms.ModelForm):
    class Meta:
        model = UserProfile
        fields = []  # We'll add fields as needed later
        
        
from django import forms
from .models import KYCVerification
from django.core.validators import FileExtensionValidator

class KYCVerificationForm(forms.ModelForm):
    document_front = forms.ImageField(
        widget=forms.FileInput(attrs={'accept': 'image/*'}),
        validators=[FileExtensionValidator(allowed_extensions=['jpg', 'jpeg', 'png'])]
    )
    document_back = forms.ImageField(
        required=False,
        widget=forms.FileInput(attrs={'accept': 'image/*'}),
        validators=[FileExtensionValidator(allowed_extensions=['jpg', 'jpeg', 'png'])]
    )
    selfie_with_document = forms.ImageField(
        widget=forms.FileInput(attrs={'accept': 'image/*'}),
        validators=[FileExtensionValidator(allowed_extensions=['jpg', 'jpeg', 'png'])]
    )
    date_of_birth = forms.DateField(
        widget=forms.DateInput(attrs={'type': 'date'})
    )
    
    class Meta:
        model = KYCVerification
        fields = [
            'document_type', 'document_number', 'document_front', 
            'document_back', 'selfie_with_document', 'date_of_birth',
            'address', 'city', 'country', 'postal_code'
        ]
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            field.widget.attrs['class'] = 'form-control'
            
    def clean_document_back(self):
        document_type = self.cleaned_data.get('document_type')
        document_back = self.cleaned_data.get('document_back')
        
        # If document is ID card, require back image
        if document_type == 'id_card' and not document_back:
            raise forms.ValidationError("Back image of ID card is required.")
            
        return document_back


class ProfileUpdateForm(forms.ModelForm):
    email = forms.EmailField()
    first_name = forms.CharField(max_length=30, required=False)
    last_name = forms.CharField(max_length=30, required=False)
    
    class Meta:
        model = UserProfile
        fields = ['phone_number', 'date_of_birth', 'address', 'city', 'country', 'postal_code']
        widgets = {
            'date_of_birth': forms.DateInput(attrs={'type': 'date'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and hasattr(self.instance, 'user'):
            self.fields['email'].initial = self.instance.user.email
            self.fields['first_name'].initial = self.instance.user.first_name
            self.fields['last_name'].initial = self.instance.user.last_name
    
    def save(self, commit=True):
        profile = super().save(commit=False)
        profile.user.email = self.cleaned_data['email']
        profile.user.first_name = self.cleaned_data['first_name']
        profile.user.last_name = self.cleaned_data['last_name']
        profile.user.save()
        
        if commit:
            profile.save()
        return profile
    
    
class CustomPasswordResetRequestForm(forms.Form):
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter your email address',
            'required': 'required'
        })
    )
    
    def clean_email(self):
        email = self.cleaned_data.get('email')
        User = get_user_model()
        
        if not User.objects.filter(email=email, is_active=True).exists():
            # Don't reveal that the email doesn't exist (security best practice)
            # We'll still show success message even if email doesn't exist
            pass
            
        return email

class CustomSetPasswordForm(forms.Form):
    new_password1 = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter new password',
            'required': 'required'
        }),
        min_length=8,
        error_messages={'min_length': 'Password must be at least 8 characters long.'}
    )
    new_password2 = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Confirm new password',
            'required': 'required'
        })
    )
    
    def clean(self):
        cleaned_data = super().clean()
        password1 = cleaned_data.get('new_password1')
        password2 = cleaned_data.get('new_password2')
        
        if password1 and password2 and password1 != password2:
            raise forms.ValidationError("Passwords don't match")
            
        return cleaned_data    