#!/usr/bin/env python3
"""
Patent XML to JSON Converter
Extracts patent data from XML or ZIP file with multiple patent documents and saves as JSON.
Supports filtering by keywords in title, abstract, and claims.
"""

import xml.etree.ElementTree as ET
import json
import sys
import zipfile
import os
import re
import hashlib
import glob
from datetime import datetime


def extract_text(element):
    """Extract all text content from an element and its children."""
    if element is None:
        return None
    text = element.text or ""
    for child in element:
        text += extract_text(child) or ""
        text += child.tail or ""
    return text.strip()


def extract_document_id(doc_id_elem):
    """Extract document ID information."""
    if doc_id_elem is None:
        return None

    return {
        "country": extract_text(doc_id_elem.find("country")),
        "doc_number": extract_text(doc_id_elem.find("doc-number")),
        "kind": extract_text(doc_id_elem.find("kind")),
        "date": extract_text(doc_id_elem.find("date"))
    }


def extract_classification(class_elem):
    """Extract classification information."""
    if class_elem is None:
        return None

    return {
        "section": extract_text(class_elem.find("section")),
        "class": extract_text(class_elem.find("class")),
        "subclass": extract_text(class_elem.find("subclass")),
        "main_group": extract_text(class_elem.find("main-group")),
        "subgroup": extract_text(class_elem.find("subgroup")),
        "symbol_position": extract_text(class_elem.find("symbol-position")),
        "classification_value": extract_text(class_elem.find("classification-value")),
        "text": extract_text(class_elem.find("text"))
    }


def extract_person(person_elem):
    """Extract person information from addressbook."""
    if person_elem is None:
        return None

    addressbook = person_elem.find("addressbook")
    if addressbook is None:
        return None

    address_elem = addressbook.find("address")
    address = None
    if address_elem is not None:
        address = {
            "city": extract_text(address_elem.find("city")),
            "state": extract_text(address_elem.find("state")),
            "country": extract_text(address_elem.find("country"))
        }

    return {
        "first_name": extract_text(addressbook.find("first-name")),
        "last_name": extract_text(addressbook.find("last-name")),
        "organization": extract_text(addressbook.find("orgname")),
        "role": extract_text(addressbook.find("role")),
        "address": address,
        "sequence": person_elem.get("sequence")
    }


def extract_claim(claim_elem):
    """Extract claim information."""
    if claim_elem is None:
        return None

    def extract_claim_text(claim_text_elem):
        """Recursively extract claim text."""
        if claim_text_elem is None:
            return None

        text = extract_text(claim_text_elem)

        # Get nested claim-text elements
        nested = []
        for child in claim_text_elem.findall("claim-text"):
            nested_text = extract_claim_text(child)
            if nested_text:
                nested.append(nested_text)

        return {
            "text": text,
            "nested": nested if nested else None
        }

    claim_text = claim_elem.find("claim-text")

    return {
        "id": claim_elem.get("id"),
        "num": claim_elem.get("num"),
        "claim_text": extract_claim_text(claim_text) if claim_text is not None else None
    }


def extract_patent(patent_elem):
    """Extract all data from a single us-patent-application or us-patent-grant element."""

    patent_data = {
        "attributes": {
            "lang": patent_elem.get("lang"),
            "dtd_version": patent_elem.get("dtd-version"),
            "file": patent_elem.get("file"),
            "status": patent_elem.get("status"),
            "id": patent_elem.get("id"),
            "country": patent_elem.get("country"),
            "date_produced": patent_elem.get("date-produced"),
            "date_publ": patent_elem.get("date-publ")
        }
    }

    # Extract bibliographic data
    # Handle both application and grant bibliographic data
    biblio = (patent_elem.find("us-bibliographic-data-application") or
              patent_elem.find("us-bibliographic-data-grant"))
    if biblio is not None:
        # Publication reference
        pub_ref = biblio.find("publication-reference")
        if pub_ref is not None:
            patent_data["publication"] = extract_document_id(
                pub_ref.find("document-id"))

        # Application reference
        app_ref = biblio.find("application-reference")
        if app_ref is not None:
            patent_data["application"] = {
                "appl_type": app_ref.get("appl-type"),
                "document_id": extract_document_id(app_ref.find("document-id"))
            }

        # Application series code
        series_code = biblio.find("us-application-series-code")
        if series_code is not None:
            patent_data["application_series_code"] = extract_text(series_code)

        # Priority claims
        priority_claims = biblio.find("priority-claims")
        if priority_claims is not None:
            patent_data["priority_claims"] = []
            for claim in priority_claims.findall("priority-claim"):
                patent_data["priority_claims"].append({
                    "sequence": claim.get("sequence"),
                    "kind": claim.get("kind"),
                    "document_id": extract_document_id(claim.find("document-id"))
                })

        # IPC Classifications
        ipcr = biblio.find("classifications-ipcr")
        if ipcr is not None:
            patent_data["classifications_ipcr"] = []
            for classification in ipcr.findall("classification-ipcr"):
                class_data = extract_classification(classification)
                if class_data:
                    patent_data["classifications_ipcr"].append(class_data)

        # CPC Classifications
        cpc = biblio.find("classifications-cpc")
        if cpc is not None:
            patent_data["classifications_cpc"] = {
                "main": extract_classification(cpc.find("main-cpc/classification-cpc")),
                "further": []
            }
            further_cpc = cpc.find("further-cpc")
            if further_cpc is not None:
                for classification in further_cpc.findall("classification-cpc"):
                    class_data = extract_classification(classification)
                    if class_data:
                        patent_data["classifications_cpc"]["further"].append(
                            class_data)

        # Invention title
        title = biblio.find("invention-title")
        if title is not None:
            patent_data["title"] = extract_text(title)

        # Inventors
        us_parties = biblio.find("us-parties")
        if us_parties is not None:
            inventors_elem = us_parties.find("inventors")
            if inventors_elem is not None:
                patent_data["inventors"] = []
                for inventor in inventors_elem.findall("inventor"):
                    person = extract_person(inventor)
                    if person:
                        patent_data["inventors"].append(person)

            # Applicants
            applicants_elem = us_parties.find("us-applicants")
            if applicants_elem is not None:
                patent_data["applicants"] = []
                for applicant in applicants_elem.findall("us-applicant"):
                    person = extract_person(applicant)
                    if person:
                        patent_data["applicants"].append(person)

        # Assignees
        assignees_elem = biblio.find("assignees")
        if assignees_elem is not None:
            patent_data["assignees"] = []
            for assignee in assignees_elem.findall("assignee"):
                person = extract_person(assignee)
                if person:
                    patent_data["assignees"].append(person)

    # Abstract
    abstract = patent_elem.find("abstract")
    if abstract is not None:
        patent_data["abstract"] = extract_text(abstract)

    # Claims
    claims = patent_elem.find("claims")
    if claims is not None:
        patent_data["claims"] = []
        for claim in claims.findall("claim"):
            claim_data = extract_claim(claim)
            if claim_data:
                patent_data["claims"].append(claim_data)

    # Description (extract headings and first few paragraphs only to keep size manageable)
    description = patent_elem.find("description")
    if description is not None:
        patent_data["description"] = {
            "headings": [],
            "paragraphs_sample": []
        }

        for heading in description.findall("heading"):
            patent_data["description"]["headings"].append({
                "level": heading.get("level"),
                "text": extract_text(heading)
            })

        # Get first 5 paragraphs as sample
        for i, para in enumerate(description.findall("p")[:5]):
            patent_data["description"]["paragraphs_sample"].append({
                "id": para.get("id"),
                "num": para.get("num"),
                "text": extract_text(para)
            })

    # Drawings info (just metadata, not the actual images)
    drawings = patent_elem.find("drawings")
    if drawings is not None:
        patent_data["drawings"] = {
            "count": len(drawings.findall("figure")),
            "figures": []
        }
        for figure in drawings.findall("figure"):
            patent_data["drawings"]["figures"].append({
                "id": figure.get("id"),
                "num": figure.get("num")
            })

    return patent_data


def contains_keywords(patent_data, keywords):
    """
    Check if patent contains any of the keywords (case-insensitive) in title, abstract, or claims.
    Returns True if any keyword is found in text fields.
    """
    if not keywords:
        return True

    text_fields = []

    # Title
    if "title" in patent_data and patent_data["title"]:
        text_fields.append(patent_data["title"])

    # Abstract
    if "abstract" in patent_data and patent_data["abstract"]:
        text_fields.append(patent_data["abstract"])

    # Claims text
    if "claims" in patent_data and patent_data["claims"]:
        for claim in patent_data["claims"]:
            if claim and "claim_text" in claim and claim["claim_text"]:
                claim_text_obj = claim["claim_text"]
                if isinstance(claim_text_obj, dict) and "text" in claim_text_obj:
                    text_fields.append(claim_text_obj["text"])

    # Combine all text
    combined_text = " ".join(text_fields).lower()

    # Check each keyword
    for keyword in keywords:
        if keyword.lower() in combined_text:
            return True

    return False


# ---------------------------------------------------------------------------
# Boolean Search Query Parser & Evaluator
# ---------------------------------------------------------------------------
# Supports: quoted phrases, AND, OR operators, and parentheses.
# Grammar (case-insensitive operators):
#   expression := or_expr
#   or_expr    := and_expr ( "OR" and_expr )*
#   and_expr   := atom ( "AND" atom )*
#   atom       := "quoted phrase" | "(" expression ")" | bare_word
# ---------------------------------------------------------------------------

class SearchToken:
    """Represents a single token from the search query."""
    AND = "AND"
    OR = "OR"
    LPAREN = "LPAREN"
    RPAREN = "RPAREN"
    PHRASE = "PHRASE"
    EOF = "EOF"

    def __init__(self, kind, value=None):
        self.kind = kind
        self.value = value

    def __repr__(self):
        return f"SearchToken({self.kind}, {self.value!r})"


def tokenize_search(query):
    """
    Tokenise a boolean search query string into a list of SearchTokens.

    Rules:
    - Text inside double-quotes becomes a PHRASE token (the quotes are stripped).
    - The words AND / OR (case-insensitive) become operator tokens.
    - ( and ) become paren tokens.
    - Any other contiguous non-whitespace text becomes a PHRASE token.
    """
    tokens = []
    i = 0
    length = len(query)

    while i < length:
        # Skip whitespace
        if query[i].isspace():
            i += 1
            continue

        # Quoted phrase
        if query[i] == '"':
            i += 1  # skip opening quote
            start = i
            while i < length and query[i] != '"':
                i += 1
            tokens.append(SearchToken(SearchToken.PHRASE, query[start:i]))
            if i < length:
                i += 1  # skip closing quote
            continue

        # Parentheses
        if query[i] == '(':
            tokens.append(SearchToken(SearchToken.LPAREN))
            i += 1
            continue
        if query[i] == ')':
            tokens.append(SearchToken(SearchToken.RPAREN))
            i += 1
            continue

        # Bare word – read until whitespace or paren or quote
        start = i
        while i < length and not query[i].isspace() and query[i] not in '()"':
            i += 1
        word = query[start:i]

        if word.upper() == "AND":
            tokens.append(SearchToken(SearchToken.AND))
        elif word.upper() == "OR":
            tokens.append(SearchToken(SearchToken.OR))
        else:
            tokens.append(SearchToken(SearchToken.PHRASE, word))

    tokens.append(SearchToken(SearchToken.EOF))
    return tokens


# AST node types -----------------------------------------------------------

class PhraseNode:
    """Leaf node: matches if the phrase appears in the text (case-insensitive)."""

    def __init__(self, phrase):
        self.phrase = phrase.lower()

    def __repr__(self):
        return f'Phrase("{self.phrase}")'


class AndNode:
    """Binary node: both children must match."""

    def __init__(self, left, right):
        self.left = left
        self.right = right

    def __repr__(self):
        return f"And({self.left}, {self.right})"


class OrNode:
    """Binary node: at least one child must match."""

    def __init__(self, left, right):
        self.left = left
        self.right = right

    def __repr__(self):
        return f"Or({self.left}, {self.right})"


# Recursive-descent parser -------------------------------------------------

class SearchParser:
    """
    Parse a list of SearchTokens into an AST of PhraseNode / AndNode / OrNode.
    """

    def __init__(self, tokens):
        self.tokens = tokens
        self.pos = 0

    def _current(self):
        return self.tokens[self.pos]

    def _consume(self, expected_kind=None):
        tok = self.tokens[self.pos]
        if expected_kind and tok.kind != expected_kind:
            raise ValueError(
                f"Search parse error: expected {expected_kind}, got {tok.kind} "
                f"(value={tok.value!r}) at token position {self.pos}"
            )
        self.pos += 1
        return tok

    def parse(self):
        node = self._or_expr()
        if self._current().kind != SearchToken.EOF:
            raise ValueError(
                f"Search parse error: unexpected token {self._current()!r} "
                f"at position {self.pos}"
            )
        return node

    def _or_expr(self):
        left = self._and_expr()
        while self._current().kind == SearchToken.OR:
            self._consume(SearchToken.OR)
            right = self._and_expr()
            left = OrNode(left, right)
        return left

    def _and_expr(self):
        left = self._atom()
        while self._current().kind == SearchToken.AND:
            self._consume(SearchToken.AND)
            right = self._atom()
            left = AndNode(left, right)
        return left

    def _atom(self):
        tok = self._current()

        if tok.kind == SearchToken.PHRASE:
            self._consume()
            return PhraseNode(tok.value)

        if tok.kind == SearchToken.LPAREN:
            self._consume(SearchToken.LPAREN)
            node = self._or_expr()
            self._consume(SearchToken.RPAREN)
            return node

        raise ValueError(
            f"Search parse error: unexpected token {tok!r} at position {self.pos}"
        )


def parse_search_query(query):
    """
    High-level helper: parse a search query string into an AST.

    Examples:
        parse_search_query('"machine learning" AND "neural networks"')
        parse_search_query('("machine learning" AND "neural networks") OR "computer vision"')
    """
    tokens = tokenize_search(query)
    parser = SearchParser(tokens)
    return parser.parse()


# Evaluator ----------------------------------------------------------------

def evaluate_search(node, text):
    """
    Evaluate a parsed search AST against a block of text (already lowercased).
    Returns True if the text matches the query.
    """
    if isinstance(node, PhraseNode):
        return node.phrase in text
    if isinstance(node, AndNode):
        return evaluate_search(node.left, text) and evaluate_search(node.right, text)
    if isinstance(node, OrNode):
        return evaluate_search(node.left, text) or evaluate_search(node.right, text)
    raise ValueError(f"Unknown AST node type: {type(node)}")


def get_entity_name(person):
    """
    Build a display name from a person/entity record.
    Returns the organisation name if present, otherwise 'First Last'.
    """
    if not person:
        return None
    if person.get("organization"):
        return person["organization"]
    parts = [person.get("first_name"), person.get("last_name")]
    name = " ".join(p for p in parts if p)
    return name if name else None


def collect_entity_names(patent_data):
    """
    Return a list of entity name strings from inventors, applicants and
    assignees found in *patent_data*.
    """
    names = []
    for field in ("inventors", "applicants", "assignees"):
        for person in patent_data.get(field, []) or []:
            name = get_entity_name(person)
            if name:
                names.append(name)
    return names


def get_patent_text(patent_data):
    """
    Collect all searchable text from a patent record into a single
    lower-cased string.  Covers title, abstract, claims, and description
    sample (but NOT entity names — use :func:`get_patent_entity_text` for that).
    """
    text_fields = []

    if "title" in patent_data and patent_data["title"]:
        text_fields.append(patent_data["title"])

    if "abstract" in patent_data and patent_data["abstract"]:
        text_fields.append(patent_data["abstract"])

    if "claims" in patent_data and patent_data["claims"]:
        for claim in patent_data["claims"]:
            if claim and "claim_text" in claim and claim["claim_text"]:
                claim_text_obj = claim["claim_text"]
                if isinstance(claim_text_obj, dict) and "text" in claim_text_obj:
                    text_fields.append(claim_text_obj["text"])

    if "description" in patent_data and patent_data["description"]:
        desc = patent_data["description"]
        if "paragraphs_sample" in desc:
            for para in desc["paragraphs_sample"]:
                if para and "text" in para and para["text"]:
                    text_fields.append(para["text"])

    return " ".join(text_fields).lower()


def get_patent_entity_text(patent_data):
    """
    Collect all entity names (inventors, applicants, assignees/owners) from
    a patent record into a single lower-cased string.
    """
    return " ".join(collect_entity_names(patent_data)).lower()


def matches_search(patent_data, search_ast):
    """Return True if *patent_data* satisfies the boolean *search_ast* on content fields."""
    combined = get_patent_text(patent_data)
    return evaluate_search(search_ast, combined)


def matches_entity_search(patent_data, search_ast):
    """Return True if *patent_data* satisfies the boolean *search_ast* on entity fields only."""
    combined = get_patent_entity_text(patent_data)
    return evaluate_search(search_ast, combined)


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


def collect_distinct_entities(patents):
    """
    Scan all *patents* and return a dict with sorted lists of unique entity
    names found under ``inventors``, ``applicants`` and ``assignees``.

    Returns::

        {
            "inventors": ["Alice Smith", "Bob Jones", ...],
            "applicants": ["Acme Corp", ...],
            "assignees": ["Acme Corp", ...],
            "all": ["Acme Corp", "Alice Smith", "Bob Jones", ...]  # union
        }
    """
    sets = {
        "inventors": set(),
        "applicants": set(),
        "assignees": set(),
    }

    for patent in patents:
        for field, s in sets.items():
            for person in patent.get(field, []) or []:
                name = get_entity_name(person)
                if name:
                    s.add(name)

    all_entities = sets["inventors"] | sets["applicants"] | sets["assignees"]

    return {
        "inventors": sorted(sets["inventors"]),
        "applicants": sorted(sets["applicants"]),
        "assignees": sorted(sets["assignees"]),
        "all": sorted(all_entities),
    }


def search_hash(query):
    """Return a short, filesystem-safe hash of the search query string."""
    return hashlib.sha256(query.encode("utf-8")).hexdigest()[:12]


def read_xml_content(file_path, keywords=None):
    """
    Read XML content from a file (plain XML or from ZIP archive).
    Returns extracted patents filtered by keywords if provided.
    """
    # Check if file is a ZIP archive
    if file_path.lower().endswith('.zip'):
        print(f"Opening ZIP archive: {file_path}")
        try:
            with zipfile.ZipFile(file_path, 'r') as zip_ref:
                # Find XML files in the archive
                xml_files = [f for f in zip_ref.namelist(
                ) if f.lower().endswith('.xml')]
                if not xml_files:
                    print(
                        f"Error: No XML files found in ZIP archive {file_path}")
                    return []

                print(f"Found {len(xml_files)} XML file(s) in ZIP archive")
                all_patents = []

                for xml_file in xml_files:
                    print(f"  Extracting from: {xml_file}")
                    try:
                        with zip_ref.open(xml_file, 'r') as xml_content:
                            content = xml_content.read().decode('utf-8', errors='replace')
                            patents = parse_xml_content(
                                content, xml_file, keywords)
                            all_patents.extend(patents)
                    except Exception as e:
                        print(f"Warning: Could not process {xml_file}: {e}")
                        continue

                return all_patents

        except zipfile.BadZipFile:
            print(f"Error: {file_path} is not a valid ZIP file")
            return []

    # Regular XML file
    print(f"Opening XML file: {file_path}")
    try:
        with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()
        return parse_xml_content(content, file_path, keywords)
    except FileNotFoundError:
        print(f"Error: File '{file_path}' not found")
        return []


def parse_xml_content(content, source_name, keywords=None):
    """
    Parse XML content and extract patents, optionally filtering by keywords.
    """
    # Split by XML declarations to handle multiple documents
    fragments = content.split('<?xml')
    fragments = [f for f in fragments if f.strip()]

    if len(fragments) > 1:
        print(f"Found {len(fragments)} XML documents in {source_name}")
        fragments = ['<?xml' + f for f in fragments]
    else:
        fragments = [content]

    all_patents = []

    for i, fragment in enumerate(fragments, 1):
        try:
            # Add XML declaration if missing
            if not fragment.strip().startswith('<?xml'):
                fragment = '<?xml version="1.0"?>\n' + fragment

            root = ET.fromstring(fragment)

            # Check if root is a patent application or grant
            if root.tag in ['us-patent-application', 'us-patent-grant']:
                print(f"Extracting patent {i}/{len(fragments)}...")
                patent_data = extract_patent(root)

                # Filter by keywords if provided
                if keywords and not contains_keywords(patent_data, keywords):
                    continue

                all_patents.append(patent_data)
            else:
                print(
                    f"Fragment {i}: Not a patent document (root: {root.tag})")

        except ET.ParseError as e:
            print(f"Warning: Could not parse fragment {i}: {e}")
            continue
        except Exception as e:
            print(f"Warning: Error extracting fragment {i}: {e}")
            continue

    return all_patents


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


def read_all_zips_sequential(data_dir, keywords=None):
    """
    Discover all .zip files in *data_dir* and extract patents from each
    sequentially (one at a time) to keep memory usage low.

    Returns a tuple of (all_patents, source_files) where *all_patents* is
    the combined list of patent dicts and *source_files* is the list of
    ZIP paths that were processed.
    """
    zip_files = sorted(glob.glob(os.path.join(data_dir, '*.zip')))
    if not zip_files:
        print(f"⚠️  No ZIP files found in {data_dir}")
        return [], []

    print(f"\nFound {len(zip_files)} ZIP file(s) in {data_dir}:")
    for zf in zip_files:
        print(f"  • {os.path.basename(zf)}")

    all_patents = []

    print(f"\nProcessing {len(zip_files)} ZIP files sequentially …")
    for idx, zip_path in enumerate(zip_files, 1):
        zip_name = os.path.basename(zip_path)
        print(f"\n[{idx}/{len(zip_files)}] Processing {zip_name} …")
        try:
            patents = read_xml_content(zip_path, keywords)
            print(f"  ✓ {zip_name}: {len(patents)} patents")
            all_patents.extend(patents)
        except Exception as e:
            print(f"  ✗ {zip_name}: Error – {e}")

    print(f"\nTotal patents extracted from all ZIPs: {len(all_patents)}")
    return all_patents, zip_files


def run_search(patents, search_query, source_file, entity_query=None, cpc_query=None):
    """
    Apply boolean search queries to a list of patent records.

    *search_query* matches against patent content (title, abstract, claims,
    description).  *entity_query* matches against entity names only
    (inventors, applicants, assignees/owners).  *cpc_query* is a
    comma-separated list of CPC code patterns with optional ``*`` wildcards.
    When multiple queries are supplied a patent must satisfy **all** of them.

    Save matching patents to ``search_<hash>.json`` and print a summary.
    """
    content_ast = None
    entity_ast = None
    cpc_patterns = None

    if search_query:
        print(f"\nParsing content search query: {search_query}")
        try:
            content_ast = parse_search_query(search_query)
        except ValueError as e:
            print(f"Error: {e}")
            sys.exit(1)
        print(f"Parsed content AST: {content_ast}")

    if entity_query:
        print(f"\nParsing entity search query: {entity_query}")
        try:
            entity_ast = parse_search_query(entity_query)
        except ValueError as e:
            print(f"Error: {e}")
            sys.exit(1)
        print(f"Parsed entity AST: {entity_ast}")

    if cpc_query:
        raw_patterns = [p.strip() for p in cpc_query.split(",") if p.strip()]
        cpc_patterns = [cpc_pattern_to_regex(p) for p in raw_patterns]
        print(f"\nCPC patterns: {raw_patterns}")

    # Filter patents — must match ALL supplied queries
    total_before = len(patents)

    def patent_matches(p):
        if content_ast and not matches_search(p, content_ast):
            return False
        if entity_ast and not matches_entity_search(p, entity_ast):
            return False
        if cpc_patterns and not matches_cpc_search(p, cpc_patterns):
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
    qhash = search_hash(combined_query)
    output_file = f"search_{qhash}.json"

    # Collect distinct entities from matched patents
    entities = collect_distinct_entities(matched)

    # Create a separate JSON file for entities with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    entities_file = f"entities_{timestamp}.json"

    with open(entities_file, 'w', encoding='utf-8') as f:
        json.dump(entities, f, indent=2, ensure_ascii=False)

    output_data = {
        "search_date": datetime.now().isoformat(),
        "search_query": search_query,
        "entity_query": entity_query,
        "cpc_query": cpc_query,
        "search_hash": qhash,
        "source_file": source_file,
        "total_searched": total_before,
        "total_matched": len(matched),
        "entities_file": entities_file,
        "patents": matched
    }

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)

    # Summary
    print(f"\n✓ Search matched {len(matched)} / {total_before} patents")
    print(f"✓ Results saved to: {output_file}")

    print("\n" + "=" * 70)
    print("SEARCH RESULTS SUMMARY")
    print("=" * 70)
    if search_query:
        print(f"Content query : {search_query}")
    if entity_query:
        print(f"Entity query  : {entity_query}")
    if cpc_query:
        print(f"CPC query     : {cpc_query}")
    print(f"Hash  : {qhash}")
    print(f"Source: {source_file}")
    print(f"Matched: {len(matched)} / {total_before}")

    print(f"Distinct entities: {len(entities['all'])} total "
          f"({len(entities['inventors'])} inventors, "
          f"{len(entities['applicants'])} applicants, "
          f"{len(entities['assignees'])} assignees)")

    print("\nFirst 5 matching patent titles:")
    for i, patent in enumerate(matched[:5], 1):
        title = patent.get("title", "No title")
        print(f"  {i}. {title[:80]}{'...' if len(title) > 80 else ''}")
    if len(matched) > 5:
        print(f"\n  ... and {len(matched) - 5} more patents")


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
            '                   A patent matches if ANY of its CPC codes match ANY pattern.')
        print('                   All search flags can be combined (all must match).')
        print('                Examples:')
        print('                  --search "machine learning"')
        print('                  --search \'"machine learning" AND "neural networks"\'')
        print('                  --search-entity "Microsoft"')
        print('                  --search-entity \'"Samsung" OR "Apple"\'')
        print('                  --search-cpc "G06F*"')
        print('                  --search-cpc "G06N*,G06F21*"')
        print('                  --search "neural" --search-entity "Google" --search-cpc "G06N*"')
        print('\n  Directory mode (sequential):')
        print('                  python main.py data/ --search "battery"')
        print('                  python main.py data/ --search-cpc "H01M*"')
        sys.exit(1)

    # Parse command line arguments
    input_file = sys.argv[1]
    output_file = "patents.json"
    keywords = None
    search_query = None
    entity_query = None
    cpc_query = None

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
        if not arg.startswith('--'):
            output_file = arg
        i += 1

    # ---- Search-only mode on an existing JSON file ----
    if input_file.lower().endswith('.json'):
        if not search_query and not entity_query and not cpc_query:
            print(
                "Error: When the input is a JSON file, --search, --search-entity, or --search-cpc is required.")
            sys.exit(1)
        print(f"Loading patents from: {input_file}")
        try:
            patents, _meta = load_patents_from_json(input_file)
        except (FileNotFoundError, ValueError, json.JSONDecodeError) as e:
            print(f"Error loading {input_file}: {e}")
            sys.exit(1)
        print(f"Loaded {len(patents)} patents")
        run_search(patents, search_query, source_file=input_file,
                   entity_query=entity_query, cpc_query=cpc_query)
        return

    # ---- Directory mode: sequential processing of all ZIPs ----
    if os.path.isdir(input_file):
        if keywords:
            print(f"Filtering patents containing keywords: {keywords}")
        all_patents, source_files = read_all_zips_sequential(
            input_file, keywords)
        source_label = ", ".join(os.path.basename(f) for f in source_files)

        if not all_patents:
            print(f"\n⚠️  No patents extracted from ZIP files in {input_file}")
            if keywords:
                print(f"   No patents matched the keywords: {keywords}")
            sys.exit(0)

        # If any search flag was supplied, apply it now
        if search_query or entity_query or cpc_query:
            run_search(all_patents, search_query,
                       source_file=source_label, entity_query=entity_query,
                       cpc_query=cpc_query)
            return

        # No search flags — save full extraction
        entities = collect_distinct_entities(all_patents)

        # Create a separate JSON file for entities with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        entities_file = f"entities_{timestamp}.json"

        with open(entities_file, 'w', encoding='utf-8') as f:
            json.dump(entities, f, indent=2, ensure_ascii=False)

        print(f"\nSaving {len(all_patents)} patents to {output_file}...")

        output_data = {
            "extraction_date": datetime.now().isoformat(),
            "source_files": [os.path.basename(f) for f in source_files],
            "keywords_filter": keywords if keywords else None,
            "total_patents": len(all_patents),
            "entities_file": entities_file,
            "patents": all_patents
        }

        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)

        print(f"\n✓ Successfully extracted {len(all_patents)} patents!")
        print(f"✓ Saved to: {output_file}")

        print("\n" + "=" * 70)
        print("EXTRACTION SUMMARY")
        print("=" * 70)
        print(f"Source: {source_label}")
        if keywords:
            print(f"Keywords filter: {keywords}")
        print(f"Total patents extracted: {len(all_patents)}")
        print(f"Distinct entities: {len(entities['all'])} total "
              f"({len(entities['inventors'])} inventors, "
              f"{len(entities['applicants'])} applicants, "
              f"{len(entities['assignees'])} assignees)")

        if all_patents:
            print("\nFirst 5 patent titles:")
            for idx, patent in enumerate(all_patents[:5], 1):
                title = patent.get("title", "No title")
                print(
                    f"  {idx}. {title[:80]}{'...' if len(title) > 80 else ''}")
            if len(all_patents) > 5:
                print(f"\n  ... and {len(all_patents) - 5} more patents")

        return

    # ---- Extraction mode (single XML / ZIP file) ----
    if keywords:
        print(f"Filtering patents containing keywords: {keywords}")
    print(f"Processing file: {input_file}")

    all_patents = read_xml_content(input_file, keywords)

    if not all_patents:
        print(f"\n⚠️ No patents extracted from {input_file}")
        if keywords:
            print(f"   No patents matched the keywords: {keywords}")
        sys.exit(0)

    # If any search flag was supplied alongside extraction, apply it now
    if search_query or entity_query or cpc_query:
        run_search(all_patents, search_query,
                   source_file=input_file, entity_query=entity_query,
                   cpc_query=cpc_query)
        return

    # Collect distinct entities across all patents
    entities = collect_distinct_entities(all_patents)

    # Create a separate JSON file for entities with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    entities_file = f"entities_{timestamp}.json"

    with open(entities_file, 'w', encoding='utf-8') as f:
        json.dump(entities, f, indent=2, ensure_ascii=False)

    # Save full extraction to JSON
    print(f"\nSaving {len(all_patents)} patents to {output_file}...")

    output_data = {
        "extraction_date": datetime.now().isoformat(),
        "source_file": input_file,
        "keywords_filter": keywords if keywords else None,
        "total_patents": len(all_patents),
        "entities_file": entities_file,
        "patents": all_patents
    }

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)

    print(f"\n✓ Successfully extracted {len(all_patents)} patents!")
    print(f"✓ Saved to: {output_file}")

    # Print summary
    print("\n" + "=" * 70)
    print("EXTRACTION SUMMARY")
    print("=" * 70)
    print(f"Source: {input_file}")
    if keywords:
        print(f"Keywords filter: {keywords}")
    print(f"Total patents extracted: {len(all_patents)}")
    print(f"Distinct entities: {len(entities['all'])} total "
          f"({len(entities['inventors'])} inventors, "
          f"{len(entities['applicants'])} applicants, "
          f"{len(entities['assignees'])} assignees)")

    if all_patents:
        # Show matched keywords in titles
        print("\nFirst 5 patent titles:")
        for i, patent in enumerate(all_patents[:5], 1):
            title = patent.get("title", "No title")
            # Highlight keywords in title
            if keywords:
                for keyword in keywords:
                    if keyword.lower() in title.lower():
                        title = title.replace(keyword, f"**{keyword}**")
                        title = title.replace(
                            keyword.lower(), f"**{keyword.lower()}**")
                        title = title.replace(
                            keyword.upper(), f"**{keyword.upper()}**")

            print(f"  {i}. {title[:80]}{'...' if len(title) > 80 else ''}")

        if len(all_patents) > 5:
            print(f"\n  ... and {len(all_patents) - 5} more patents")

        # Show keyword statistics
        if keywords:
            print("\nKeyword matches (case-insensitive):")
            keyword_counts = {keyword: 0 for keyword in keywords}
            for patent in all_patents:
                text_fields = []
                if "title" in patent and patent["title"]:
                    text_fields.append(patent["title"].lower())
                if "abstract" in patent and patent["abstract"]:
                    text_fields.append(patent["abstract"].lower())

                combined_text = " ".join(text_fields)
                for keyword in keywords:
                    if keyword.lower() in combined_text:
                        keyword_counts[keyword] += 1

            for keyword, count in keyword_counts.items():
                if count > 0:
                    print(f"  '{keyword}': {count} patents")


if __name__ == "__main__":
    main()
