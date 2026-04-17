#!/usr/bin/env python3
"""
Script to import patents from patents_refined.json into the database.
Run inside the Docker container: docker compose exec web python import_patents.py
"""

import os
import sys
import json
import ijson
from datetime import datetime
from pathlib import Path

# Setup Django
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django
django.setup()

from accounts.models import Patent


def parse_date(date_str):
    """Parse date string in format YYYYMMDD to date object."""
    if not date_str:
        return None
    try:
        return datetime.strptime(str(date_str), '%Y%m%d').date()
    except (ValueError, TypeError):
        return None


def import_patents(json_file_path, batch_size=100, dry_run=False):
    """
    Import patents from JSON file to database.
    
    Args:
        json_file_path: Path to patents_refined.json
        batch_size: Number of patents to process before saving
        dry_run: If True, don't actually save to database
    """
    print(f"Starting import from: {json_file_path}")
    print(f"Batch size: {batch_size}")
    print(f"Dry run: {dry_run}")
    print("-" * 50)
    
    patents_to_create = []
    total_imported = 0
    total_errors = 0
    batch_count = 0
    
    # Check if publication_number already exists to avoid duplicates
    existing_numbers = set(
        Patent.objects.values_list('publication_number', flat=True)
    )
    print(f"Found {len(existing_numbers)} existing patents in database")
    
    with open(json_file_path, 'rb') as f:
        # Use ijson for streaming parse of large file
        patents = ijson.items(f, 'patents.item')
        
        for patent_data in patents:
            try:
                # Extract publication info
                pub = patent_data.get('publication', {})
                pub_number = pub.get('doc_number')
                
                # Skip if already exists and not dry run
                if pub_number in existing_numbers and not dry_run:
                    continue
                
                # Extract application info
                app = patent_data.get('application', {})
                app_doc_id = app.get('document_id', {})
                
                # Extract attributes
                attrs = patent_data.get('attributes', {})
                
                # Create Patent object
                patent = Patent(
                    publication_country=pub.get('country'),
                    publication_number=pub_number,
                    publication_kind=pub.get('kind'),
                    publication_date=parse_date(pub.get('date')),
                    
                    application_type=app.get('appl_type'),
                    application_number=app_doc_id.get('doc_number'),
                    application_date=parse_date(app_doc_id.get('date')),
                    application_series_code=patent_data.get('application_series_code'),
                    
                    title=patent_data.get('title'),
                    abstract=patent_data.get('abstract'),
                    
                    classifications_ipcr=patent_data.get('classifications_ipcr'),
                    # CPC classifications might not be in the JSON, set to None
                    classifications_cpc_main=None,
                    classifications_cpc_further=None,
                    
                    inventors=patent_data.get('inventors'),
                    applicants=patent_data.get('applicants'),
                    claims=patent_data.get('claims'),
                    priority_claims=None,  # Not in the JSON structure
                    
                    source_file=attrs.get('file'),
                    language=attrs.get('lang'),
                    production_date=parse_date(attrs.get('date_produced')),
                )
                
                if dry_run:
                    patents_to_create.append(patent)
                else:
                    patents_to_create.append(patent)
                    existing_numbers.add(pub_number)  # Mark as seen
                
                batch_count += 1
                
                if batch_count >= batch_size:
                    if not dry_run:
                        Patent.objects.bulk_create(patents_to_create)
                    total_imported += len(patents_to_create)
                    print(f"Processed {total_imported} patents...")
                    patents_to_create = []
                    batch_count = 0
                    
            except Exception as e:
                total_errors += 1
                print(f"Error processing patent: {e}")
                continue
    
    # Save remaining patents
    if patents_to_create:
        if not dry_run:
            Patent.objects.bulk_create(patents_to_create)
        total_imported += len(patents_to_create)
    
    print("-" * 50)
    print(f"Import complete!")
    print(f"Total patents imported: {total_imported}")
    print(f"Total errors: {total_errors}")
    
    return total_imported, total_errors


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Import patents from JSON to database')
    parser.add_argument(
        '--json-file',
        default='/app/patents_refined.json',
        help='Path to patents_refined.json file (default: /app/patents_refined.json)'
    )
    parser.add_argument(
        '--batch-size',
        type=int,
        default=100,
        help='Number of patents to process per batch (default: 100)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be imported without saving to database'
    )
    
    args = parser.parse_args()
    
    # Resolve path
    json_path = Path(args.json_file)
    if not json_path.is_absolute():
        # If relative, assume it's relative to the project root
        json_path = Path(__file__).resolve().parent / json_path
    
    if not json_path.exists():
        print(f"Error: JSON file not found: {json_path}")
        sys.exit(1)
    
    import_patents(str(json_path), batch_size=args.batch_size, dry_run=args.dry_run)


if __name__ == '__main__':
    main()
