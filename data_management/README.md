# Patent XML Data Extraction

This module processes USPTO (United States Patent and Trademark Office) patent grant XML files from the IBM Patent Grant Weekly XML collections.

## Data Source

The XML files are located in [`data_management/data/`](data_management/data/) and contain weekly patent grant data from 2022-2026. Each zip file (e.g., `ipg220215.zip`) contains one XML file with all patents granted that week.

### File Format

- **Format**: USPTO Patent Grant XML (DTD v4.6)
- **Content**: Weekly patent grants (both design and utility patents)
- **Size**: Each zip contains ~6000-7000 patents (~500MB-1GB compressed)

## Installation

The script uses only Python standard library modules:
- `zipfile` - Reading compressed XML files
- `xml.etree.ElementTree` - Parsing XML content
- `pathlib` - File path handling
- `re` - Regular expressions for multi-document XML parsing
- `datetime` - Date parsing

No additional dependencies required.

## Usage

### Basic Commands

```bash
# Extract all patents from all zip files
docker compose exec web python data_management/extract_xml.py

# Extract from a specific zip file
docker compose exec web python data_management/extract_xml.py --zip ipg220215.zip

# Limit number of patents per file (useful for testing)
docker compose exec web python data_management/extract_xml.py --limit 100

# List contents of zip files without extracting
docker compose exec web python data_management/extract_xml.py --list

# Show detailed sample of first patent
docker compose exec web python data_management/extract_xml.py --zip ipg220215.zip --limit 1 --sample

# Extract and save to database (SQLite)
docker compose exec web python data_management/extract_xml.py --save --limit 100
```

### Command-Line Options

| Option | Description | Default |
|--------|-------------|---------|
| `--list` | List contents of zip files without extracting | False |
| `--data-dir` | Custom data directory path | `data_management/data` |
| `--zip` | Process specific zip file only | All files |
| `--limit` | Limit patents per file (None = all) | None |
| `--sample` | Show detailed sample of first patent | False |
| `--save` | Save extracted patents to SQLite database | False |

## Output Schema

The extracted data maps to the [`Patent` model](accounts/models.py:36):

### Publication Info
| Field | Type | Description |
|-------|------|-------------|
| `publication_country` | str | Country code (US) |
| `publication_number` | str | Patent number (e.g., "11246252") |
| `publication_kind` | str | Publication kind (e.g., "B2", "S1") |
| `publication_date` | date | Publication date |

### Application Info
| Field | Type | Description |
|-------|------|-------------|
| `application_type` | str | "utility" or "design" |
| `application_number` | str | Application number |
| `application_date` | date | Application filing date |
| `application_series_code` | str | Application series code |

### Core Content
| Field | Type | Description |
|-------|------|-------------|
| `title` | str | Patent title |
| `abstract` | str | Patent abstract (utility patents only) |

### Classifications
| Field | Type | Description |
|-------|------|-------------|
| `classifications_ipcr` | list | IPCR classifications |
| `classifications_cpc_main` | list | CPC primary classifications |
| `classifications_cpc_further` | list | CPC secondary classifications |

### People & Organizations
| Field | Type | Description |
|-------|------|-------------|
| `inventors` | list | List of inventors with name/address |
| `applicants` | list | List of applicants with name/address |

### Claims
| Field | Type | Description |
|-------|------|-------------|
| `claims` | list | List of claims with id, num, text |
| `priority_claims` | list | Priority claim information |

### Metadata
| Field | Type | Description |
|-------|------|-------------|
| `source_file` | str | Source zip filename |
| `language` | str | Document language (EN) |
| `production_date` | date | XML production date |

## Patent Types

### Utility Patents
- Have abstracts
- Multiple claims (typically 10-30)
- Full IPCR and CPC classifications
- Application type: "utility"

### Design Patents
- No abstract
- Single claim (ornamental design)
- Limited classifications (Locarno, US national)
- Application type: "design"

## Example Output

```
=== Starting Patent Extraction ===
Data directory: /app/data_management/data

Found 222 zip file(s) in /app/data_management/data

Processing: ipg220215.zip
  Processing ipg220215.zip: 1 XML file(s) found
    Extracted 700 patent(s) from ipg220215.xml
  Total extracted so far: 700

=== Extraction Complete ===
Total patents extracted: 700

--- Sample Results (first 3) ---

Patent 1:
  Publication: 11246252
  Title: Pick-up hitch assembly...
  Inventors: 2
  Applicants: 1
  Claims: 20
```

## Performance Notes

- Processing 7000 patents takes approximately 30-60 seconds
- Memory usage is moderate (streams XML from zip file)
- Each zip file contains one large XML with multiple concatenated documents

## Integration with Django

To save extracted patents to the database:

```python
from data_management.extract_xml import extract_all_patents
from accounts.models import Patent
from pathlib import Path

# Extract patents
patents_data = extract_all_patents(
    Path('data_management/data'),
    zip_name='ipg220215.zip',
    limit=100
)

# Save to database
for data in patents_data:
    patent = Patent(**data)
    patent.save()
```

## File Structure

```
patent_risk_website_2/
├── data_management/
│   ├── __init__.py
│   ├── extract_xml.py      # Main extraction script
│   ├── README.md           # This file
│   └── data/               # USPTO XML zip files
│       ├── ipg220215.zip
│       ├── ipg220308.zip
│       └── ...