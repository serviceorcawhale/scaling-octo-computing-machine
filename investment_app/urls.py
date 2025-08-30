from django.urls import path
from . import views

from .views import (
    CustomPasswordResetView, CustomPasswordResetDoneView,
    CustomPasswordResetConfirmView, CustomPasswordResetCompleteView
)
from .views import referral_view, referral_share_view
urlpatterns = [
    path('', views.index, name='index'),
    path('register/', views.register_view, name='register'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('invest/', views.invest_view, name='invest'),
    path('deposit/', views.deposit_view, name='deposit'),
    path('withdraw/', views.withdraw_view, name='withdraw'),
    path('transactions/', views.transactions_view, name='transactions'),
    path('profile/', views.profile_view, name='profile'),
    
    # Password reset URLs
    path('password-reset/', CustomPasswordResetView.as_view(), name='password_reset'),
    path('password-reset/done/', CustomPasswordResetDoneView.as_view(), name='password_reset_done'),
    path('password-reset-confirm/<uidb64>/<token>/', CustomPasswordResetConfirmView.as_view(), name='password_reset_confirm'),
    path('password-reset/complete/', CustomPasswordResetCompleteView.as_view(), name='password_reset_complete'),
    
    path('referral/', referral_view, name='referral'),
    path('referral/share/', referral_share_view, name='referral_share'),
    
    path('verification/', views.kyc_verification, name='verification'),
    path('status/', views.kyc_status, name='status'),
    
    path('profile/edit/', views.edit_account, name='edit_account'),
    path('profile/change-password/', views.change_password, name='change_password'),
    path('profile/delete_account/', views.delete_account, name='delete_account'),    
    
    path('profile/enable_2fa/', views.enable_2fa, name='enable_2fa'),
    path('profile/disable_2fa/', views.disable_2fa, name='disable_2fa'),
    
    # Admin URLs
    path('terms/', views.TermsView.as_view(), name='terms'),
    path('privacy/', views.PrivacyView.as_view(), name='privacy'),
    
    
]