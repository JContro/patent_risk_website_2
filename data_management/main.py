#!/usr/bin/env python3
"""
Patent XML to JSON Converter - CLI Entry Point
Extracts patent data from XML or ZIP file with multiple patent documents and saves as JSON.
Supports filtering by keywords in title, abstract, and claims.
"""

import sys
import os
import gc
import json
import tempfile
import shutil
import zipfile

from tqdm import tqdm

# Import from modular components
from . import database
from . import xml_parser
from . import search
from . import filters
from . import file_io


def run_search(patents, search_query, source_file, entity_query=None, cpc_query=None,
               start_date=None, end_date=None, document_type=None, jurisdiction=None):
    """
    Apply boolean search queries to a list of patent records.

    *search_query* matches against patent content (title, abstract, claims,
    description).  *entity_query* matches against entity names only
    (inventors, applicants, assignees/owners).  *cpc_query* is a
    comma-separated list of CPC code patterns with optional ``*`` wildcards.
    *start_date* and *end_date* filter by patent date (datetime or string).
    *document_type* filters by document type ('Granted_patent' or 'Application').
    *jurisdiction* filters by country code (e.g., 'US').
    When multiple queries are supplied a patent must satisfy **all** of them.

    Save matching patents to ``search_<hash>.json`` and print a summary.
    """
    content_ast = None
    entity_ast = None
    cpc_patterns = None

    if search_query:
        print(f"\nParsing content search query: {search_query}")
        try:
            content_ast = search.parse_search_query(search_query)
        except ValueError as e:
            print(f"Error: {e}")
            sys.exit(1)
        print(f"Parsed content AST: {content_ast}")

    if entity_query:
        print(f"\nParsing entity search query: {entity_query}")
        try:
            entity_ast = search.parse_search_query(entity_query)
        except ValueError as e:
            print(f"Error: {e}")
            sys.exit(1)
        print(f"Parsed entity AST: {entity_ast}")

    if cpc_query:
        raw_patterns = [p.strip() for p in cpc_query.split(",") if p.strip()]
        cpc_patterns = [filters.cpc_pattern_to_regex(p) for p in raw_patterns]
        print(f"\nCPC patterns: {raw_patterns}")

    # Parse date filters
    parsed_start_date = None
    parsed_end_date = None
    if start_date:
        parsed_start_date = filters.parse_date(start_date) if isinstance(start_date, str) else start_date
        print(f"\nDate range: {start_date} to {end_date or 'present'}")
    if end_date:
        parsed_end_date = filters.parse_date(end_date) if isinstance(end_date, str) else end_date
    
    if document_type:
        print(f"\nDocument type: {document_type}")
    if jurisdiction:
        print(f"\nJurisdiction: {jurisdiction}")

    # Filter patents — must match ALL supplied queries
    total_before = len(patents)

    def patent_matches(p):
        if content_ast and not search.matches_search(p, content_ast):
            return False
        if entity_ast and not search.matches_entity_search(p, entity_ast):
            return False
        if cpc_patterns and not filters.matches_cpc_search(p, cpc_patterns):
            return False
        if parsed_start_date or parsed_end_date:
            if not filters.matches_date_range(p, parsed_start_date, parsed_end_date):
                return False
        if document_type:
            if not filters.matches_document_type(p, document_type):
                return False
        if jurisdiction:
            if not filters.matches_jurisdiction(p, jurisdiction):
                return False
        return True

    matched = [p for p in patents if patent_matches(p)]

    if not matched:
        print(
            f"\n⚠️  No patents matched the search query out of {total_before} records.")
        sys.exit(0)

    # Build output filename from combined query hash
    combined_query = (search_query or "") + "|" + \
        (entity_query or "") + "|" + (cpc_query or "")
    qhash = search.search_hash(combined_query)
    output_file = f"search_{qhash}.json"

    # Save search to database if patents exist in database
    search_obj = None
    try:
        from accounts.models import Patent, Search
        db_patent_count = Patent.objects.count()
        if db_patent_count > 0:
            # Get patent IDs from matched patents (by publication number)
            patent_ids = []
            for p in matched:
                pub = p.get('publication', {})
                pub_num = pub.get('doc_number')
                if pub_num:
                    db_patent = Patent.objects.filter(publication_number=pub_num).first()
                    if db_patent:
                        patent_ids.append(db_patent.patent_id)
            
            if patent_ids:
                # Create or get search record
                query_description = combined_query
                search_obj = database.save_search_to_db(qhash, query_description, patent_ids)
                if search_obj:
                    print(f"  ✓ Search saved to database with {len(patent_ids)} attributed patents")
    except Exception as e:
        print(f"  Note: Could not save search to database: {e}")

    # Collect distinct entities from matched patents
    entities = search.collect_distinct_entities(matched)

    # Save entities to database
    entity_count = 0
    if search_obj:
        entity_count = database.save_entities_to_db(entities, search_obj=search_obj)

    # Summary (minimal output)
    print(f"\n✓ Search matched {len(matched)} / {total_before} patents")
    if search_obj:
        print(f"✓ Search saved to database")
    if entity_count > 0:
        print(f"✓ Saved {entity_count} entities to database")


def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print(
            "  python main.py <xml_or_zip_file_or_dir> [output.json] [--keywords kw1,kw2,...]")
        print("  python main.py <xml_or_zip_or_json_file_or_dir> --search '<query>'")
        print("  python main.py <xml_or_zip_or_json_file_or_dir> --search-entity '<query>'")
        print("  python main.py <xml_or_zip_or_json_file_or_dir> --search-cpc '<pattern>'")
        print("\nExtracts patents from XML/ZIP and saves as JSON.")
        print("When a directory is given, all ZIP files inside it are")
        print("processed sequentially.\n")
        print("Searches patent JSON with boolean queries.\n")
        print("Options:")
        print(
            "  --keywords       Comma-separated list of keywords to filter during extraction")
        print(
            "                   (e.g., --keywords computer vision,AI,artificial intelligence)")
        print(
            "  --search         Boolean search on patent content (title, abstract,")
        print('                   claims, description).  Supports AND, OR, parentheses,')
        print('                   and quoted phrases.  Case-insensitive.')
        print("  --search-entity  Boolean search on entity names only (inventors,")
        print('                   applicants, assignees/owners).  Same syntax as --search.')
        print("  --search-cpc     Comma-separated CPC code patterns with wildcard *.")
        print(
            '                   Supports class_cpc.symbol: syntax (e.g., class_cpc.symbol:G06N*).')
        print('                   A patent matches if ANY of its CPC codes match ANY pattern.')
        print('  --start-date     Filter patents from this date (MM/DD/YYYY, YYYY-MM-DD, or YYYYMMDD)')
        print('  --end-date       Filter patents until this date (MM/DD/YYYY, YYYY-MM-DD, or YYYYMMDD)')
        print('  --document-type  Filter by document type: Granted_patent or Application')
        print('  --jurisdiction   Filter by jurisdiction/country code (e.g., US, EP, WO)')
        print('                   All search flags can be combined (all must match).')
        print('                Examples:')
        print('                  --search "machine learning"')
        print('                  --search \'"machine learning" AND "neural networks"\'')
        print('                  --search-entity "Microsoft"')
        print('                  --search-entity \'"Samsung" OR "Apple"\'')
        print('                  --search-cpc "G06F*"')
        print('                  --search-cpc "class_cpc.symbol:G06N*"')
        print('                  --search-cpc "G06N*,G06F21*"')
        print('                  --search "neural" --search-entity "Google" --search-cpc "G06N*"')
        print('                  --search "AI" --start-date 04/01/2021 --end-date 04/01/2025 --jurisdiction US --document-type Granted_patent --search-cpc "G06N*"')
        print('\n  Directory mode (sequential):')
        print('                  python main.py data/ --search "battery"')
        print('                  python main.py data/ --search-cpc "H01M*"')
        print('\n  Database options:')
        print('                  --save-db         Save extracted patents to database')
        sys.exit(1)

    # Parse command line arguments
    input_file = sys.argv[1]
    keywords = None
    search_query = None
    entity_query = None
    cpc_query = None
    start_date = None
    end_date = None
    document_type = None
    jurisdiction = None
    save_to_db = False

    # Collect flags
    i = 2
    while i < len(sys.argv):
        arg = sys.argv[i]
        if arg == "--keywords" and i + 1 < len(sys.argv):
            keyword_arg = sys.argv[i + 1]
            keywords = [k.strip() for k in keyword_arg.split(',') if k.strip()]
            i += 2
            continue
        if arg == "--search" and i + 1 < len(sys.argv):
            search_query = sys.argv[i + 1]
            i += 2
            continue
        if arg == "--search-entity" and i + 1 < len(sys.argv):
            entity_query = sys.argv[i + 1]
            i += 2
            continue
        if arg == "--search-cpc" and i + 1 < len(sys.argv):
            cpc_query = sys.argv[i + 1]
            i += 2
            continue
        if arg == "--start-date" and i + 1 < len(sys.argv):
            start_date = sys.argv[i + 1]
            i += 2
            continue
        if arg == "--end-date" and i + 1 < len(sys.argv):
            end_date = sys.argv[i + 1]
            i += 2
            continue
        if arg == "--document-type" and i + 1 < len(sys.argv):
            document_type = sys.argv[i + 1]
            i += 2
            continue
        if arg == "--jurisdiction" and i + 1 < len(sys.argv):
            jurisdiction = sys.argv[i + 1]
            i += 2
            continue
        if arg == "--save-db":
            save_to_db = True
            i += 1
            continue
        if not arg.startswith('--'):
            output_file = arg
        i += 1

    # ---- Search-only mode on an existing JSON file ----
    if input_file.lower().endswith('.json'):
        if not search_query and not entity_query and not cpc_query and not start_date and not end_date and not document_type and not jurisdiction:
            print(
                "Error: When the input is a JSON file, at least one search filter is required.")
            sys.exit(1)
        print(f"Loading patents from: {input_file}")
        try:
            patents, _meta = file_io.load_patents_from_json(input_file)
        except (FileNotFoundError, ValueError, json.JSONDecodeError) as e:
            print(f"Error loading {input_file}: {e}")
            sys.exit(1)
        print(f"Loaded {len(patents)} patents")
        run_search(patents, search_query, source_file=input_file,
                   entity_query=entity_query, cpc_query=cpc_query,
                   start_date=start_date, end_date=end_date,
                   document_type=document_type, jurisdiction=jurisdiction)
        # Explicitly release memory after search
        del patents
        del _meta
        gc.collect()
        return

    # ---- Directory mode: sequential processing of all ZIPs ----
    if os.path.isdir(input_file):
        if keywords:
            print(f"Filtering patents containing keywords: {keywords}")
        
        # Create Search record for directory
        search_obj = None
        if save_to_db:
            try:
                from accounts.models import Search
                dir_hash = search.search_hash(input_file)
                search_obj, _ = Search.objects.get_or_create(
                    search_hash=dir_hash,
                    defaults={'search_query': f'Extracted from directory {os.path.basename(input_file)}'}
                )
            except Exception as e:
                print(f"    Warning: Failed to create search record: {e}")
        
        # Define callback for saving patents with search
        def save_patent_cb(patent_data, search_obj):
            return database.save_patent_with_search(patent_data, search_obj)
        
        all_patents, source_files = file_io.read_all_zips_sequential(
            input_file, keywords, save_to_db=save_to_db, 
            save_patent_with_search=lambda p, s: save_patent_cb(p, search_obj) if save_to_db else None)
        
        source_label = ", ".join(os.path.basename(f) for f in source_files)

        if not all_patents:
            print(f"\n⚠️  No patents extracted from ZIP files in {input_file}")
            if keywords:
                print(f"   No patents matched the keywords: {keywords}")
            sys.exit(0)

        # Collect distinct entities across all patents
        entities = search.collect_distinct_entities(all_patents)

        # If any search flag was supplied, apply it now
        if search_query or entity_query or cpc_query or start_date or end_date or document_type or jurisdiction:
            run_search(all_patents, search_query,
                       source_file=source_label, entity_query=entity_query,
                       cpc_query=cpc_query, start_date=start_date, end_date=end_date,
                       document_type=document_type, jurisdiction=jurisdiction)
            return

        # No search flags — save to database or show summary
        if save_to_db:
            entity_count = database.save_entities_to_db(entities, search_obj=search_obj)
            print(f"\n✓ Extracted {len(all_patents)} patents")
            print(f"✓ Saved {entity_count} entities to database")
        else:
            print(f"\n✓ Extracted {len(all_patents)} patents")
            print(f"✓ Distinct entities: {len(entities['all'])} total")

        return

    # ---- Extraction mode (single XML / ZIP file) ----
    if keywords:
        print(f"Filtering patents containing keywords: {keywords}")
    print(f"Processing file: {input_file}")

    # Check if it's a ZIP file - use memory-efficient processing
    if input_file.lower().endswith('.zip'):
        temp_dir = None
        try:
            temp_dir = tempfile.mkdtemp(prefix='patent_extract_')
            
            # Extract ZIP to temp directory
            print(f"  Extracting to temp directory...")
            with zipfile.ZipFile(input_file, 'r') as zip_ref:
                zip_ref.extractall(temp_dir)
            
            # Find all XML files in the extracted directory
            xml_files = sorted([
                os.path.join(root, f)
                for root, _, files in os.walk(temp_dir)
                for f in files if f.lower().endswith('.xml')
            ])
            
            if not xml_files:
                print(f"\n⚠️ No XML files found in {input_file}")
                sys.exit(0)
            
            print(f"  Found {len(xml_files)} XML files")
            
            # Reset error counters for this run
            file_io.reset_parsing_errors()
            
            # Create Search record for this file
            search_obj = None
            if save_to_db:
                try:
                    from accounts.models import Search
                    file_hash = search.search_hash(input_file)
                    search_obj, _ = Search.objects.get_or_create(
                        search_hash=file_hash,
                        defaults={'search_query': f'Extracted from {os.path.basename(input_file)}'}
                    )
                except Exception as e:
                    print(f"    Warning: Failed to create search record: {e}")
            
            # Process each XML file one at a time
            all_patents = []
            saved_count = 0
            total_count = 0
            
            for xml_file in tqdm(xml_files, desc="Processing XML files", leave=False):
                for patent_data in file_io.process_xml_file_sequential(xml_file, keywords):
                    # If saving to DB, do it immediately
                    if save_to_db and search_obj:
                        if database.save_patent_with_search(patent_data, search_obj):
                            saved_count += 1
                    else:
                        all_patents.append(patent_data)
                    
                    total_count += 1
                    gc.collect()
            
            print(f"  ✓ Processed {total_count} patents")
            if save_to_db:
                print(f"  ✓ Saved {saved_count} patents to database")
            
            # Print error summary
            file_io.print_parsing_errors()
            
            # If no search query and saving to DB, we're done
            if save_to_db and not (search_query or entity_query or cpc_query or start_date or end_date or document_type or jurisdiction):
                return
            
            # If we have search queries but saved to DB, we need to reload for search
            # For now, just return if saving to DB
            if save_to_db:
                print("\n✓ Extraction complete (search not supported with --save-db for single ZIP)")
                return
                
        finally:
            # Clean up temp directory
            if temp_dir and os.path.exists(temp_dir):
                try:
                    shutil.rmtree(temp_dir)
                except Exception as e:
                    print(f"    Warning: Failed to clean up temp directory: {e}")
    else:
        # Regular XML file processing
        all_patents = file_io.read_xml_content(input_file, keywords)

    if not all_patents:
        print(f"\n⚠️ No patents extracted from {input_file}")
        if keywords:
            print(f"   No patents matched the keywords: {keywords}")
        sys.exit(0)

    # Collect distinct entities across all patents
    entities = search.collect_distinct_entities(all_patents)

    # If any search flag was supplied alongside extraction, apply it now
    if search_query or entity_query or cpc_query or start_date or end_date or document_type or jurisdiction:
        run_search(all_patents, search_query,
                   source_file=input_file, entity_query=entity_query,
                   cpc_query=cpc_query, start_date=start_date, end_date=end_date,
                   document_type=document_type, jurisdiction=jurisdiction)
        return

    # Save entities to database
    if save_to_db:
        entity_count = database.save_entities_to_db(entities)
        print(f"\n✓ Extracted {len(all_patents)} patents")
        print(f"✓ Saved {entity_count} entities to database")
    else:
        print(f"\n✓ Extracted {len(all_patents)} patents")
        print(f"✓ Distinct entities: {len(entities['all'])} total")


if __name__ == "__main__":
    main()
