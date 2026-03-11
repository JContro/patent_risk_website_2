"""
Data management package for patent XML processing.

Modules:
- database: Django database operations for patents, searches, and entities
- xml_parser: USPTO XML parsing utilities
- search: Boolean search query parser and evaluator
- filters: CPC code, date range, jurisdiction, and document type filters
- file_io: File reading utilities for XML, ZIP, and JSON
- main: CLI entry point
"""

# Database operations
from .database import (
    save_patent_to_db,
    save_patent_with_search,
    save_patents_batch_to_db,
    save_search_to_db,
    save_entities_to_db,
    parse_patent_date,
)

# XML parsing
from .xml_parser import (
    extract_text,
    extract_document_id,
    extract_classification,
    extract_person,
    extract_claim,
    extract_patent,
    contains_keywords,
)

# Search
from .search import (
    SearchToken,
    tokenize_search,
    SearchParser,
    parse_search_query,
    PhraseNode,
    AndNode,
    OrNode,
    evaluate_search,
    get_entity_name,
    collect_entity_names,
    get_patent_text,
    get_patent_entity_text,
    matches_search,
    matches_entity_search,
    collect_distinct_entities,
    search_hash,
)

# Filters
from .filters import (
    format_cpc_code,
    get_patent_cpc_codes,
    cpc_pattern_to_regex,
    matches_cpc_search,
    parse_date as parse_filter_date,
    get_patent_date,
    matches_date_range,
    get_patent_country,
    matches_jurisdiction,
    is_patent_grant,
    matches_document_type,
)

# File I/O
from .file_io import (
    load_patents_from_json,
    parse_xml_content,
    process_xml_file_sequential,
    read_xml_content,
    read_all_zips_sequential,
    reset_parsing_errors,
    print_parsing_errors,
    PARSING_ERRORS,
)

__all__ = [
    # Database
    'save_patent_to_db',
    'save_patent_with_search',
    'save_patents_batch_to_db',
    'save_search_to_db',
    'save_entities_to_db',
    'parse_patent_date',
    
    # XML Parser
    'extract_text',
    'extract_document_id',
    'extract_classification',
    'extract_person',
    'extract_claim',
    'extract_patent',
    'contains_keywords',
    
    # Search
    'SearchToken',
    'tokenize_search',
    'SearchParser',
    'parse_search_query',
    'PhraseNode',
    'AndNode',
    'OrNode',
    'evaluate_search',
    'get_entity_name',
    'collect_entity_names',
    'get_patent_text',
    'get_patent_entity_text',
    'matches_search',
    'matches_entity_search',
    'collect_distinct_entities',
    'search_hash',
    
    # Filters
    'format_cpc_code',
    'get_patent_cpc_codes',
    'cpc_pattern_to_regex',
    'matches_cpc_search',
    'parse_filter_date',
    'get_patent_date',
    'matches_date_range',
    'get_patent_country',
    'matches_jurisdiction',
    'is_patent_grant',
    'matches_document_type',
    
    # File I/O
    'load_patents_from_json',
    'parse_xml_content',
    'process_xml_file_sequential',
    'read_xml_content',
    'read_all_zips_sequential',
    'reset_parsing_errors',
    'print_parsing_errors',
    'PARSING_ERRORS',
]
