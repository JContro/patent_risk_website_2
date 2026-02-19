# Patent Data Processing Tool

This tool extracts patent data from XML or ZIP files containing USPTO patent documents and provides powerful search capabilities.

## Features

- Extract patents from XML files, ZIP archives, or directories containing multiple ZIP files
- Filter patents during extraction using keywords
- Search patents using boolean queries on:
  - Patent content (title, abstract, claims, description)
  - Entity names (inventors, applicants, assignees/owners)
  - CPC classification codes with wildcard support
- Combine multiple search criteria with AND logic
- Generate JSON output with distinct entity lists

## Usage

```bash
# Extract patents from a single file
python main.py <xml_or_zip_file> [output.json] [--keywords kw1,kw2,...]

# Extract patents from all ZIP files in a directory (processed sequentially)
python main.py <directory_path> [output.json] [--keywords kw1,kw2,...]

# Search existing patent JSON file
python main.py <json_file> --search '<query>'
python main.py <json_file> --search-entity '<query>'
python main.py <json_file> --search-cpc '<pattern>'
```

## Command Line Options

### --keywords
Filter patents during extraction by keywords in title or abstract.

Example:
```bash
python main.py data/ipa260115.zip --keywords "artificial intelligence,neural network"
```

### --search
Boolean search on patent content (title, abstract, claims, description).

Supports:
- Quoted phrases: `"machine learning"`
- AND/OR operators: `"machine learning" AND "neural networks"`
- Parentheses for grouping: `("machine learning" AND "neural") OR "deep learning"`
- Case-insensitive matching

Example:
```bash
python main.py patents.json --search '"machine learning" AND "neural networks"'
```

### --search-entity
Boolean search on entity names only (inventors, applicants, assignees/owners).

Uses the same syntax as `--search`.

Example:
```bash
python main.py patents.json --search-entity "Microsoft"
python main.py patents.json --search-entity '"Samsung" OR "Apple"'
```

### --search-cpc
Search by CPC (Cooperative Patent Classification) codes with wildcard support.

- Comma-separated patterns (OR logic - matches if ANY pattern hits)
- `*` matches any sequence of characters
- Case-insensitive matching

Example:
```bash
# All AI/ML patents
python main.py patents.json --search-cpc "G06N*"

# AI/ML or networking patents
python main.py patents.json --search-cpc "G06N*,H04L*"

# Specific subgroup
python main.py patents.json --search-cpc "G06N5/043"
```

## Combining Search Flags

All search flags can be combined with AND logic (a patent must match ALL criteria).

Example:
```bash
# Microsoft AI patents
python main.py patents.json --search-entity "Microsoft" --search-cpc "G06N*"

# Google neural network patents with specific classification
python main.py patents.json --search "neural" --search-entity "Google" --search-cpc "G06N*"

# AI patents by specific companies in a technical field
python main.py patents.json --search-entity '"IBM" OR "Microsoft"' --search-cpc "G06N*,G06F*"
```

## Directory Mode

When a directory path is provided, all ZIP files in that directory are processed sequentially:

```bash
# Process all ZIP files in the data directory
python main.py data/ --search "battery" --search-cpc "H01M*"
```

## Output Files

### Main Output JSON
Contains:
- Search date and query information
- Source file information
- Total patents searched and matched
- List of matching patents with full data
- Reference to entities file

### Entities JSON
Separate file containing distinct entities from matching patents:
- Sorted lists of unique inventors, applicants, assignees
- Combined list of all entities

Example entities structure:
```json
{
  "inventors": ["Alice Smith", "Bob Jones", ...],
  "applicants": ["Acme Corp", ...],
  "assignees": ["Acme Corp", ...],
  "all": ["Acme Corp", "Alice Smith", "Bob Jones", ...]
}
```

## CPC Code Format

CPC codes follow the standard format: `{section}{class}{subclass}{main_group}/{subgroup}`

Examples:
- `G06N5/043` - Artificial Intelligence / Neural networks / Pattern recognition
- `H04L63/00` - Networking / Network security
- `A63F13/67` - Games / Video games / Player interaction

## Examples

### Basic Extraction
```bash
# Extract all patents from a ZIP file
python main.py data/ipa260115.zip

# Extract with keyword filtering
python main.py data/ipa260115.zip --keywords "AI,artificial intelligence"
```

### Content Search
```bash
# Simple term search
python main.py patents.json --search "blockchain"

# Boolean search
python main.py patents.json --search '"machine learning" AND ("neural network" OR "deep learning")'
```

### Entity Search
```bash
# Find patents by specific company
python main.py patents.json --search-entity "Google"

# Find patents by multiple companies
python main.py patents.json --search-entity '"Microsoft" OR "Apple"'

# Find patents by specific inventor
python main.py patents.json --search-entity "John Smith"
```

### CPC Classification Search
```bash
# All AI/ML patents
python main.py patents.json --search-cpc "G06N*"

# Multiple classifications
python main.py patents.json --search-cpc "G06N*,G06F21*"

# Specific subgroup
python main.py patents.json --search-cpc "G06N5/043"
```

### Combined Searches
```bash
# AI patents by Microsoft
python main.py patents.json --search-entity "Microsoft" --search-cpc "G06N*"

# Neural network patents by Google
python main.py patents.json --search "neural network" --search-entity "Google"

# AI patents by major tech companies
python main.py patents.json --search-cpc "G06N*" --search-entity '"Google" OR "Microsoft" OR "Apple" OR "Amazon" OR "Facebook"'
```

### Directory Processing
```bash
# Search across all ZIP files in a directory
python main.py data/ --search "quantum computing" --search-cpc "G06N10*"