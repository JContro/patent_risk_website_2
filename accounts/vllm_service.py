"""
vLLM API service for patent analysis.
Analyzes patent claims against EU AI Act risks using local vLLM server.
"""
import requests
from django.conf import settings


def analyse_patent_with_vllm(patent, prompt_template):
    """
    Send patent claims to local vLLM API for risk analysis.
    
    Args:
        patent: The Patent model instance
        prompt_template: The prompt template to use (with {risks_list} and {patent_claims} placeholders)
    
    Returns:
        The raw response from vLLM API as a string, or None if failed
    """
    # Get the vLLM API URL from settings
    # Use the Docker service name to reach vLLM server on the same network
    # Note: vLLM runs on port 8000 inside container, mapped to 8090 on host
    vllm_api_url = getattr(settings, 'VLLM_API_URL', 'http://vllm-api-server:8000')
    
    # Get the structured risks list from settings
    risks_structure = getattr(settings, 'EU_AI_RISKS_STRUCTURE', {})
    if not risks_structure:
        raise ValueError("EU AI Risks not configured. Please check settings.")

    # Format the risks list as a string with category headers
    risks_str = ""
    for category, risks in risks_structure.items():
        risks_str += f"\n{category}:\n"
        for risk in risks:
            risks_str += f"  - {risk}\n"
    risks_str = risks_str.strip()
    
    # Build patent claims from the patent object
    patent_claims = _build_patent_claims(patent)
    
    if not patent_claims.strip():
        raise ValueError("No patent claims available for analysis")
    
    # Replace placeholders in the prompt
    prompt = prompt_template.replace('{risks_list}', risks_str).replace('{patent_claims}', patent_claims)
    
    # vLLM API endpoint (OpenAI-compatible)
    url = f"{vllm_api_url}/v1/chat/completions"
    
    # Request headers
    headers = {
        "Content-Type": "application/json",
    }
    
    # Request body - using the model loaded in vLLM
    data = {
        "model": "google/gemma-4-26B-A4B-it",  # Model loaded in vLLM
        "messages": [
            {
                "role": "user",
                "content": prompt
            }
        ],
        "temperature": 0.3,  # Lower temperature for more consistent outputs
        "max_tokens": 4096,
    }
    
    try:
        response = requests.post(url, headers=headers, json=data, timeout=120)
        response.raise_for_status()
        
        result = response.json()
        
        # Extract the content from the response
        # vLLM returns OpenAI-compatible format: {"choices": [{"message": {"content": "..."}}]}
        if 'choices' in result and len(result['choices']) > 0:
            message = result['choices'][0].get('message', {})
            content = message.get('content', '')
            return content
        
        return str(result)
        
    except requests.exceptions.Timeout:
        raise Exception("vLLM API request timed out")
    except requests.exceptions.RequestException as e:
        raise Exception(f"vLLM API request failed: {str(e)}")
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
