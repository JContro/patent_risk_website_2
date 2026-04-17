#!/usr/bin/env python3
"""
Test script to analyze a single patent using local vLLM API.
Run this first to verify the vLLM setup works before running full batch analysis.
"""
import os
import sys
import django

# Setup Django
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from accounts.models import Patent
from accounts.vllm_service import analyse_patent_with_vllm
from django.conf import settings
import json


def test_single_patent(patent_id=None):
    """Test vLLM analysis on a single patent."""
    
    # Get prompt template from settings
    prompt_template = getattr(settings, 'PATENT_ANALYSIS_PROMPT', '')
    if not prompt_template:
        print("ERROR: PATENT_ANALYSIS_PROMPT not configured in settings")
        return False
    
    # Get a patent to analyze
    if patent_id:
        try:
            patent = Patent.objects.get(patent_id=patent_id)
            print(f"Using specified patent: {patent.patent_id}")
        except Patent.DoesNotExist:
            print(f"ERROR: Patent with ID {patent_id} not found")
            return False
    else:
        # Get first patent without analysis
        patents_without_analysis = Patent.objects.filter(analysis__isnull=True)[:1]
        if not patents_without_analysis.exists():
            print("No patents without analysis found. Trying to get any patent...")
            patent = Patent.objects.first()
            if not patent:
                print("ERROR: No patents found in database")
                return False
        else:
            patent = patents_without_analysis.first()
        print(f"Testing with patent: {patent.patent_id}")
        print(f"Title: {patent.title}")
    
    # Build claims preview
    claims_count = len(patent.claims) if patent.claims else 0
    print(f"Number of claims: {claims_count}")
    
    if claims_count == 0:
        print("ERROR: This patent has no claims to analyze")
        return False
    
    # Limit claims for testing (first 3)
    print("\nLimiting to first 3 claims for quick test...")
    original_claims = patent.claims
    patent.claims = patent.claims[:3] if len(patent.claims) > 3 else patent.claims
    
    print("\n" + "="*60)
    print("Starting vLLM analysis...")
    print("="*60 + "\n")
    
    try:
        raw_response = analyse_patent_with_vllm(patent, prompt_template)
        
        if raw_response:
            print("SUCCESS! Received response from vLLM API")
            print("\nRaw response (first 1000 chars):")
            print(raw_response[:1000])
            
            # Try to parse as JSON
            try:
                parsed = json.loads(raw_response)
                print("\nParsed JSON response:")
                print(json.dumps(parsed, indent=2)[:500])
            except json.JSONDecodeError:
                print("\nResponse is not valid JSON")
            
            return True
        else:
            print("ERROR: No response received from vLLM API")
            return False
            
    except Exception as e:
        print(f"ERROR: {str(e)}")
        return False
    finally:
        # Restore original claims
        patent.claims = original_claims


if __name__ == '__main__':
    # Allow specifying patent_id as command line argument
    patent_id = int(sys.argv[1]) if len(sys.argv) > 1 else None
    
    success = test_single_patent(patent_id)
    sys.exit(0 if success else 1)
