#!/usr/bin/env python
"""
Data Management Script for processing zipped XML patent files.

This script extracts patent data from USPTO XML files and maps it to the Patent model schema.

Usage in Docker:
    docker compose exec web python data_management/extract_xml.py
    
    # Or with options:
    docker compose exec web python data_management/extract_xml.py --limit 10
    docker compose exec web python data_management/extract_xml.py --zip ipg220215.zip
    
    # Save to database:
    docker compose exec web python data_management/extract_xml.py --save --limit 100
"""

import os
import sys
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime
from typing import Optional
import re

# Setup Django before importing models
import django
from django.conf import settings

# Configure Django settings if not already configured
if not settings.configured:
    # Add project to path
    sys.path.insert(0, str(Path(__file__).parent.parent))
    import config.settings as config_settings
    django.setup()

from accounts.models import Patent


# Data directory - inside data_management folder
DATA_DIR = Path(__file__).parent / "data"


def find_zipped_xml_files(data_dir: Path) -> list[Path]:
    """Find all zip files in the data directory."""
    if not data_dir.exists():
        print(f"Data directory does not exist: {data_dir}")
        return []

    zip_files = sorted(data_dir.glob("*.zip"))
    print(f"Found {len(zip_files)} zip file(s) in {data_dir}")
    return zip_files


def parse_date(date_str: Optional[str]) -> Optional[datetime]:
    """Parse date string in YYYYMMDD format to datetime.date."""
    if not date_str:
        return None
    try:
        # Handle dates with only year or year-month
        if len(date_str) == 8:
            return datetime.strptime(date_str, '%Y%m%d').date()
        elif len(date_str) == 6:
            return datetime.strptime(date_str + '01', '%Y%m%d').date()
        elif len(date_str) == 4:
            return datetime.strptime(date_str + '0101', '%Y%m%d').date()
    except ValueError:
        pass
    return None


def extract_text(element: Optional[ET.Element]) -> Optional[str]:
    """Extract text from XML element safely."""
    if element is None:
        return None
    text = element.text
    return text.strip() if text else None


def get_doc_id_text(element: Optional[ET.Element]) -> Optional[str]:
    """Extract text from document-id element."""
    if element is None:
        return None
    text = ''.join(element.itertext())
    return text.strip() if text else None


def parse_patent(patent_elem: ET.Element, source_file: str) -> dict:
    """
    Parse a single patent element into a dictionary matching the Patent model.

    Args:
        patent_elem: The XML element containing patent data
        source_file: The source zip file name

    Returns:
        Dictionary with patent data matching Patent model schema
    """
    data = {
        'source_file': source_file,
    }

    # Get root attributes
    root = patent_elem
    data['publication_country'] = root.get('country', 'US')
    data['language'] = root.get('lang', 'EN')
    data['production_date'] = parse_date(root.get('date-produced'))

    # Parse bibliographic data grant
    biblio = root.find('.//us-bibliographic-data-grant')
    if biblio is None:
        return data

    # Publication reference
    pub_ref = biblio.find('.//publication-reference')
    if pub_ref is not None:
        doc_id = pub_ref.find('.//document-id')
        if doc_id is not None:
            data['publication_number'] = get_doc_id_text(
                doc_id.find('doc-number'))
            data['publication_kind'] = extract_text(doc_id.find('kind'))
            pub_date = extract_text(doc_id.find('date'))
            data['publication_date'] = parse_date(pub_date)

    # Application reference
    app_ref = biblio.find('.//application-reference')
    if app_ref is not None:
        data['application_type'] = app_ref.get('appl-type')
        doc_id = app_ref.find('.//document-id')
        if doc_id is not None:
            data['application_number'] = get_doc_id_text(
                doc_id.find('doc-number'))
            app_date = extract_text(doc_id.find('date'))
            data['application_date'] = parse_date(app_date)

    # Application series code
    series_code = biblio.find('.//us-application-series-code')
    if series_code is not None:
        data['application_series_code'] = extract_text(series_code)

    # Title
    title_elem = biblio.find('.//invention-title')
    if title_elem is not None:
        data['title'] = extract_text(title_elem)

    # Classifications - IPCR
    ipcr_classifications = []
    for ipcr in biblio.findall('.//classifications-ipcr//classification-ipcr'):
        text_parts = []
        for child in ipcr:
            if child.text:
                text_parts.append(child.text.strip())
        if text_parts:
            ipcr_classifications.append(' '.join(text_parts))
    data['classifications_ipcr'] = ipcr_classifications if ipcr_classifications else None

    # Classifications - CPC (main)
    cpc_main = []
    for cpc in biblio.findall('.//classification-cpc-primary//classification-cpc-text'):
        text = extract_text(cpc)
        if text:
            cpc_main.append(text)
    data['classifications_cpc_main'] = cpc_main if cpc_main else None

    # Classifications - CPC (further)
    cpc_further = []
    for cpc in biblio.findall('.//classification-cpc-secondary//classification-cpc-text'):
        text = extract_text(cpc)
        if text:
            cpc_further.append(text)
    data['classifications_cpc_further'] = cpc_further if cpc_further else None

    # Also try to get classifications from us-field-of-classification-search
    for cpc_text in biblio.findall('.//classification-cpc-text'):
        text = extract_text(cpc_text)
        if text and data['classifications_cpc_further'] is not None:
            if text not in data['classifications_cpc_further']:
                data['classifications_cpc_further'].append(text)
        elif text:
            data['classifications_cpc_further'] = [text]

    # Inventors
    inventors = []
    for inv in biblio.findall('.//inventor'):
        addressbook = inv.find('.//addressbook')
        if addressbook is not None:
            inventor = {}
            last_name = addressbook.find('.//last-name')
            first_name = addressbook.find('.//first-name')
            if last_name is not None:
                inventor['last_name'] = extract_text(last_name)
            if first_name is not None:
                inventor['first_name'] = extract_text(first_name)

            # Address
            address = addressbook.find('.//address')
            if address is not None:
                city = address.find('.//city')
                country = address.find('.//country')
                state = address.find('.//state')
                inventor['city'] = extract_text(city)
                inventor['country'] = extract_text(country)
                inventor['state'] = extract_text(state)

            if inventor:
                inventors.append(inventor)
    data['inventors'] = inventors if inventors else None

    # Applicants
    applicants = []
    for app in biblio.findall('.//us-applicant'):
        addressbook = app.find('.//addressbook')
        if addressbook is not None:
            applicant = {}
            orgname = addressbook.find('.//orgname')
            if orgname is not None:
                applicant['name'] = extract_text(orgname)

            # Address
            address = addressbook.find('.//address')
            if address is not None:
                city = address.find('.//city')
                country = address.find('.//country')
                state = address.find('.//state')
                applicant['city'] = extract_text(city)
                applicant['country'] = extract_text(country)
                applicant['state'] = extract_text(state)

            # Applicant type
            app_type = app.get('app-type')
            if app_type:
                applicant['applicant_type'] = app_type

            if applicant:
                applicants.append(applicant)
    data['applicants'] = applicants if applicants else None

    # Assignees
    assignees = []
    for assignee in biblio.findall('.//assignees//assignee'):
        addressbook = assignee.find('.//addressbook')
        if addressbook is not None:
            entity = {}
            orgname = addressbook.find('.//orgname')
            if orgname is not None:
                entity['name'] = extract_text(orgname)

            role = assignee.find('.//role')
            if role is not None:
                entity['role'] = extract_text(role)

            # Address
            address = addressbook.find('.//address')
            if address is not None:
                city = address.find('.//city')
                country = address.find('.//country')
                entity['city'] = extract_text(city)
                entity['country'] = extract_text(country)

            if entity:
                assignees.append(entity)

    # Add assignees to applicants if no separate applicants
    if not applicants and assignees:
        data['applicants'] = assignees

    # Abstract - from abstract element (utility patents have this)
    abstract_elem = root.find('.//abstract')
    if abstract_elem is not None:
        # Get all text including p elements
        abstract_text = ''.join(abstract_elem.itertext()).strip()
        data['abstract'] = abstract_text if abstract_text else None

    # Claims - from claims element
    claims = []
    for claim in root.findall('.//claim'):
        claim_text_elem = claim.find('.//claim-text')
        if claim_text_elem is not None:
            claim_text = extract_text(claim_text_elem)
            if claim_text:
                claims.append({
                    'id': claim.get('id'),
                    'num': claim.get('num'),
                    'text': claim_text
                })
    data['claims'] = claims if claims else None

    # Priority claims
    priority_claims = []
    for priority in biblio.findall('.//priority-claim'):
        doc_id = priority.find('.//document-id')
        if doc_id is not None:
            pc = {}
            pc['country'] = get_doc_id_text(doc_id.find('country'))
            pc['doc_number'] = get_doc_id_text(doc_id.find('doc-number'))
            pc['date'] = extract_text(doc_id.find('date'))
            priority_claims.append(pc)
    data['priority_claims'] = priority_claims if priority_claims else None

    return data


def iter_patents_from_xml(xml_content: bytes, source_file: str):
    """
    Iterate over patents in an XML file.
    Handles the case where multiple patent documents are concatenated.
    """
    # The XML files may contain multiple patent grants concatenated
    # We need to find all us-patent-grant elements
    content_str = xml_content.decode('utf-8')

    # Find all patent grant start tags
    pattern = r'<\?xml[^>]*\?>.*?<us-patent-grant'

    # Split by patent grant elements
    # This is a workaround since ElementTree requires well-formed XML
    # USPTO files have multiple XML documents concatenated

    # Try parsing as is first (if it's well-formed)
    try:
        root = ET.fromstring(xml_content)
        # Single patent
        yield parse_patent(root, source_file)
        return
    except ET.ParseError:
        pass

    # Split by patent grant document
    # Find all us-patent-grant start positions
    start_pattern = r'<\?xml[^?]*\?>\s*<!DOCTYPE[^>]*>\s*<us-patent-grant'

    # Use regex to split the content
    parts = re.split(r'(?=<\?xml[^?]*\?>)', content_str)

    for part in parts:
        if '<us-patent-grant' in part:
            try:
                # Try to parse each part as separate XML
                # Add XML declaration if missing
                if not part.strip().startswith('<?xml'):
                    part = '<?xml version="1.0" encoding="UTF-8"?>' + part
                root = ET.fromstring(part.encode('utf-8'))
                yield parse_patent(root, source_file)
            except ET.ParseError as e:
                print(f"    Warning: Could not parse patent section: {e}")
                continue


def process_zipped_xml(zip_path: Path, limit: int = None) -> list[dict]:
    """
    Extract and parse XML files from a zip archive.

    Args:
        zip_path: Path to the zip file
        limit: Maximum number of patents to process (None for all)

    Returns:
        List of dictionaries containing parsed patent data
    """
    results = []

    with zipfile.ZipFile(zip_path, 'r') as zf:
        # List all files in the zip
        file_list = zf.namelist()
        xml_files = [f for f in file_list if f.endswith('.xml')]

        print(
            f"  Processing {zip_path.name}: {len(xml_files)} XML file(s) found")

        for xml_file in xml_files:
            try:
                # Read the XML content
                with zf.open(xml_file) as xml_content:
                    content = xml_content.read()

                    # Parse each patent in the file
                    patent_count = 0
                    for patent_data in iter_patents_from_xml(content, zip_path.name):
                        results.append(patent_data)
                        patent_count += 1

                        if limit and patent_count >= limit:
                            break

                    print(
                        f"    Extracted {patent_count} patent(s) from {xml_file}")

                    if limit and patent_count >= limit:
                        break

            except ET.ParseError as e:
                print(f"  Error parsing {xml_file}: {e}")
            except Exception as e:
                print(f"  Error processing {xml_file}: {e}")

    return results


def save_patents_to_db(patents_data: list[dict]) -> int:
    """
    Save extracted patent data to the SQLite database.

    Args:
        patents_data: List of patent dictionaries

    Returns:
        Number of patents saved
    """
    saved_count = 0
    skipped_count = 0

    for data in patents_data:
        # Check if patent already exists by publication_number
        pub_num = data.get('publication_number')

        if pub_num:
            existing = Patent.objects.filter(
                publication_number=pub_num).first()
            if existing:
                # Update existing patent
                for key, value in data.items():
                    setattr(existing, key, value)
                existing.save()
                saved_count += 1
            else:
                # Create new patent
                patent = Patent(**data)
                patent.save()
                saved_count += 1
        else:
            # Skip patents without publication number
            skipped_count += 1

    return saved_count


def extract_all_patents(
    data_dir: Path = DATA_DIR,
    zip_name: str = None,
    limit: int = None,
    save_to_db: bool = False
) -> list[dict]:
    """
    Main function to extract all patent data from zipped XML files.

    Args:
        data_dir: Directory containing zip files
        zip_name: Specific zip file to process (None for all)
        limit: Maximum number of patents to process per file
        save_to_db: Whether to save extracted patents to database

    Returns:
        List of all parsed patent data
    """
    print(f"\n=== Starting Patent Extraction ===")
    print(f"Data directory: {data_dir}")
    if save_to_db:
        print(f"Mode: Extract and save to database")
    else:
        print(f"Mode: Extract only (no database save)")
    print()

    all_results = []
    zip_files = find_zipped_xml_files(data_dir)

    # Filter to specific zip if provided
    if zip_name:
        zip_files = [zf for zf in zip_files if zf.name == zip_name]
        if not zip_files:
            print(f"Zip file not found: {zip_name}")
            return []

    for zip_file in zip_files:
        print(f"\nProcessing: {zip_file.name}")
        results = process_zipped_xml(zip_file, limit=limit)
        all_results.extend(results)
        print(f"  Total extracted so far: {len(all_results)}")

    print(f"\n=== Extraction Complete ===")
    print(f"Total patents extracted: {len(all_results)}")

    # Save to database if requested
    if save_to_db and all_results:
        print(f"\n=== Saving to Database ===")
        saved = save_patents_to_db(all_results)
        print(f"Patents saved to database: {saved}")
        print(f"Database now contains {Patent.objects.count()} patents total")

    return all_results


def print_patent_sample(patent: dict, num: int = 1) -> None:
    """Print a sample of the extracted patent data."""
    print(f"\n{'='*60}")
    print(f"Patent #{num} Sample")
    print(f"{'='*60}")

    # Key fields
    print(f"\n--- Publication Info ---")
    print(f"  Number: {patent.get('publication_number')}")
    print(f"  Kind: {patent.get('publication_kind')}")
    print(f"  Date: {patent.get('publication_date')}")
    print(f"  Country: {patent.get('publication_country')}")

    print(f"\n--- Application Info ---")
    print(f"  Number: {patent.get('application_number')}")
    print(f"  Type: {patent.get('application_type')}")
    print(f"  Date: {patent.get('application_date')}")
    print(f"  Series Code: {patent.get('application_series_code')}")

    print(f"\n--- Content ---")
    print(f"  Title: {patent.get('title')}")
    abstract = patent.get('abstract')
    if abstract:
        print(f"  Abstract: {abstract[:200]}...")
    else:
        print(f"  Abstract: (none)")

    print(f"\n--- Classifications ---")
    ipcr = patent.get('classifications_ipcr') or []
    cpc_main = patent.get('classifications_cpc_main') or []
    print(f"  IPCR: {ipcr[:3]}...")
    print(f"  CPC Main: {cpc_main[:3]}...")

    print(f"\n--- Inventors ---")
    inventors = patent.get('inventors', [])
    if inventors:
        for inv in inventors[:3]:
            print(f"    {inv.get('first_name')} {inv.get('last_name')}")
        if len(inventors) > 3:
            print(f"    ... and {len(inventors) - 3} more")

    print(f"\n--- Applicants ---")
    applicants = patent.get('applicants', [])
    if applicants:
        for app in applicants[:3]:
            print(f"    {app.get('name')}")
        if len(applicants) > 3:
            print(f"    ... and {len(applicants) - 3} more")

    print(f"\n--- Claims ---")
    claims = patent.get('claims', [])
    if claims:
        print(f"    {len(claims)} claim(s)")
        print(f"    First claim: {claims[0].get('text', '')[:100]}...")

    print(f"\n--- Source ---")
    print(f"  File: {patent.get('source_file')}")
    print(f"  Language: {patent.get('language')}")


def list_zip_contents(zip_path: Path) -> None:
    """
    List all files inside a zip archive without extracting.

    Args:
        zip_path: Path to the zip file
    """
    print(f"\nContents of {zip_path.name}:")
    with zipfile.ZipFile(zip_path, 'r') as zf:
        for info in zf.infolist():
            print(f"  {info.filename} ({info.file_size:,} bytes)")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Process zipped XML patent files"
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List contents of zip files without extracting"
    )
    parser.add_argument(
        "--data-dir",
        type=str,
        default=None,
        help="Custom data directory path (default: ./data_management/data)"
    )
    parser.add_argument(
        "--zip",
        type=str,
        default=None,
        help="Process specific zip file only"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit number of patents to extract per file"
    )
    parser.add_argument(
        "--sample",
        action="store_true",
        help="Show detailed sample of first patent extracted"
    )
    parser.add_argument(
        "--save",
        action="store_true",
        help="Save extracted patents to the SQLite database"
    )

    args = parser.parse_args()

    # Allow custom data directory
    if args.data_dir:
        data_dir = Path(args.data_dir)
    else:
        data_dir = DATA_DIR

    if args.list:
        zip_files = find_zipped_xml_files(data_dir)
        for zip_file in zip_files:
            list_zip_contents(zip_file)
    else:
        results = extract_all_patents(
            data_dir,
            zip_name=args.zip,
            limit=args.limit,
            save_to_db=args.save
        )

        # Print sample results
        if results and args.sample:
            print_patent_sample(results[0], 1)
        elif results:
            print(f"\n--- Sample Results (first 3) ---")
            for i, result in enumerate(results[:3]):
                print(f"\nPatent {i+1}:")
                print(f"  Publication: {result.get('publication_number')}")
                print(f"  Title: {result.get('title', 'N/A')[:80]}...")
                print(f"  Inventors: {len(result.get('inventors', []))}")
                print(f"  Applicants: {len(result.get('applicants', []))}")
                print(f"  Claims: {len(result.get('claims', []))}")
