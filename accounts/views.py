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
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
import uuid

from .models import User, Patent, Entity, Analysis
from .forms import RegistrationForm
from django.db.models import Q
import json


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


def patent_list(request):
    """
    Display a paginated list of patents.
    Users can click on a patent to view more details.
    """
    # Get all patents with their analysis (if any), ordered by publication date (newest first)
    patents_list = Patent.objects.select_related('analysis').all().order_by('-publication_date', '-patent_id')
    
    # Number of patents per page
    items_per_page = 10
    
    # Paginate the results
    paginator = Paginator(patents_list, items_per_page)
    
    # Get the current page number from the request
    page = request.GET.get('page', 1)
    
    try:
        patents = paginator.page(page)
    except PageNotAnInteger:
        # If page is not an integer, deliver first page
        patents = paginator.page(1)
    except EmptyPage:
        # If page is out of range, deliver last page
        patents = paginator.page(paginator.num_pages)
    
    return render(request, 'accounts/patent_list.html', {
        'patents': patents,
        'search_query': request.GET.get('q', ''),
        'search_inventor': request.GET.get('inventor', ''),
        'search_applicant': request.GET.get('applicant', ''),
        'search_assignee': request.GET.get('assignee', ''),
    })


def patent_detail(request, patent_id):
    """
    Display detailed information about a specific patent.
    """
    patent = get_object_or_404(Patent, patent_id=patent_id)
    is_analysed = hasattr(patent, 'analysis')
    
    return render(request, 'accounts/patent_detail.html', {
        'patent': patent,
        'is_analysed': is_analysed,
    })


def analyse_patent(request, patent_id):
    """
    Create an analysis entry for a patent.
    For now, this is a simple placeholder that marks the patent as analysed.
    """
    patent = get_object_or_404(Patent, patent_id=patent_id)
    
    # Check if already analysed
    if not hasattr(patent, 'analysis'):
        # Create a new analysis entry
        Analysis.objects.create(patent=patent)
        messages.success(request, f'Patent {patent.publication_number} has been analysed.')
    else:
        messages.info(request, f'Patent {patent.publication_number} is already analysed.')
    
    # Redirect back to the patent detail page
    return redirect('patent_detail', patent_id=patent_id)


def autocomplete_entities(request):
    """
    Autocomplete view for searching inventors, applicants, and assignees.
    Returns JSON list of matching entity names.
    Searches both the Entity table and Patent JSON fields for comprehensive results.
    """
    query = request.GET.get('q', '')
    entity_type = request.GET.get('type', 'all')  # 'inventor', 'applicant', 'assignee', or 'all'
    
    if len(query) < 2:
        return HttpResponse(json.dumps([]), content_type='application/json')
    
    results = set()
    
    # Search in Entity table first
    if entity_type == 'all':
        entities = Entity.objects.filter(
            Q(name__icontains=query)
        ).distinct().values_list('name', flat=True)[:10]
    else:
        entities = Entity.objects.filter(
            Q(name__icontains=query) & Q(entity_type=entity_type)
        ).distinct().values_list('name', flat=True)[:10]
    
    for e in entities:
        results.add(e)
    
    # Also search in Patent JSON fields for inventors and applicants
    if entity_type in ['all', 'inventor']:
        # Search inventors in Patent model
        patents_with_inventor = Patent.objects.filter(
            inventors__isnull=False
        ).values_list('inventors', flat=True)[:100]
        
        for inventors_list in patents_with_inventor:
            if inventors_list and isinstance(inventors_list, list):
                for inventor in inventors_list:
                    if isinstance(inventor, dict):
                        # Handle dict format with first_name and last_name
                        first_name = inventor.get('first_name', '') or ''
                        last_name = inventor.get('last_name', '') or ''
                        full_name = f"{first_name} {last_name}".strip()
                        if full_name and query.lower() in full_name.lower():
                            results.add(full_name)
    
    if entity_type in ['all', 'applicant']:
        # Search applicants in Patent model
        patents_with_applicant = Patent.objects.filter(
            applicants__isnull=False
        ).values_list('applicants', flat=True)[:100]
        
        for applicants_list in patents_with_applicant:
            if applicants_list and isinstance(applicants_list, list):
                for applicant in applicants_list:
                    if isinstance(applicant, dict):
                        # For applicants, use organization if first/last name are not available
                        organization = applicant.get('organization', '')
                        first_name = applicant.get('first_name', '') or ''
                        last_name = applicant.get('last_name', '') or ''
                        
                        if first_name or last_name:
                            full_name = f"{first_name} {last_name}".strip()
                            if full_name and query.lower() in full_name.lower():
                                results.add(full_name)
                        elif organization and query.lower() in organization.lower():
                            results.add(organization)
    
    # Convert to sorted list and return as JSON (limit to 10)
    sorted_results = sorted(list(results))[:10]
    return HttpResponse(json.dumps(sorted_results), content_type='application/json')


def search_patents(request):
    """
    Search patents by various fields including inventor, applicant, and assignee.
    """
    query = request.GET.get('q', '')
    inventor = request.GET.get('inventor', '')
    applicant = request.GET.get('applicant', '')
    assignee = request.GET.get('assignee', '')  # Owner
    
    # Start with all patents
    patents = Patent.objects.all()
    
    # Filter by general query (title, abstract, publication number)
    if query:
        patents = patents.filter(
            Q(title__icontains=query) |
            Q(abstract__icontains=query) |
            Q(publication_number__icontains=query)
        )
    
    # Filter by inventor
    if inventor:
        patents = patents.filter(
            Q(inventors__icontains=inventor)
        ).distinct()
    
    # Filter by applicant
    if applicant:
        patents = patents.filter(
            Q(applicants__icontains=applicant)
        ).distinct()
    
    # Filter by assignee (owner) - using Entity model
    if assignee:
        # Use the reverse ManyToMany relation from Patent to Entity
        # The Entity model has patents=ManyToManyField(Patent), so we access via 'entities'
        patents = patents.filter(
            entities__name__icontains=assignee,
            entities__entity_type='assignee'
        ).distinct()
    
    # Order by publication date (newest first)
    patents = patents.order_by('-publication_date', '-patent_id')
    
    # Paginate results
    items_per_page = 10
    paginator = Paginator(patents, items_per_page)
    page = request.GET.get('page', 1)
    
    try:
        patents_page = paginator.page(page)
    except PageNotAnInteger:
        patents_page = paginator.page(1)
    except EmptyPage:
        patents_page = paginator.page(paginator.num_pages)
    
    return render(request, 'accounts/patent_list.html', {
        'patents': patents_page,
        'search_query': query,
        'search_inventor': inventor,
        'search_applicant': applicant,
        'search_assignee': assignee,
    })
