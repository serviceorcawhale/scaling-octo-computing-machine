# investment_app/middleware.py
from django.utils.deprecation import MiddlewareMixin
from django_otp.middleware import OTPMiddleware
from django.http import HttpResponseRedirect
from django.urls import reverse

class SmartOTPMiddleware(MiddlewareMixin):
    def __init__(self, get_response=None):
        self.get_response = get_response
        self.otp_middleware = OTPMiddleware(get_response)
        super().__init__(get_response)

    def __call__(self, request):
        # List of URL patterns to exclude from OTP
        excluded_patterns = [
            '/admin/',
            '/static/',
            '/media/',
            '/login/',
            '/register/',
            '/password-reset/',
            '/logout/',
            '/test-email/',
        ]
        
        # Check if current path should be excluded
        for pattern in excluded_patterns:
            if request.path.startswith(pattern):
                # Skip OTP for excluded URLs
                if self.get_response is None:
                    return None
                return self.get_response(request)
        
        # Apply OTP to all other requests
        return self.otp_middleware(request)