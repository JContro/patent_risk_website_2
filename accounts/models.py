from django.db import models
from django.contrib.auth.models import AbstractUser

from django.utils import timezone
import uuid


class User(AbstractUser):
    email = models.EmailField(unique=True)
    is_email_verified = models.BooleanField(default=False)
    verification_token = models.UUIDField(default=uuid.uuid4, editable=False)
    verification_token_created_at = models.DateTimeField(default=timezone.now)
    
    # Override username field to use email as unique identifier if desired
    # but we'll keep default username for simplicity.
    
    def __str__(self):
        return self.email
    
    def generate_new_verification_token(self):
        """Generate a new verification token and update timestamp."""
        self.verification_token = uuid.uuid4()
        self.verification_token_created_at = timezone.now()
        self.save()


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    # Additional fields can be added later
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"Profile of {self.user.email}"


class Patent(models.Model):
    """
    Patent model storing full extraction data from USPTO XML files.
    """
    # Primary key
    patent_id = models.AutoField(primary_key=True)
    
    # Publication info
    publication_country = models.CharField(max_length=10, blank=True, null=True)
    publication_number = models.CharField(max_length=50, blank=True, null=True, db_index=True)
    publication_kind = models.CharField(max_length=10, blank=True, null=True)
    publication_date = models.DateField(blank=True, null=True)
    
    # Application info
    application_type = models.CharField(max_length=50, blank=True, null=True)
    application_number = models.CharField(max_length=50, blank=True, null=True, db_index=True)
    application_date = models.DateField(blank=True, null=True)
    application_series_code = models.CharField(max_length=20, blank=True, null=True)
    
    # Core content
    title = models.TextField(blank=True, null=True)
    abstract = models.TextField(blank=True, null=True)
    
    # Classifications (stored as JSON for flexibility)
    classifications_ipcr = models.JSONField(blank=True, null=True)
    classifications_cpc_main = models.JSONField(blank=True, null=True)
    classifications_cpc_further = models.JSONField(blank=True, null=True)
    
    # Inventors (stored as JSON - list of inventors)
    inventors = models.JSONField(blank=True, null=True)
    
    # Applicants (stored as JSON - list of applicants)
    applicants = models.JSONField(blank=True, null=True)
    
    # Claims (stored as JSON - list of claims)
    claims = models.JSONField(blank=True, null=True)
    
    # Priority claims
    priority_claims = models.JSONField(blank=True, null=True)
    
    # Metadata
    source_file = models.CharField(max_length=255, blank=True, null=True)
    language = models.CharField(max_length=10, blank=True, null=True)
    production_date = models.DateField(blank=True, null=True)
    
    # Timestamps
    extracted_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-publication_date', '-patent_id']
    
    def __str__(self):
        return f"Patent {self.publication_number}"


class Search(models.Model):
    """
    Search model to attribute searches to patents.
    """
    search_hash = models.CharField(max_length=64, unique=True, db_index=True)  # SHA256 hash
    search_query = models.TextField(blank=True, null=True)  # Store original query for reference
    created_at = models.DateTimeField(auto_now_add=True)
    
    # Many-to-many relationship with patents
    patents = models.ManyToManyField(Patent, related_name='searches')
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Search {self.search_hash[:16]}..."


class Entity(models.Model):
    """
    Entity model representing inventors, applicants, and assignees extracted from patents.
    """
    ENTITY_TYPE_CHOICES = [
        ('inventor', 'Inventor'),
        ('applicant', 'Applicant'),
        ('assignee', 'Assignee'),
    ]
    
    # Primary key
    entity_id = models.AutoField(primary_key=True)
    
    # Entity name
    name = models.CharField(max_length=255, db_index=True)
    
    # Entity type
    entity_type = models.CharField(max_length=20, choices=ENTITY_TYPE_CHOICES, db_index=True)

    # Stock ticker symbol (for publicly traded companies)
    ticker = models.CharField(max_length=10, blank=True, null=True, db_index=True)

    # Many-to-many relationship with patents
    patents = models.ManyToManyField(Patent, related_name='entities')
    
    # Many-to-many relationship with searches
    searches = models.ManyToManyField(Search, related_name='entities')
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['name']
        unique_together = ['name', 'entity_type']
    
    def __str__(self):
        return f"{self.name} ({self.entity_type})"


class Analysis(models.Model):
    """
    Analysis model representing a patent analysis/classification.
    Stores the raw response from OpenRouter API for each patent analysis.
    """
    # Primary key
    analysis_id = models.AutoField(primary_key=True)
    
    # Foreign key to Patent
    patent = models.OneToOneField(Patent, on_delete=models.CASCADE, related_name='analysis')
    
    # Raw response from OpenRouter API
    raw_response = models.TextField(blank=True, null=True)
    
    # Parsed JSON response (list of risks with snippet, risk type, confidence)
    parsed_risks = models.JSONField(blank=True, null=True)
    
    # Timestamp
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Analysis for Patent {self.patent.publication_number}"


class SavedSearch(models.Model):
    """
    Saved search model linked to a user.
    Stores search parameters so users can re-run searches later.
    """
    # Foreign key to User
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='saved_searches')
    
    # Search name (optional, user can name their search)
    name = models.CharField(max_length=255, blank=True, null=True)
    
    # Search parameters (stored as JSON)
    query = models.CharField(max_length=500, blank=True, null=True)
    inventor = models.CharField(max_length=255, blank=True, null=True)
    applicant = models.CharField(max_length=255, blank=True, null=True)
    assignee = models.CharField(max_length=255, blank=True, null=True)
    ticker = models.CharField(max_length=10, blank=True, null=True, help_text="Stock ticker symbol")
    
    # Timestamp
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"SavedSearch {self.name or self.query} by {self.user.email}"


class DashboardCache(models.Model):
    """
    Dashboard cache model to store pre-computed dashboard statistics.
    """
    # Foreign key to User
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='dashboard_caches')
    
    # Foreign key to SavedSearch (optional - null means global cache)
    saved_search = models.ForeignKey(SavedSearch, on_delete=models.CASCADE, related_name='dashboard_cache', null=True, blank=True)
    
    # Cache data stored as JSON
    cache_data = models.JSONField(default=dict)
    
    # Cached timestamp
    cached_at = models.DateTimeField(auto_now_add=True)
    
    # Cached counts
    patent_count = models.IntegerField(default=0)  # Number of analyzed patents
    total_patent_count = models.IntegerField(default=0)  # Total patents in database
    risks_count = models.IntegerField(default=0)  # Number of patents with at least one risk
    total_risks = models.IntegerField(default=0)  # Total number of individual risks
    patents_with_military = models.IntegerField(default=0)
    patents_with_surveillance = models.IntegerField(default=0)
    patents_with_online_manipulation = models.IntegerField(default=0)
    
    # Flag for global cache
    is_global = models.BooleanField(default=False)
    
    class Meta:
        ordering = ['-cached_at']
        unique_together = ['user', 'saved_search']
    
    def __str__(self):
        return f"DashboardCache for {self.user.email} (saved_search={self.saved_search_id})"