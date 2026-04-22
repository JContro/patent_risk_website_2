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
from django.urls import reverse
from urllib.parse import urlencode
import uuid
import threading

from .models import User, Patent, Entity, Analysis, SavedSearch, DashboardCache
from .forms import RegistrationForm
from django.db.models import Q
from django.conf import settings
from .openrouter_service import analyse_patent_with_openrouter
import json
import re


def _parse_json_response(raw_response):
    """
    Robustly parse JSON from API response, handling various edge cases.
    Returns a normalized list of risk objects with consistent keys and types.
    """
    if not raw_response:
        return None
    
    # Try direct JSON parse first
    try:
        data = json.loads(raw_response)
    except json.JSONDecodeError:
        # Try to extract JSON from response that might have extra text
        json_match = re.search(r'\[.*\]', raw_response, re.DOTALL)
        if json_match:
            try:
                data = json.loads(json_match.group(0))
            except json.JSONDecodeError:
                return None
        else:
            return None
    
    # Normalize to a list
    if isinstance(data, dict):
        # If the response is a dict with a 'risks' or 'results' key, use that
        if 'risks' in data:
            data = data['risks']
        elif 'results' in data:
            data = data['results']
        elif 'items' in data:
            data = data['items']
        else:
            # Single item dict - wrap in list
            data = [data]
    elif not isinstance(data, list):
        return None
    
    # Normalize each risk item to have consistent keys
    normalized_risks = []
    for item in data:
        if not isinstance(item, dict):
            continue
        
        # Map common alternative key names to standard keys
        snippet = (
            item.get('snippet') or
            item.get('text') or
            item.get('quote') or
            item.get('matched_text') or
            item.get('content', '')
        )
        
        risk = (
            item.get('risk') or
            item.get('risk_type') or
            item.get('category') or
            item.get('type', '')
        )
        
        # Ensure confidence_score is a float between 0 and 1
        confidence = item.get('confidence_score') or item.get('confidence') or item.get('score')
        if confidence is not None:
            try:
                confidence = float(confidence)
                # Clamp to valid range
                confidence = max(0.0, min(1.0, confidence))
            except (TypeError, ValueError):
                confidence = 0.5  # Default if invalid
        else:
            confidence = 0.5
        
        # Only add if we have at least a snippet
        if snippet:
            normalized_risks.append({
                'snippet': str(snippet),
                'risk': str(risk),
                'explanation': str(item.get('explanation', '')),
                'confidence_score': confidence
            })
    
    # Return the normalized list (including empty list for "no risks found" case)
    # This preserves [] from the API rather than converting to None
    return normalized_risks


def landing(request):
    """Landing page - shows login/register for unauthenticated users, redirects to dashboard for authenticated."""
    if request.user.is_authenticated:
        return redirect('dashboard')
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
        username = request.POST.get('username')
        password = request.POST.get('password')
        
        # Try to find user by username first, then by email
        user = None
        user_obj = None
        try:
            # Check if it's an email address
            if '@' in username:
                user_obj = User.objects.get(email=username)
                user = authenticate(request, username=user_obj.username, password=password)
            else:
                user = authenticate(request, username=username, password=password)
        except User.DoesNotExist:
            pass
        
        if user is not None:
            if not user.is_email_verified:
                messages.error(request, 'Please verify your email before logging in.')
                return redirect('login')
            login(request, user)
            return redirect(settings.LOGIN_REDIRECT_URL)
        
        # Authentication failed - show error
        messages.error(request, 'Invalid username or password.')
        return redirect('login')
    else:
        form = AuthenticationForm()
    return render(request, 'accounts/login.html', {'form': form})


@login_required
def dashboard(request):
    """Dashboard with tabs for dashboard, search, and company profile.
    Uses cached data for performance, with fallback to full computation.
    """
    from collections import Counter
    from django.db.models import Count
    import plotly.utils
    
    # Get all saved searches for the current user (for the dropdown)
    saved_searches = SavedSearch.objects.filter(user=request.user).order_by('-created_at')
    
    # Get the selected saved search from query params
    selected_search_id = request.GET.get('search_id')
    
    # Try to get cached data first
    cache = None
    selected_search = None
    if selected_search_id:
        try:
            selected_search = SavedSearch.objects.get(id=selected_search_id, user=request.user)
            cache = DashboardCache.objects.filter(user=request.user, saved_search=selected_search).first()
        except SavedSearch.DoesNotExist:
            selected_search = None
    else:
        cache = DashboardCache.objects.filter(user=request.user, saved_search=None, is_global=True).first()
    
    # If cache exists, use it for fast rendering
    if cache:
        cache_data = cache.cache_data
        total_patents = cache.patent_count
        patents_with_risks = cache.risks_count
        patents_with_military = cache.patents_with_military
        patents_with_surveillance = cache.patents_with_surveillance
        patents_with_online_manipulation = cache.patents_with_online_manipulation
        
        # Get total patents in search (need to recalculate for this)
        total_patents_in_search = _get_total_patents_for_search(selected_search, selected_search_id)
        
        # Calculate percentages
        if total_patents > 0:
            military_percentage = round((patents_with_military / total_patents) * 100, 1)
            surveillance_percentage = round((patents_with_surveillance / total_patents) * 100, 1)
            online_manipulation_percentage = round((patents_with_online_manipulation / total_patents) * 100, 1)
            risks_percentage = round((patents_with_risks / total_patents) * 100, 1)
        else:
            military_percentage = 0
            surveillance_percentage = 0
            online_manipulation_percentage = 0
            risks_percentage = 0
        
        # Build display names for searches
        searches_with_display = []
        for search in saved_searches:
            if search.name:
                display_name = search.name
            elif search.applicant:
                display_name = f"Applicant: {search.applicant}"
            elif search.assignee:
                display_name = f"Assignee: {search.assignee}"
            elif search.inventor:
                display_name = f"Inventor: {search.inventor}"
            elif search.query:
                display_name = f"Search: {search.query}"
            else:
                display_name = f"Search #{search.id}"
            
            searches_with_display.append({
                'id': search.id,
                'display_name': display_name[:50],
            })
        
        # Reconstruct patent_risk_data from cache directly (no database query needed)
        # We store minimal patent data in cache to avoid fetching full Patent objects
        from accounts.models import Patent
        
        patent_risk_data = []
        for p in cache_data.get('patent_risk_data', []):
            # Create a lightweight dict with patent data instead of fetching from DB
            patent_risk_data.append({
                'patent_id': p.get('patent_id'),
                'publication_number': p.get('publication_number', ''),
                'title': p.get('title', ''),
                'publication_date': p.get('publication_date'),
                'risks': p.get('risks', []),
                'has_risks': p.get('has_risks', False),
                'has_military': p.get('has_military', False),
                'has_surveillance': p.get('has_surveillance', False),
            })
        
        context = {
            'user': request.user,
            'saved_searches': searches_with_display,
            'selected_search': selected_search,
            'total_patents': total_patents,
            'patents_with_risks': patents_with_risks,
            'total_risks': patents_with_risks,
            'patents_with_military': patents_with_military,
            'patents_with_surveillance': patents_with_surveillance,
            'patents_with_online_manipulation': patents_with_online_manipulation,
            'online_manipulation_percentage': online_manipulation_percentage,
            'military_percentage': military_percentage,
            'surveillance_percentage': surveillance_percentage,
            'risks_percentage': risks_percentage,
            'total_patents_in_search': total_patents_in_search,
            'risk_labels_json': json.dumps(cache_data.get('risk_labels', [])),
            'risk_values_json': json.dumps(cache_data.get('risk_values', [])),
            'time_labels_json': json.dumps(cache_data.get('time_labels', [])),
            'time_values_json': json.dumps(cache_data.get('time_values', [])),
            'patent_risk_data': patent_risk_data,
            'cache_status': f'Cached at {cache.cached_at.strftime("%Y-%m-%d %H:%M:%S")}' if cache else 'No cache',
        }
        return render(request, 'accounts/dashboard.html', context)
    
    # No cache - compute from scratch (original slow path)
    return _dashboard_compute(request, saved_searches, selected_search_id, selected_search)


def _get_total_patents_for_search(selected_search, selected_search_id):
    """Get total patent count for a search without full analysis."""
    from django.db.models import Q
    q = Q()
    
    if selected_search and selected_search_id:
        if selected_search.applicant:
            q |= Q(applicants__icontains=selected_search.applicant)
        if selected_search.inventor:
            q |= Q(inventors__icontains=selected_search.inventor)
        if selected_search.assignee:
            q |= Q(entities__name__icontains=selected_search.assignee, entities__entity_type='assignee')
        if selected_search.query:
            q |= Q(title__icontains=selected_search.query)
    
    if q:
        return Patent.objects.filter(q).distinct().count()
    return Analysis.objects.count()


def _dashboard_compute(request, saved_searches, selected_search_id, selected_search):
    """Original dashboard computation logic - kept for fallback when no cache exists."""
    from collections import Counter
    from accounts.models import Patent
    # Keywords to detect military/surveillance from parsed_risks (from API analysis)
    military_risk_keywords = ['military', 'weapon', 'defense', 'ordnance', 'munition', 'warfare', 'combat', 'armi', '武器', '軍', 'security', 'attack', 'threat']
    surveillance_risk_keywords = ['surveillance', 'monitoring', 'tracking', 'recognit', 'spy', 'intercept', 'camer', 'sensor', '監視', '偵查', 'face recognition', 'biometric', 'privacy', 'data collection']
    online_manipulation_keywords = ['manipulation', 'manipulat', 'cognitive bias', 'emotional vulnerab', 'psychographic', 'microtarget', 'dark pattern', 'covert influence', 'exploit vulnerab', 'personalized pricing', 'urgency tactic', 'behavioral nudge', 'addictive behav', 'algorithmic management', 'disinformation', 'polarization']
    
    # Get analyses - either filtered by selected search or all
    total_patents_in_search = 0  # Total patents from the search
    if selected_search_id:
        try:
            selected_search = SavedSearch.objects.get(id=selected_search_id, user=request.user)
            
            q = Q()
            
            if selected_search.applicant:
                q |= Q(applicants__icontains=selected_search.applicant)
            if selected_search.inventor:
                q |= Q(inventors__icontains=selected_search.inventor)
            if selected_search.assignee:
                q |= Q(entities__name__icontains=selected_search.assignee, entities__entity_type='assignee')
            if selected_search.query:
                q |= Q(title__icontains=selected_search.query)
            
            if q:
                matching_patents = Patent.objects.filter(q).distinct()
                total_patents_in_search = matching_patents.count()
                
                patent_ids = list(matching_patents.values_list('patent_id', flat=True))
                analyses = Analysis.objects.select_related('patent').filter(patent_id__in=patent_ids)
            else:
                analyses = Analysis.objects.select_related('patent').all()
                total_patents_in_search = analyses.count()
                
        except SavedSearch.DoesNotExist:
            analyses = Analysis.objects.select_related('patent').all()
            selected_search = None
            total_patents_in_search = 0
    else:
        analyses = Analysis.objects.select_related('patent').all()
        selected_search = None
        total_patents_in_search = analyses.count()
    
    analyses = list(analyses)
    
    total_patents = len(analyses)
    patents_with_risks = 0
    total_risks = 0
    risk_counts = Counter()
    risks_by_month = Counter()
    patents_with_military = 0
    patents_with_surveillance = 0
    patents_with_online_manipulation = 0
    patent_risk_data = []
    
    for analysis in analyses:
        patent = analysis.patent
        parsed_risks = analysis.parsed_risks
        
        has_military = False
        has_surveillance = False
        has_online_manipulation = False
        
        if parsed_risks and isinstance(parsed_risks, list) and len(parsed_risks) > 0:
            for risk in parsed_risks:
                risk_type = risk.get('risk', '').lower()
                if any(kw in risk_type for kw in military_risk_keywords):
                    has_military = True
                if any(kw in risk_type for kw in surveillance_risk_keywords):
                    has_surveillance = True
                if any(kw in risk_type for kw in online_manipulation_keywords):
                    has_online_manipulation = True
        
        if has_military:
            patents_with_military += 1
        if has_surveillance:
            patents_with_surveillance += 1
        if has_online_manipulation:
            patents_with_online_manipulation += 1
        
        if parsed_risks and isinstance(parsed_risks, list) and len(parsed_risks) > 0:
            patents_with_risks += 1
            total_risks += len(parsed_risks)
            
            for risk in parsed_risks:
                risk_type = risk.get('risk', 'Unknown')
                risk_counts[risk_type] += 1
            
            if patent.publication_date:
                month_key = patent.publication_date.strftime('%Y-%m')
                risks_by_month[month_key] += 1
            
            patent_risk_data.append({
                'patent_id': patent.patent_id,
                'publication_number': patent.publication_number,
                'title': patent.title,
                'publication_date': patent.publication_date,
                'risks': parsed_risks,
                'has_risks': True,
                'has_military': has_military,
                'has_surveillance': has_surveillance,
                'has_online_manipulation': has_online_manipulation,
            })
    
    if total_patents > 0:
        military_percentage = round((patents_with_military / total_patents) * 100, 1)
        surveillance_percentage = round((patents_with_surveillance / total_patents) * 100, 1)
        online_manipulation_percentage = round((patents_with_online_manipulation / total_patents) * 100, 1)
        risks_percentage = round((patents_with_risks / total_patents) * 100, 1)
    else:
        military_percentage = 0
        surveillance_percentage = 0
        online_manipulation_percentage = 0
        risks_percentage = 0
    
    risk_labels = list(risk_counts.keys())
    risk_values = list(risk_counts.values())
    
    if risks_by_month:
        sorted_months = sorted(risks_by_month.keys())
        time_labels = sorted_months
        time_values = [risks_by_month[m] for m in sorted_months]
    else:
        time_labels = []
        time_values = []
    
    searches_with_display = []
    for search in saved_searches:
        if search.name:
            display_name = search.name
        elif search.applicant:
            display_name = f"Applicant: {search.applicant}"
        elif search.assignee:
            display_name = f"Assignee: {search.assignee}"
        elif search.inventor:
            display_name = f"Inventor: {search.inventor}"
        elif search.query:
            display_name = f"Search: {search.query}"
        else:
            display_name = f"Search #{search.id}"
        
        searches_with_display.append({
            'id': search.id,
            'display_name': display_name[:50],
        })
    
    context = {
        'user': request.user,
        'saved_searches': searches_with_display,
        'selected_search': selected_search,
        'total_patents': total_patents,
        'patents_with_risks': patents_with_risks,
        'total_risks': total_risks,
        'patents_with_military': patents_with_military,
        'patents_with_surveillance': patents_with_surveillance,
        'patents_with_online_manipulation': patents_with_online_manipulation,
        'military_percentage': military_percentage,
        'surveillance_percentage': surveillance_percentage,
        'risks_percentage': risks_percentage,
        'total_patents_in_search': total_patents_in_search,
        'risk_labels_json': json.dumps(risk_labels),
        'risk_values_json': json.dumps(risk_values),
        'time_labels_json': json.dumps(time_labels),
        'time_values_json': json.dumps(time_values),
        'patent_risk_data': patent_risk_data[:50],
        'cache_status': 'No cache - computed fresh',
    }
    
    return render(request, 'accounts/dashboard.html', context)


@login_required
def recalculate_cache(request):
    """
    Recalculate dashboard cache for the current user.
    Can recalculate for a specific saved search or all patents (global).
    Returns JSON response with status.
    """
    from django.http import JsonResponse
    from django.views.decorators.http import require_POST
    from django.utils import timezone
    from collections import Counter
    
    if request.method != 'POST':
        return JsonResponse({'error': 'POST method required'}, status=405)
    
    search_id = request.POST.get('search_id') or request.GET.get('search_id')
    
    # Get or create cache entry
    if search_id:
        try:
            saved_search = SavedSearch.objects.get(id=search_id, user=request.user)
            cache, created = DashboardCache.objects.get_or_create(
                user=request.user,
                saved_search=saved_search,
                defaults={'is_global': False}
            )
        except SavedSearch.DoesNotExist:
            return JsonResponse({'error': 'Saved search not found'}, status=404)
    else:
        # Global cache for all patents
        cache, created = DashboardCache.objects.get_or_create(
            user=request.user,
            saved_search=None,
            defaults={'is_global': True}
        )
    
    # Build Q objects for filtering
    q = Q()
    selected_search = None
    total_patents_in_search = 0
    
    if search_id:
        try:
            selected_search = SavedSearch.objects.get(id=search_id, user=request.user)
            
            if selected_search.applicant:
                q |= Q(applicants__icontains=selected_search.applicant)
            if selected_search.inventor:
                q |= Q(inventors__icontains=selected_search.inventor)
            if selected_search.assignee:
                q |= Q(entities__name__icontains=selected_search.assignee, entities__entity_type='assignee')
            if selected_search.query:
                q |= Q(title__icontains=selected_search.query)
            
            if q:
                matching_patents = Patent.objects.filter(q).distinct()
                total_patents_in_search = matching_patents.count()
                patent_ids = list(matching_patents.values_list('patent_id', flat=True))
                analyses = Analysis.objects.select_related('patent').filter(patent_id__in=patent_ids)
            else:
                analyses = Analysis.objects.select_related('patent').all()
                total_patents_in_search = analyses.count()
        except SavedSearch.DoesNotExist:
            analyses = Analysis.objects.select_related('patent').all()
            total_patents_in_search = analyses.count()
    else:
        analyses = Analysis.objects.select_related('patent').all()
        total_patents_in_search = analyses.count()
    
    analyses = list(analyses)
    
    # Compute stats (same logic as dashboard)
    total_patents = len(analyses)
    patents_with_risks = 0
    total_risks = 0
    risk_counts = Counter()
    risks_by_month = Counter()
    patents_with_military = 0
    patents_with_surveillance = 0
    patents_with_online_manipulation = 0
    patent_risk_data = []
    
    military_risk_keywords = ['military', 'weapon', 'defense', 'ordnance', 'munition', 'warfare', 'combat', 'armi', '武器', '軍', 'security', 'attack', 'threat']
    surveillance_risk_keywords = ['surveillance', 'monitoring', 'tracking', 'recognit', 'spy', 'intercept', 'camer', 'sensor', '監視', '偵查', 'face recognition', 'biometric', 'privacy', 'data collection']
    online_manipulation_keywords = ['manipulation', 'manipulat', 'cognitive bias', 'emotional vulnerab', 'psychographic', 'microtarget', 'dark pattern', 'covert influence', 'exploit vulnerab', 'personalized pricing', 'urgency tactic', 'behavioral nudge', 'addictive behav', 'algorithmic management', 'disinformation', 'polarization']
    
    for analysis in analyses:
        patent = analysis.patent
        parsed_risks = analysis.parsed_risks
        
        has_military = False
        has_surveillance = False
        has_online_manipulation = False
        
        if parsed_risks and isinstance(parsed_risks, list) and len(parsed_risks) > 0:
            for risk in parsed_risks:
                risk_type = risk.get('risk', '').lower()
                if any(kw in risk_type for kw in military_risk_keywords):
                    has_military = True
                if any(kw in risk_type for kw in surveillance_risk_keywords):
                    has_surveillance = True
                if any(kw in risk_type for kw in online_manipulation_keywords):
                    has_online_manipulation = True
        
        if has_military:
            patents_with_military += 1
        if has_surveillance:
            patents_with_surveillance += 1
        if has_online_manipulation:
            patents_with_online_manipulation += 1
        
        if parsed_risks and isinstance(parsed_risks, list) and len(parsed_risks) > 0:
            patents_with_risks += 1
            total_risks += len(parsed_risks)
            
            for risk in parsed_risks:
                risk_type = risk.get('risk', 'Unknown')
                risk_counts[risk_type] += 1
            
            if patent.publication_date:
                month_key = patent.publication_date.strftime('%Y-%m')
                risks_by_month[month_key] += 1
            
            patent_risk_data.append({
                'patent_id': patent.patent_id,
                'publication_number': patent.publication_number,
                'title': patent.title,
                'publication_date': patent.publication_date,
                'risks': parsed_risks,
                'has_risks': True,
                'has_military': has_military,
                'has_surveillance': has_surveillance,
                'has_online_manipulation': has_online_manipulation,
            })
    
    # Calculate percentages
    if total_patents > 0:
        military_percentage = round((patents_with_military / total_patents) * 100, 1)
        surveillance_percentage = round((patents_with_surveillance / total_patents) * 100, 1)
        online_manipulation_percentage = round((patents_with_online_manipulation / total_patents) * 100, 1)
        risks_percentage = round((patents_with_risks / total_patents) * 100, 1)
    else:
        military_percentage = 0
        surveillance_percentage = 0
        online_manipulation_percentage = 0
        risks_percentage = 0
    
    # Prepare cache data
    cache_data = {
        'risk_labels': list(risk_counts.keys()),
        'risk_values': list(risk_counts.values()),
        'time_labels': sorted(risks_by_month.keys()),
        'time_values': [risks_by_month[m] for m in sorted(risks_by_month.keys())],
        'patent_risk_data': patent_risk_data[:50],  # Limit to 50
    }
    
    # Update cache
    cache.cache_data = cache_data
    cache.cached_at = timezone.now()
    cache.patent_count = total_patents
    cache.risks_count = total_risks
    cache.patents_with_military = patents_with_military
    cache.patents_with_surveillance = patents_with_surveillance
    cache.patents_with_online_manipulation = patents_with_online_manipulation
    cache.save()
    
    return JsonResponse({
        'success': True,
        'cached_at': cache.cached_at.isoformat(),
        'patent_count': total_patents,
        'risks_count': total_risks,
        'patents_with_military': patents_with_military,
        'patents_with_surveillance': patents_with_surveillance,
        'patents_with_online_manipulation': patents_with_online_manipulation,
    })

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
    
    # Get saved searches for the user if authenticated
    saved_searches = []
    current_saved_search = None
    if request.user.is_authenticated:
        saved_searches = SavedSearch.objects.filter(user=request.user)[:10]
        # Check if current search matches any saved search
        query = request.GET.get('q', '')
        inventor = request.GET.get('inventor', '')
        applicant = request.GET.get('applicant', '')
        assignee = request.GET.get('assignee', '')
        for saved in saved_searches:
            if (saved.query == query and saved.inventor == inventor and
                saved.applicant == applicant and saved.assignee == assignee):
                current_saved_search = saved
                break
    
    return render(request, 'accounts/patent_list.html', {
        'patents': patents,
        'search_query': request.GET.get('q', ''),
        'search_inventor': request.GET.get('inventor', ''),
        'search_applicant': request.GET.get('applicant', ''),
        'search_assignee': request.GET.get('assignee', ''),
        'saved_searches': saved_searches,
        'current_saved_search': current_saved_search,
    })


def patent_detail(request, patent_id):
    """
    Display detailed information about a specific patent.
    """
    patent = get_object_or_404(Patent, patent_id=patent_id)
    is_analysed = hasattr(patent, 'analysis')
    analysis = getattr(patent, 'analysis', None)
    
    return render(request, 'accounts/patent_detail.html', {
        'patent': patent,
        'is_analysed': is_analysed,
        'analysis': analysis,
    })


@login_required
def analyse_patent(request, patent_id):
    """
    Create an analysis entry for a patent by sending it to OpenRouter API.
    The raw response from OpenRouter is saved in the database.
    """
    patent = get_object_or_404(Patent, patent_id=patent_id)
    
    # Get the prompt template from settings
    prompt_template = getattr(settings, 'PATENT_ANALYSIS_PROMPT', '')
    
    if not prompt_template:
        messages.error(request, 'Analysis prompt not configured. Please contact the administrator.')
        return redirect('patent_detail', patent_id=patent_id)
    
    # Check if API key is configured
    api_key = getattr(settings, 'OPENROUTER_API_KEY', '')
    if not api_key:
        messages.error(request, 'OpenRouter API key not configured. Please contact the administrator.')
        return redirect('patent_detail', patent_id=patent_id)
    
    try:
        # Call the OpenRouter API to analyze the patent
        raw_response = analyse_patent_with_openrouter(patent, prompt_template)
        
        # Parse the JSON response from the API
        parsed_risks = None
        if raw_response:
            parsed_risks = _parse_json_response(raw_response)
        
        # Create or update the analysis entry with the raw response and parsed risks
        analysis, created = Analysis.objects.update_or_create(
            patent=patent,
            defaults={
                'raw_response': raw_response,
                'parsed_risks': parsed_risks
            }
        )
        
        if created:
            messages.success(request, f'Patent {patent.publication_number} has been analysed.')
        else:
            messages.success(request, f'Analysis for patent {patent.publication_number} has been updated.')
            
    except Exception as e:
        messages.error(request, f'Error analyzing patent: {str(e)}')
    
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
    Supports multiple values (comma-separated) and date range filtering.
    Shows search form if no query parameters, otherwise shows results.
    """
    from datetime import datetime
    
    query = request.GET.get('q', '')
    inventor = request.GET.get('inventor', '')
    applicant = request.GET.get('applicant', '')
    assignee = request.GET.get('assignee', '')  # Owner
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    
    # Check if any search parameters are provided
    has_search = query or inventor or applicant or assignee or date_from or date_to
    
    # Get saved searches for the user if authenticated
    saved_searches = []
    current_saved_search = None
    if request.user.is_authenticated:
        saved_searches = SavedSearch.objects.filter(user=request.user)[:10]
        # Check if current search matches any saved search
        for saved in saved_searches:
            if (saved.query == query and saved.inventor == inventor and
                saved.applicant == applicant and saved.assignee == assignee):
                current_saved_search = saved
                break
    
    if not has_search:
        # Show search form (empty)
        return render(request, 'accounts/search.html', {
            'search_query': '',
            'search_inventor': '',
            'search_applicant': '',
            'search_assignee': '',
            'date_from': '',
            'date_to': '',
            'saved_searches': saved_searches,
            'current_saved_search': current_saved_search,
        })
    
    # Start with all patents
    patents = Patent.objects.all()
    
    # Filter by general query (title, abstract, publication number)
    if query:
        patents = patents.filter(
            Q(title__icontains=query) |
            Q(abstract__icontains=query) |
            Q(publication_number__icontains=query)
        )
    
    # Filter by multiple inventors (comma-separated) - OR logic
    if inventor:
        inventor_list = [inv.strip() for inv in inventor.split(',') if inv.strip()]
        if inventor_list:
            inventor_q = Q()
            for inv in inventor_list:
                inventor_q |= Q(inventors__icontains=inv)
            patents = patents.filter(inventor_q).distinct()
    
    # Filter by multiple applicants (comma-separated) - OR logic
    if applicant:
        applicant_list = [app.strip() for app in applicant.split(',') if app.strip()]
        if applicant_list:
            applicant_q = Q()
            for app in applicant_list:
                applicant_q |= Q(applicants__icontains=app)
            patents = patents.filter(applicant_q).distinct()
    
    # Filter by multiple assignees (owners) - OR logic
    if assignee:
        assignee_list = [ass.strip() for ass in assignee.split(',') if ass.strip()]
        if assignee_list:
            assignee_q = Q()
            for ass in assignee_list:
                assignee_q |= Q(entities__name__icontains=ass)
            patents = patents.filter(
                assignee_q,
                entities__entity_type='assignee'
            ).distinct()
    
    # Filter by date range
    if date_from:
        try:
            from_date = datetime.strptime(date_from, '%Y-%m-%d').date()
            patents = patents.filter(publication_date__gte=from_date)
        except ValueError:
            pass  # Invalid date format, ignore
    
    if date_to:
        try:
            to_date = datetime.strptime(date_to, '%Y-%m-%d').date()
            patents = patents.filter(publication_date__lte=to_date)
        except ValueError:
            pass  # Invalid date format, ignore
    
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
        'date_from': date_from,
        'date_to': date_to,
        'saved_searches': saved_searches,
        'current_saved_search': current_saved_search,
    })


@login_required
def save_search(request):
    """
    Save the current search parameters for the logged-in user.
    """
    if request.method == 'POST':
        query = request.POST.get('query', '')
        inventor = request.POST.get('inventor', '')
        applicant = request.POST.get('applicant', '')
        assignee = request.POST.get('assignee', '')
        name = request.POST.get('name', '')
        
        # Check if at least one search parameter is provided
        if not (query or inventor or applicant or assignee):
            messages.error(request, 'Please provide at least one search parameter.')
            return redirect('search_patents')
        
        # Create the saved search
        saved_search = SavedSearch.objects.create(
            user=request.user,
            name=name if name else None,
            query=query,
            inventor=inventor,
            applicant=applicant,
            assignee=assignee,
        )
        
        messages.success(request, 'Search saved successfully!')
        
        # Redirect back to the search results
        params = {}
        if query:
            params['q'] = query
        if inventor:
            params['inventor'] = inventor
        if applicant:
            params['applicant'] = applicant
        if assignee:
            params['assignee'] = assignee
        
        url = reverse('patent_list')
        if params:
            url += '?' + urlencode(params)
        return redirect(url)
    
    return redirect('search_patents')


@login_required
def delete_saved_search(request, search_id):
    """
    Delete a saved search.
    """
    saved_search = get_object_or_404(SavedSearch, id=search_id, user=request.user)
    saved_search.delete()
    messages.success(request, 'Saved search deleted.')
    return redirect('search_patents')


def _run_background_analysis(saved_search_id, user_id):
    """
    Background task to analyze all patents from a saved search.
    This runs in a separate thread so the user isn't blocked.
    """
    # Re-setup Django inside the thread
    import django
    import os
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    django.setup()
    
    from django.contrib.auth import get_user_model
    from django.db import transaction
    
    User = get_user_model()
    
    try:
        # Get the saved search and user
        saved_search = SavedSearch.objects.get(id=saved_search_id, user_id=user_id)
        user = User.objects.get(id=user_id)
        
        # Re-run the search to get matching patents
        patents = Patent.objects.all()
        
        query = saved_search.query
        inventor = saved_search.inventor
        applicant = saved_search.applicant
        assignee = saved_search.assignee
        
        if query:
            patents = patents.filter(
                Q(title__icontains=query) |
                Q(abstract__icontains=query) |
                Q(publication_number__icontains=query)
            )
        
        if inventor:
            patents = patents.filter(
                Q(inventors__icontains=inventor)
            ).distinct()
        
        if applicant:
            patents = patents.filter(
                Q(applicants__icontains=applicant)
            ).distinct()
        
        if assignee:
            patents = patents.filter(
                entities__name__icontains=assignee,
                entities__entity_type='assignee'
            ).distinct()
        
        # Get patents that haven't been analyzed yet
        patents_to_analyze = list(patents.filter(analysis__isnull=True))
        
        # Get the prompt template from settings
        prompt_template = getattr(settings, 'PATENT_ANALYSIS_PROMPT', '')
        
        # Get API key
        api_key = getattr(settings, 'OPENROUTER_API_KEY', '')
        
        if not prompt_template or not api_key:
            print("Analysis not configured - missing prompt template or API key")
            return
        
        analyzed_count = 0
        for patent in patents_to_analyze:
            try:
                raw_response = analyse_patent_with_openrouter(patent, prompt_template)
                
                # Parse the JSON response from the API using robust parser
                parsed_risks = None
                if raw_response:
                    parsed_risks = _parse_json_response(raw_response)
                
                with transaction.atomic():
                    Analysis.objects.update_or_create(
                        patent=patent,
                        defaults={
                            'raw_response': raw_response,
                            'parsed_risks': parsed_risks
                        }
                    )
                analyzed_count += 1
                print(f"Analyzed patent {patent.patent_id} ({analyzed_count}/{len(patents_to_analyze)})")
            except Exception as e:
                print(f"Error analyzing patent {patent.patent_id}: {e}")
        
        print(f"Background analysis complete: {analyzed_count} patents analyzed")
        
    except SavedSearch.DoesNotExist:
        print(f"Saved search {saved_search_id} not found")
    except Exception as e:
        print(f"Background analysis failed: {e}")


@login_required
def analyse_all_patents(request):
    """
    Analyze all patents from a saved search.
    Takes a saved_search_id parameter and starts background analysis.
    """
    if request.method == 'POST':
        saved_search_id = request.POST.get('saved_search_id')
        saved_search = get_object_or_404(SavedSearch, id=saved_search_id, user=request.user)
        
        # Get the prompt template from settings to validate configuration
        prompt_template = getattr(settings, 'PATENT_ANALYSIS_PROMPT', '')
        api_key = getattr(settings, 'OPENROUTER_API_KEY', '')
        
        if not prompt_template or not api_key:
            messages.error(request, 'Analysis not configured. Please contact the administrator.')
            return redirect('search_patents')
        
        # Count patents to analyze
        query = saved_search.query
        inventor = saved_search.inventor
        applicant = saved_search.applicant
        assignee = saved_search.assignee
        
        patents = Patent.objects.all()
        
        if query:
            patents = patents.filter(
                Q(title__icontains=query) |
                Q(abstract__icontains=query) |
                Q(publication_number__icontains=query)
            )
        
        if inventor:
            patents = patents.filter(
                Q(inventors__icontains=inventor)
            ).distinct()
        
        if applicant:
            patents = patents.filter(
                Q(applicants__icontains=applicant)
            ).distinct()
        
        if assignee:
            patents = patents.filter(
                entities__name__icontains=assignee,
                entities__entity_type='assignee'
            ).distinct()
        
        patents_to_analyze = patents.filter(analysis__isnull=True)
        count = patents_to_analyze.count()
        
        if count == 0:
            messages.info(request, 'No new patents to analyze. All patents in this search have already been analyzed.')
        else:
            # Start background analysis in a separate thread
            thread = threading.Thread(
                target=_run_background_analysis,
                args=(saved_search.id, request.user.id)
            )
            thread.daemon = True
            thread.start()
            
            messages.success(request, f'Analysis started! {count} patents will be analyzed in the background. You can leave this page - the analysis will continue.')
        
        # Redirect back to the search results page
        params = {}
        if saved_search.query:
            params['q'] = saved_search.query
        if saved_search.inventor:
            params['inventor'] = saved_search.inventor
        if saved_search.applicant:
            params['applicant'] = saved_search.applicant
        if saved_search.assignee:
            params['assignee'] = saved_search.assignee
        
        url = reverse('search_patents')
        if params:
            url += '?' + urlencode(params)
        return redirect(url)
    
    return redirect('search_patents')
