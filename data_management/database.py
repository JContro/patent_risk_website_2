"""
Database operations for patent data management.
Handles saving patents, searches, and entities to the Django database.
"""

import django
import os
import sys

# Django setup for database operations
# Add the parent directory to the path to import Django settings
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.utils.dateparse import parse_date
from django.db import transaction
from accounts.models import Patent, Search, Entity
from tqdm import tqdm


def parse_patent_date(date_str):
    """Parse date string to Django date object."""
    if not date_str:
        return None
    try:
        # Try ISO format first (YYYYMMDD)
        return parse_date(date_str)
    except (ValueError, TypeError):
        return None


def save_patent_to_db(patent_data):
    """
    Save a single patent dictionary to the database.
    Returns the Patent object if successful, None if failed.
    """
    try:
        with transaction.atomic():
            # Get publication data
            pub = patent_data.get('publication', {})
            app = patent_data.get('application', {})
            attrs = patent_data.get('attributes', {})
            cpc = patent_data.get('classifications_cpc', {})
            
            # Check if patent already exists (by publication number)
            pub_number = pub.get('doc_number')
            existing = None
            if pub_number:
                try:
                    existing = Patent.objects.filter(publication_number=pub_number).first()
                except Exception:
                    pass
            
            if existing:
                # Update existing patent
                patent = existing
            else:
                # Create new patent
                patent = Patent()
            
            # Map fields
            patent.publication_country = pub.get('country')
            patent.publication_number = pub_number
            patent.publication_kind = pub.get('kind')
            patent.publication_date = parse_patent_date(pub.get('date'))
            
            patent.application_type = app.get('appl_type')
            patent.application_number = app.get('document_id', {}).get('doc_number')
            patent.application_date = parse_patent_date(app.get('document_id', {}).get('date'))
            patent.application_series_code = patent_data.get('application_series_code')
            
            patent.title = patent_data.get('title')
            patent.abstract = patent_data.get('abstract')
            
            # Classifications
            patent.classifications_ipcr = patent_data.get('classifications_ipcr')
            patent.classifications_cpc_main = cpc.get('main')
            patent.classifications_cpc_further = cpc.get('further')
            
            # Inventors and applicants
            patent.inventors = patent_data.get('inventors')
            patent.applicants = patent_data.get('applicants')
            
            # Claims
            patent.claims = patent_data.get('claims')
            
            # Priority claims
            patent.priority_claims = patent_data.get('priority_claims')
            
            # Metadata
            patent.source_file = attrs.get('file')
            patent.language = attrs.get('lang')
            patent.production_date = parse_patent_date(attrs.get('date_produced'))
            
            patent.save()
            return patent
            
    except Exception as e:
        print(f"    Warning: Failed to save patent {pub.get('doc_number', 'unknown')}: {e}")
        return None


def save_patent_with_search(patent_data, search_obj):
    """
    Save a single patent and link it to a Search record.
    Returns the Patent object if successful, None if failed.
    This function uses O(1) memory - it saves one patent at a time.
    """
    patent = save_patent_to_db(patent_data)
    if patent and search_obj:
        try:
            search_obj.patents.add(patent)
        except Exception as e:
            print(f"    Warning: Failed to link patent to search: {e}")
    return patent


def save_patents_batch_to_db(patents_data):
    """
    Save a batch of patents to the database.
    Returns the number of patents saved successfully.
    """
    saved_count = 0
    for patent_data in tqdm(patents_data, desc="Saving to DB", leave=False):
        if save_patent_to_db(patent_data):
            saved_count += 1
    
    return saved_count


def save_search_to_db(search_hash, query, patent_ids):
    """
    Save a search record to the database with associated patents.
    """
    try:
        with transaction.atomic():
            search, created = Search.objects.get_or_create(
                search_hash=search_hash,
                defaults={'search_query': query}
            )
            
            if patent_ids:
                patents = Patent.objects.filter(patent_id__in=patent_ids)
                search.patents.set(patents)
            
            return search
    except Exception as e:
        print(f"    Warning: Failed to save search {search_hash}: {e}")
        return None


def save_entities_to_db(entities_data, search_obj=None, patents=None):
    """
    Save entity records to the database.
    
    Args:
        entities_data: Dict with 'inventors', 'applicants', 'assignees' lists
        search_obj: Optional Search object to link entities to
        patents: Optional list of Patent objects to link entities to
    
    Returns the number of entities saved.
    """
    saved_count = 0
    try:
        with transaction.atomic():
            entity_type_map = {
                'inventors': 'inventor',
                'applicants': 'applicant',
                'assignees': 'assignee',
            }
            
            for field, entity_type in entity_type_map.items():
                entity_names = entities_data.get(field, [])
                for name in entity_names:
                    entity, created = Entity.objects.get_or_create(
                        name=name,
                        entity_type=entity_type
                    )
                    if created:
                        saved_count += 1
                    
                    # Link to search if provided
                    if search_obj:
                        entity.searches.add(search_obj)
                    
                    # Link to patents if provided
                    if patents:
                        for patent in patents:
                            entity.patents.add(patent)
            
            return saved_count
    except Exception as e:
        print(f"    Warning: Failed to save entities: {e}")
        return 0