"""
File I/O utilities for reading patent data from XML, ZIP, and JSON files.
"""

import json
import zipfile
import os
import glob
import gzip
import gc
import xml.etree.ElementTree as ET
from tqdm import tqdm

from .xml_parser import extract_patent, contains_keywords
from .search import search_hash


# Global error counters for tracking parsing issues
PARSING_ERRORS = {
    'xml_parse_errors': 0,
    'extract_patent_errors': 0,
    'missing_root_tag': 0,
    'keyword_filter_errors': 0,
    'other_errors': 0,
}


def reset_parsing_errors():
    """Reset all error counters to zero."""
    global PARSING_ERRORS
    PARSING_ERRORS = {
        'xml_parse_errors': 0,
        'extract_patent_errors': 0,
        'missing_root_tag': 0,
        'keyword_filter_errors': 0,
        'other_errors': 0,
    }


def print_parsing_errors():
    """Print a summary of parsing errors that occurred."""
    total_errors = sum(PARSING_ERRORS.values())
    print(f"\n{'='*60}")
    print("PARSING ERROR SUMMARY")
    print(f"{'='*60}")
    print(f"  XML Parse Errors:        {PARSING_ERRORS['xml_parse_errors']}")
    print(f"  Extract Patent Errors:   {PARSING_ERRORS['extract_patent_errors']}")
    print(f"  Missing Root Tag Errors: {PARSING_ERRORS['missing_root_tag']}")
    print(f"  Keyword Filter Errors:   {PARSING_ERRORS['keyword_filter_errors']}")
    print(f"  Other Errors:            {PARSING_ERRORS['other_errors']}")
    print(f"  ─────────────────────────────────")
    print(f"  TOTAL ERRORS:            {total_errors}")
    print(f"{'='*60}\n")


def load_patents_from_json(json_path):
    """Load patent records from a previously-saved JSON file."""
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    if isinstance(data, dict) and "patents" in data:
        return data["patents"], data
    if isinstance(data, list):
        return data, None
    raise ValueError(
        f"{json_path} does not contain a recognised patent JSON structure")


def parse_xml_content(content, source_name, keywords=None):
    """
    Parse XML content and extract patents, optionally filtering by keywords.
    Tracks and reports parsing errors.
    """
    global PARSING_ERRORS
    
    # Split by XML declarations to handle multiple documents
    fragments = content.split('<?xml')
    fragments = [f for f in fragments if f.strip()]

    if len(fragments) > 1:
        fragments = ['<?xml' + f for f in fragments]
    else:
        fragments = [content]

    all_patents = []

    for fragment in tqdm(fragments, desc=source_name[:30], leave=False):
        try:
            # Add XML declaration if missing
            if not fragment.strip().startswith('<?xml'):
                fragment = '<?xml version="1.0"?>\n' + fragment

            root = ET.fromstring(fragment)

            # Check if root is a patent application or grant
            if root.tag in ['us-patent-application', 'us-patent-grant']:
                try:
                    patent_data = extract_patent(root)

                    # Filter by keywords if provided
                    if keywords:
                        try:
                            if not contains_keywords(patent_data, keywords):
                                continue
                        except Exception as e:
                            PARSING_ERRORS['keyword_filter_errors'] += 1
                            print(f"    Warning: Keyword filter error in {source_name}: {e}")
                            continue

                    all_patents.append(patent_data)
                except Exception as e:
                    PARSING_ERRORS['extract_patent_errors'] += 1
                    print(f"    Warning: Extract patent error in {source_name}: {e}")
                    continue
            else:
                PARSING_ERRORS['missing_root_tag'] += 1
                # Only print first few to avoid spam
                if PARSING_ERRORS['missing_root_tag'] <= 3:
                    print(f"    Warning: Unknown root tag '{root.tag}' in {source_name}")

        except ET.ParseError as e:
            PARSING_ERRORS['xml_parse_errors'] += 1
            # Only print first few to avoid spam
            if PARSING_ERRORS['xml_parse_errors'] <= 3:
                print(f"    Warning: XML parse error in {source_name}: {e}")
            continue
        except Exception as e:
            PARSING_ERRORS['other_errors'] += 1
            # Only print first few to avoid spam
            if PARSING_ERRORS['other_errors'] <= 3:
                print(f"    Warning: Unexpected error in {source_name}: {e}")
            continue

    return all_patents


def process_xml_file_sequential(xml_file_path, keywords=None):
    """
    Process a single XML file and yield patents one at a time.
    Uses iterparse for streaming XML parsing to avoid loading entire file into memory.
    
    Note: This works for single XML documents. For files with multiple concatenated
    XML documents, use parse_xml_content instead.
    
    Args:
        xml_file_path: Path to the XML file
        keywords: Optional keywords to filter patents
        
    Yields:
        Patent dictionaries one at a time
    """
    global PARSING_ERRORS
    
    try:
        # Use iterparse for streaming XML parsing
        # This doesn't load the entire tree into memory
        context = ET.iterparse(xml_file_path, events=('end',))
        
        # Keep track of elements to clear for memory management
        ancestors = {}
        
        for event, elem in context:
            # Track ancestors for proper cleanup
            if event == 'start':
                ancestors[elem] = None  # Will be updated when we have parent info
            elif event == 'end':
                # Check if this is a patent element
                if elem.tag in ['us-patent-application', 'us-patent-grant']:
                    try:
                        patent_data = extract_patent(elem)
                        
                        # Filter by keywords if provided
                        if keywords and not contains_keywords(patent_data, keywords):
                            # Clear element from memory
                            elem.clear()
                            continue
                        
                        yield patent_data
                        
                    except Exception as e:
                        # Clear element from memory on error
                        PARSING_ERRORS['extract_patent_errors'] += 1
                        if PARSING_ERRORS['extract_patent_errors'] <= 5:
                            print(f"    Warning: Extract patent error in {xml_file_path}: {e}")
                        elem.clear()
                        continue
                    finally:
                        # Always clear the element to free memory
                        elem.clear()
                
                # Remove from ancestors if present
                if elem in ancestors:
                    del ancestors[elem]
                    
    except FileNotFoundError:
        PARSING_ERRORS['other_errors'] += 1
        print(f"Error: File '{xml_file_path}' not found")
    except ET.ParseError as e:
        PARSING_ERRORS['xml_parse_errors'] += 1
        if PARSING_ERRORS['xml_parse_errors'] <= 5:
            print(f"XML parse error in {xml_file_path}: {e}")
    except Exception as e:
        PARSING_ERRORS['other_errors'] += 1
        if PARSING_ERRORS['other_errors'] <= 5:
            print(f"Error processing {xml_file_path}: {e}")


def read_xml_content(file_path, keywords=None):
    """
    Read XML content from a file (plain XML or from ZIP archive).
    Returns extracted patents filtered by keywords if provided.
    """
    # Check if file is a ZIP archive
    if file_path.lower().endswith('.zip'):
        try:
            with zipfile.ZipFile(file_path, 'r') as zip_ref:
                # Find XML files in the archive
                xml_files = [f for f in zip_ref.namelist(
                ) if f.lower().endswith('.xml')]
                if not xml_files:
                    print(
                        f"Error: No XML files found in ZIP archive {file_path}")
                    return []

                all_patents = []

                for xml_file in tqdm(xml_files, desc=os.path.basename(file_path), leave=False):
                    try:
                        with zip_ref.open(xml_file, 'r') as xml_content:
                            content = xml_content.read().decode('utf-8', errors='replace')
                            patents = parse_xml_content(
                                content, xml_file, keywords)
                            all_patents.extend(patents)
                    except Exception as e:
                        global PARSING_ERRORS
                        PARSING_ERRORS['other_errors'] += 1
                        if PARSING_ERRORS['other_errors'] <= 5:
                            print(f"Warning: Could not process {xml_file}: {e}")
                        continue

                return all_patents

        except zipfile.BadZipFile:
            print(f"Error: {file_path} is not a valid ZIP file")
            return []

    # Regular XML file - use tqdm for progress
    try:
        with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()
        return parse_xml_content(content, file_path, keywords)
    except FileNotFoundError:
        print(f"Error: File '{file_path}' not found")
        return []


def read_all_zips_sequential(data_dir, keywords=None, save_to_db=False, save_patent_with_search=None):
    """
    Discover all .zip files in *data_dir* and extract patents from each
    sequentially (one at a time) to keep memory usage low.
    
    This version extracts each ZIP to a temp directory and processes files
    one at a time to avoid running out of memory with large archives.

    Args:
        data_dir: Directory containing ZIP files
        keywords: Optional keywords to filter patents during extraction
        save_to_db: If True, save extracted patents to the database
        save_patent_with_search: Optional callback function for saving patents

    Returns a tuple of (all_patents, source_files) where *all_patents* is
    the combined list of patent dicts and *source_files* is the list of
    ZIP paths that were processed.
    """
    import tempfile
    import shutil
    
    global PARSING_ERRORS
    reset_parsing_errors()
    
    zip_files = sorted(glob.glob(os.path.join(data_dir, '*.zip')))
    if not zip_files:
        print(f"⚠️  No ZIP files found in {data_dir}")
        return [], []

    print(f"\nFound {len(zip_files)} ZIP file(s) in {data_dir}")

    all_patents = []
    processed_count = 0
    total_patents_saved = 0
    
    # Use tqdm for progress tracking
    with tqdm(zip_files, desc="Processing ZIPs") as pbar:
        for zip_path in pbar:
            zip_name = os.path.basename(zip_path)
            pbar.set_postfix_str(zip_name)
            
            # Create temp directory for extraction
            temp_dir = None
            try:
                temp_dir = tempfile.mkdtemp(prefix='patent_extract_')
                
                # Extract ZIP to temp directory
                print(f"\n  Extracting {zip_name} to temp directory...")
                with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                    zip_ref.extractall(temp_dir)
                
                # Find all XML files in the extracted directory
                xml_files = sorted([
                    os.path.join(root, f)
                    for root, _, files in os.walk(temp_dir)
                    for f in files if f.lower().endswith('.xml')
                ])
                
                if not xml_files:
                    print(f"  Warning: No XML files found in {zip_name}")
                    continue
                
                print(f"  Found {len(xml_files)} XML files in {zip_name}")
                
                # Process each XML file one at a time
                file_count = 0
                for xml_file in tqdm(xml_files, desc=f"  {zip_name[:20]}", leave=False):
                    # Process file and yield patents one at a time
                    for patent_data in process_xml_file_sequential(xml_file, keywords):
                        # If save_to_db, save immediately and don't accumulate
                        if save_to_db and save_patent_with_search:
                            if save_patent_with_search(patent_data, None):
                                total_patents_saved += 1
                        else:
                            # Only keep in memory if not saving to DB
                            all_patents.append(patent_data)
                        
                        file_count += 1
                        
                        # Force GC after each patent to prevent memory buildup
                        gc.collect()
                
                processed_count += 1
                print(f"  ✓ Processed {file_count} patents from {zip_name}")
                
            except Exception as e:
                print(f"\n  ✗ {zip_name}: Error – {e}")
                continue
                
            finally:
                # Clean up temp directory
                if temp_dir and os.path.exists(temp_dir):
                    try:
                        shutil.rmtree(temp_dir)
                    except Exception as e:
                        print(f"    Warning: Failed to clean up temp directory: {e}")

    print(f"\nTotal patents extracted from all ZIPs: {len(all_patents)}")
    if save_to_db:
        print(f"Total patents saved to database: {total_patents_saved}")
    
    # Print error summary
    print_parsing_errors()
    
    return all_patents, zip_files
