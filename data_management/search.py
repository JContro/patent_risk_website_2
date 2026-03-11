"""
Boolean search query parser and evaluator for patent data.
Supports: quoted phrases, AND, OR operators, and parentheses.

Grammar (case-insensitive operators):
    expression := or_expr
    or_expr    := and_expr ( "OR" and_expr )*
    and_expr   := atom ( "AND" atom )*
    atom       := "quoted phrase" | "(" expression ")" | bare_word
"""

# ---------------------------------------------------------------------------
# Tokenizer
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


# ---------------------------------------------------------------------------
# AST node types
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Recursive-descent parser
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Evaluator
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Patent text extraction helpers
# ---------------------------------------------------------------------------

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
    import hashlib
    return hashlib.sha256(query.encode("utf-8")).hexdigest()[:12]
