"""
OpenRouter API service for patent analysis.
Analyzes patent claims against EU AI Act risks.
"""
import requests
from django.conf import settings


def analyse_patent_with_openrouter(patent, prompt_template):
    """
    Send patent claims to OpenRouter API for risk analysis.
    
    Args:
        patent: The Patent model instance
        prompt_template: The prompt template to use (with {risks_list} and {patent_claims} placeholders)
    
    Returns:
        The raw response from OpenRouter API as a string, or None if failed
    """
    api_key = settings.OPENROUTER_API_KEY
    
    if not api_key:
        raise ValueError("OpenRouter API key not configured. Please set OPENROUTER_API_KEY in .env")
    
    # Get the risks list from settings
    risks_list = getattr(settings, 'EU_AI_RISKS', [])
    if not risks_list:
        raise ValueError("EU AI Risks not configured. Please check settings.")
    
    # Format the risks list as a string
    risks_str = "\n".join(f"- {risk}" for risk in risks_list)
    
    # Build patent claims from the patent object
    patent_claims = _build_patent_claims(patent)
    
    if not patent_claims.strip():
        raise ValueError("No patent claims available for analysis")
    
    # Replace placeholders in the prompt
    prompt = prompt_template.replace('{risks_list}', risks_str).replace('{patent_claims}', patent_claims)
    
    # OpenRouter API endpoint
    url = "https://openrouter.ai/api/v1/chat/completions"
    
    # Request headers
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://patentrisk.com",  # Required by OpenRouter
        "X-Title": "Patent Risk Analyzer",  # Optional, for OpenRouter dashboard
    }
    
    # Request body - using a general model that works well for analysis
    data = {
        "model": "deepseek/deepseek-v3.2",  # qwen/qwen3.5-397b-a17b
        "messages": [
            {
                "role": "user",
                "content": prompt
            }
        ],
        "temperature": 1,
        # "max_tokens": 4096,
    }
    
    try:
        response = requests.post(url, headers=headers, json=data, timeout=60)
        response.raise_for_status()
        
        result = response.json()
        
        # Extract the content from the response
        # OpenRouter returns: {"choices": [{"message": {"content": "..."}}]}
        if 'choices' in result and len(result['choices']) > 0:
            message = result['choices'][0].get('message', {})
            content = message.get('content', '')
            return content
        
        return str(result)
        
    except requests.exceptions.Timeout:
        raise Exception("OpenRouter API request timed out")
    except requests.exceptions.RequestException as e:
        raise Exception(f"OpenRouter API request failed: {str(e)}")
    except Exception as e:
        raise Exception(f"Error analyzing patent: {str(e)}")


def _build_patent_claims(patent):
    """
    Build a text representation of patent claims for analysis.
    """
    claims_parts = []
    
    # Title
    if patent.title:
        claims_parts.append(f"Title: {patent.title}")
    
    # Abstract
    if patent.abstract:
        claims_parts.append(f"\nAbstract: {patent.abstract}")
    
    # Claims
    if patent.claims:
        claims_parts.append(f"\nClaims:")
        for i, claim in enumerate(patent.claims, 1):
            if isinstance(claim, dict):
                claim_text = claim.get('text', '')
            else:
                claim_text = str(claim)
            if claim_text:
                claims_parts.append(f"{i}. {claim_text}")
    
    return "\n".join(claims_parts)
