from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, authenticate
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.decorators import login_required
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str
from django.http import HttpResponse, HttpResponseBadRequest
from django.contrib.sites.shortcuts import get_current_site
from django.utils import timezone
from django.contrib import messages
from django.conf import settings
import uuid

from .models import User
from .forms import RegistrationForm


def landing(request):
    """Landing page with login/register buttons."""
    return render(request, 'accounts/landing.html')


def register(request):
    if request.method == 'POST':
        form = RegistrationForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.is_active = True  # User is active but email not verified
            user.save()
            
            # Send verification email
            send_verification_email(request, user)
            
            messages.success(request, 'Registration successful! Please check your email to verify your account.')
            return redirect('login')
    else:
        form = RegistrationForm()
    return render(request, 'accounts/register.html', {'form': form})


def send_verification_email(request, user):
    """Send an email with verification link."""
    token = user.verification_token
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    
    current_site = get_current_site(request)
    mail_subject = 'Verify your email address'
    message = render_to_string('accounts/verification_email.html', {
        'user': user,
        'domain': current_site.domain,
        'uid': uid,
        'token': token,
    })
    
    # In production, use real email settings
    # For development, console backend will print to terminal
    from django.utils import timezone
    import sys
    timestamp = timezone.now().isoformat()
    print(f"[{timestamp}] DEBUG: Attempting to send verification email to {user.email}")
    print(f"[{timestamp}] DEBUG: Using email backend: {settings.EMAIL_BACKEND}")
    print(f"[{timestamp}] DEBUG: From email: {settings.DEFAULT_FROM_EMAIL if hasattr(settings, 'DEFAULT_FROM_EMAIL') else 'noreply@example.com'}")
    print(f"[{timestamp}] DEBUG: Current site domain: {current_site.domain}")
    print(f"[{timestamp}] DEBUG: Verification token: {token}")
    print(f"[{timestamp}] DEBUG: UID: {uid}")
    print(f"[{timestamp}] DEBUG: Email subject: {mail_subject}")
    print(f"[{timestamp}] DEBUG: Email body preview: {message[:200]}...")
    try:
        send_mail(
            mail_subject,
            message,
            settings.DEFAULT_FROM_EMAIL if hasattr(settings, 'DEFAULT_FROM_EMAIL') else 'noreply@example.com',
            [user.email],
            html_message=message,
            fail_silently=False,
        )
        print(f"[{timestamp}] DEBUG: Email sent successfully to {user.email}")
    except Exception as e:
        print(f"[{timestamp}] DEBUG: Email sending failed: {e}")
        import traceback
        traceback.print_exc(file=sys.stdout)


def verify_email(request, uidb64, token):
    from django.utils import timezone
    import sys
    timestamp = timezone.now().isoformat()
    print(f"[{timestamp}] DEBUG: verify_email called with uidb64={uidb64}, token={token}")
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        print(f"[{timestamp}] DEBUG: Decoded uid={uid}")
        user = User.objects.get(pk=uid)
        print(f"[{timestamp}] DEBUG: Found user: {user.email}, verification_token={user.verification_token}, is_email_verified={user.is_email_verified}")
    except (TypeError, ValueError, OverflowError, User.DoesNotExist) as e:
        print(f"[{timestamp}] DEBUG: Exception decoding uid or user not found: {e}")
        user = None
    
    if user is not None and str(user.verification_token) == token:
        print(f"[{timestamp}] DEBUG: Token matches. Checking expiry...")
        # Check token expiry (optional, e.g., 24 hours)
        token_age = timezone.now() - user.verification_token_created_at
        print(f"[{timestamp}] DEBUG: Token age: {token_age.total_seconds()} seconds")
        if token_age.total_seconds() > 24 * 3600:  # 24 hours
            print(f"[{timestamp}] DEBUG: Token expired, generating new token and resending email.")
            # Generate new token and resend email
            user.generate_new_verification_token()
            send_verification_email(request, user)
            messages.warning(request, 'Verification link expired. A new link has been sent to your email.')
            return redirect('login')
        
        user.is_email_verified = True
        user.save()
        print(f"[{timestamp}] DEBUG: Email verified successfully for {user.email}")
        messages.success(request, 'Email verified successfully! You can now log in.')
        return redirect('login')
    else:
        print(f"[{timestamp}] DEBUG: Invalid verification link. User is None? {user is None}")
        if user is not None:
            print(f"[{timestamp}] DEBUG: User token: {user.verification_token}, provided token: {token}")
        messages.error(request, 'Invalid verification link.')
        return redirect('login')


def custom_login(request):
    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            if not user.is_email_verified:
                messages.error(request, 'Please verify your email before logging in.')
                return redirect('login')
            login(request, user)
            return redirect(settings.LOGIN_REDIRECT_URL)
    else:
        form = AuthenticationForm()
    return render(request, 'accounts/login.html', {'form': form})


@login_required
def dashboard(request):
    """Dashboard with tabs for dashboard and search."""
    return render(request, 'accounts/dashboard.html', {'user': request.user})

@login_required
def profile(request):
    # Keep for backward compatibility, redirect to dashboard
    return redirect('dashboard')


def resend_verification(request):
    if request.method == 'POST':
        email = request.POST.get('email')
        try:
            user = User.objects.get(email=email)
            if user.is_email_verified:
                messages.info(request, 'Email already verified.')
            else:
                user.generate_new_verification_token()
                send_verification_email(request, user)
                messages.success(request, 'Verification email resent. Please check your inbox.')
        except User.DoesNotExist:
            messages.error(request, 'No account found with that email.')
        return redirect('login')
    return render(request, 'accounts/resend_verification.html')
