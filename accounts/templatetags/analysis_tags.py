from django import template
import re

register = template.Library()

@register.filter
def is_empty_list(value):
    """
    Returns True if the value is an empty list, False otherwise.
    Used to check if parsed_risks is [] (no risks detected).
    """
    return isinstance(value, list) and len(value) == 0


@register.filter
def has_risks(value):
    """
    Returns True if the value is a non-empty list (has risks), False otherwise.
    """
    return isinstance(value, list) and len(value) > 0


@register.filter
def get_risk_count(value):
    """
    Returns the length of the list, or 0 if not a list.
    """
    if isinstance(value, list):
        return len(value)
    return 0


@register.filter
def snippet_found(snippet, patent_text):
    """
    Check if a snippet text is found in the patent text (claims/abstract).
    Returns True if found, False otherwise.
    """
    if not snippet or not patent_text:
        return False
    
    # Normalize both texts for comparison
    snippet_normalized = snippet.lower().strip()
    text_normalized = patent_text.lower()
    
    # Check if the snippet exists in the text
    return snippet_normalized in text_normalized


@register.simple_tag
def check_snippet_in_patent(snippet, patent):
    """
    Check if the snippet is found in the patent's claims or abstract.
    Returns a dict with 'found' boolean and 'location' string.
    """
    if not snippet or not patent:
        return {'found': False, 'location': None}
    
    snippet_lower = snippet.lower().strip()
    
    # Check in claims
    if patent.claims:
        for claim in patent.claims:
            if isinstance(claim, dict):
                claim_text = claim.get('text', '').lower()
            else:
                claim_text = str(claim).lower()
            
            if snippet_lower in claim_text:
                return {'found': True, 'location': 'claims'}
    
    # Check in abstract
    if patent.abstract:
        if snippet_lower in patent.abstract.lower():
            return {'found': True, 'location': 'abstract'}
    
    return {'found': False, 'location': None}