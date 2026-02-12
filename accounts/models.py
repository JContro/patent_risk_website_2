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
