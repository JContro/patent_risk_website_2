"""
Patent filtering functions for CPC codes, date ranges, jurisdiction, and document types.
"""

import re
from datetime import datetime


# ---------------------------------------------------------------------------
# CPC Code Search with Wildcard Support
# ---------------------------------------------------------------------------

def format_cpc_code(classification):
    """
    Build a standard CPC code string from a classification dict.

    Format: ``{section}{class}{subclass}{main_group}/{subgroup}``
    e.g. ``A63F13/67``, ``G06N5/043``
    """
    if not classification:
        return None
    section = classification.get("section") or ""
    cls = classification.get("class") or ""
    subclass = classification.get("subclass") or ""
    main_group = classification.get("main_group") or ""
    subgroup = classification.get("subgroup") or ""

    code = f"{section}{cls}{subclass}{main_group}/{subgroup}"
    # Only return if we have at least section+class
    return code if section and cls else None


def get_patent_cpc_codes(patent_data):
    """
    Return a list of all CPC code strings for a patent.
    """
    codes = []
    cpc = patent_data.get("classifications_cpc")
    if not cpc:
        return codes

    main = cpc.get("main")
    if main:
        code = format_cpc_code(main)
        if code:
            codes.append(code)

    for further in cpc.get("further", []) or []:
        code = format_cpc_code(further)
        if code:
            codes.append(code)

    return codes


def cpc_pattern_to_regex(pattern):
    """
    Convert a CPC wildcard pattern to a compiled regex.

    ``*`` matches any sequence of characters.  The match is
    case-insensitive and anchored (full match).

    Examples::

        "G06F*"   →  matches G06F21/10, G06F3/00, etc.
        "G06*"    →  matches anything in G06
        "A63F13/*" → matches A63F13/67, A63F13/58, etc.
    """
    # Handle class_cpc.symbol: prefix (extract pattern after colon)
    if ":" in pattern:
        pattern = pattern.split(":", 1)[1]
    
    # Escape regex-special chars, then convert '*' to '.*'
    escaped = re.escape(pattern).replace(r"\*", ".*")
    return re.compile(f"^{escaped}$", re.IGNORECASE)


def matches_cpc_search(patent_data, cpc_patterns):
    """
    Return True if any of the patent's CPC codes match **any** of the
    supplied *cpc_patterns* (list of compiled regexes).
    """
    codes = get_patent_cpc_codes(patent_data)
    for code in codes:
        for pat in cpc_patterns:
            if pat.match(code):
                return True
    return False


# ---------------------------------------------------------------------------
# Date Range Filtering
# ---------------------------------------------------------------------------

def parse_date(date_str):
    """
    Parse date string in various formats (YYYYMMDD, YYYY-MM-DD, MM/DD/YYYY).
    Returns a datetime object or None if parsing fails.
    """
    if not date_str:
        return None
    
    # Remove any non-digit characters except for the date separators
    clean_date = re.sub(r'[^\d\-/]', '', date_str)
    
    formats = [
        '%Y%m%d',      # 20210401
        '%Y-%m-%d',    # 2021-04-01
        '%m/%d/%Y',    # 04/01/2021
        '%d/%m/%Y',    # 01/04/2021
    ]
    
    for fmt in formats:
        try:
            return datetime.strptime(clean_date, fmt)
        except ValueError:
            continue
    
    return None


def get_patent_date(patent_data):
    """
    Extract the publication date from patent data.
    Returns a datetime object or None if not available.
    """
    # Try publication date first
    if "publication" in patent_data and patent_data["publication"]:
        pub_date = patent_data["publication"].get("date")
        if pub_date:
            parsed = parse_date(pub_date)
            if parsed:
                return parsed
    
    # Try application date
    if "application" in patent_data and patent_data["application"]:
        app_doc_id = patent_data["application"].get("document_id")
        if app_doc_id and isinstance(app_doc_id, dict):
            app_date = app_doc_id.get("date")
            if app_date:
                parsed = parse_date(app_date)
                if parsed:
                    return parsed
    
    return None


def matches_date_range(patent_data, start_date=None, end_date=None):
    """
    Return True if the patent's date falls within the specified range.
    start_date and end_date should be datetime objects or date strings.
    """
    patent_date = get_patent_date(patent_data)
    if not patent_date:
        return False
    
    # Parse start/end dates if they're strings
    if isinstance(start_date, str):
        start_date = parse_date(start_date)
    if isinstance(end_date, str):
        end_date = parse_date(end_date)
    
    if start_date and patent_date < start_date:
        return False
    if end_date and patent_date > end_date:
        return False
    
    return True


# ---------------------------------------------------------------------------
# Jurisdiction Filtering
# ---------------------------------------------------------------------------

def get_patent_country(patent_data):
    """
    Extract the country code from patent data.
    Returns the country code or None.
    """
    # Check attributes
    if "attributes" in patent_data:
        country = patent_data["attributes"].get("country")
        if country:
            return country.upper()
    
    # Check publication reference
    if "publication" in patent_data and patent_data["publication"]:
        country = patent_data["publication"].get("country")
        if country:
            return country.upper()
    
    return None


def matches_jurisdiction(patent_data, jurisdiction):
    """
    Return True if the patent's country matches the specified jurisdiction.
    """
    if not jurisdiction:
        return True
    
    patent_country = get_patent_country(patent_data)
    if not patent_country:
        return False
    
    return patent_country == jurisdiction.upper()


# ---------------------------------------------------------------------------
# Document Type Filtering
# ---------------------------------------------------------------------------

def is_patent_grant(patent_data):
    """
    Return True if the patent is a granted patent (not an application).
    """
    # Check attributes for status
    if "attributes" in patent_data:
        status = patent_data["attributes"].get("status")
        if status and status.lower() == "granted":
            return True
    
    # Check if it's a us-patent-grant element (root tag would indicate this)
    # The extraction function handles both, but we can check application type
    if "application" in patent_data:
        appl_type = patent_data["application"].get("appl_type")
        # appl_type of "utility" typically indicates a granted patent
        if appl_type and appl_type.lower() == "utility":
            return True
    
    return False


def matches_document_type(patent_data, doc_type):
    """
    Return True if the patent matches the specified document type.
    Supported doc_type values: 'Granted_patent', 'Application'
    """
    if not doc_type:
        return True
    
    doc_type_lower = doc_type.lower().replace("_", " ")
    
    if doc_type_lower in ["granted", "granted_patent", "patent"]:
        return is_patent_grant(patent_data)
    elif doc_type_lower in ["application", "patent application"]:
        return not is_patent_grant(patent_data)
    
    # If unknown type, allow all
    return True
