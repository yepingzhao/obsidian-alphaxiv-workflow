"""
Boolean query parser for AlphaXiv search.
Parses user queries with AND, OR, NOT, -exclude, and parentheses.
Converts to a structured expression that can be evaluated against paper text.
"""
import re
from dataclasses import dataclass, field


# ──────────────────────────────────────────────────────────────────
# Expression tree
# ──────────────────────────────────────────────────────────────────

@dataclass
class Expr:
    """Base expression node."""
    pass


@dataclass
class Term(Expr):
    """A single search term (word or phrase)."""
    text: str
    negated: bool = False  # True for NOT / -exclude


@dataclass
class And(Expr):
    """All children must match."""
    children: list = field(default_factory=list)


@dataclass
class Or(Expr):
    """Any child must match."""
    children: list = field(default_factory=list)


# ──────────────────────────────────────────────────────────────────
# Tokenizer
# ──────────────────────────────────────────────────────────────────

TOKEN_RE = re.compile(
    r'\s*('
    r'AND|OR|NOT|'          # Operators (uppercase only)
    r'\(|\)|'               # Parens
    r'-?\w+(?:-\w+)*|'      # Words (with optional -prefix) and hyphenated words
    r'"[^"]+"|'             # Quoted phrases
    r"'[^']+'"              # Single-quoted phrases
    r')\s*',
    re.IGNORECASE
)


def tokenize(query: str) -> list:
    """Tokenize a query string into (type, value) pairs.

    Types: 'AND', 'OR', 'NOT', 'LPAREN', 'RPAREN', 'WORD'
    """
    tokens = []
    for match in TOKEN_RE.finditer(query):
        raw = match.group(1)
        upper = raw.upper()

        if upper == 'AND':
            tokens.append(('AND', 'AND'))
        elif upper == 'OR':
            tokens.append(('OR', 'OR'))
        elif upper == 'NOT':
            tokens.append(('NOT', 'NOT'))
        elif raw == '(':
            tokens.append(('LPAREN', '('))
        elif raw == ')':
            tokens.append(('RPAREN', ')'))
        elif raw.startswith('-') and len(raw) > 1:
            # -word → NOT word
            tokens.append(('NOT', 'NOT'))
            tokens.append(('WORD', raw[1:]))
        else:
            word = raw.strip('"\'')
            if word:
                tokens.append(('WORD', word))

    return tokens


# ──────────────────────────────────────────────────────────────────
# Parser (recursive descent)
# ──────────────────────────────────────────────────────────────────

class ParseError(Exception):
    pass


class Parser:
    """Recursive descent parser for boolean query expressions.

    Grammar:
        expr     → or_expr
        or_expr  → and_expr ('OR' and_expr)*
        and_expr → not_expr ('AND'? not_expr)*
        not_expr → 'NOT'? atom
        atom     → WORD | '(' expr ')'
    """

    def __init__(self, tokens: list):
        self.tokens = tokens
        self.pos = 0

    def peek(self):
        if self.pos < len(self.tokens):
            return self.tokens[self.pos]
        return ('EOF', '')

    def consume(self, expected_type: str = None):
        if self.pos >= len(self.tokens):
            raise ParseError(f'Unexpected end of input, expected {expected_type}')
        token = self.tokens[self.pos]
        if expected_type and token[0] != expected_type:
            raise ParseError(
                f'Expected {expected_type} at position {self.pos}, got {token}'
            )
        self.pos += 1
        return token

    def parse(self) -> Expr:
        """Parse the token stream into an expression tree."""
        if not self.tokens:
            return And(children=[])
        result = self._parse_or()
        if self.pos < len(self.tokens):
            remaining = self.tokens[self.pos:]
            raise ParseError(f'Unexpected tokens after expression: {remaining}')
        return result

    def _parse_or(self) -> Expr:
        left = self._parse_and()
        while self.peek()[0] == 'OR':
            self.consume('OR')
            right = self._parse_and()
            if isinstance(left, Or):
                left.children.append(right)
            else:
                left = Or(children=[left, right])
        return left

    def _parse_and(self) -> Expr:
        left = self._parse_not()
        # Unified loop: handles both implicit AND (adjacent terms) and explicit AND
        while self.peek()[0] in ('WORD', 'LPAREN', 'NOT', 'AND'):
            if self.peek()[0] == 'AND':
                self.consume('AND')
            right = self._parse_not()
            if isinstance(left, And):
                left.children.append(right)
            else:
                left = And(children=[left, right])
        return left

    def _parse_not(self) -> Expr:
        if self.peek()[0] == 'NOT':
            self.consume('NOT')
            atom = self._parse_atom()
            if isinstance(atom, Term):
                atom.negated = True
            return atom
        return self._parse_atom()

    def _parse_atom(self) -> Expr:
        token = self.peek()
        if token[0] == 'WORD':
            self.consume('WORD')
            return Term(text=token[1].lower())
        elif token[0] == 'LPAREN':
            self.consume('LPAREN')
            expr = self._parse_or()
            if self.peek()[0] != 'RPAREN':
                raise ParseError(f'Expected ) at position {self.pos}, got {self.peek()}')
            self.consume('RPAREN')
            return expr
        else:
            raise ParseError(f'Unexpected token at position {self.pos}: {token}')


# ──────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────

def parse_query(query: str) -> tuple:
    """Parse a boolean query string into (expr, search_terms, exclude_terms).

    Args:
        query: Raw user query with optional AND/OR/NOT/- operators.

    Returns:
        expr: Expression tree for post-filter evaluation
        search_terms: List of positive terms to send to AlphaXiv API
        exclude_terms: List of negated terms (NOT/-exclude) for post-filtering
    """
    tokens = tokenize(query)

    # Fast path: no operators → simple AND of all words
    words = [t[1] for t in tokens if t[0] == 'WORD']
    operators_present = any(t[0] in ('AND', 'OR', 'NOT') for t in tokens)

    if not operators_present:
        expr = And(children=[Term(text=w) for w in words])
        return expr, words, []

    parser = Parser(tokens)
    expr = parser.parse()

    search_terms = []
    exclude_terms = []

    def collect_terms(node):
        if isinstance(node, Term):
            if node.negated:
                exclude_terms.append(node.text)
            else:
                search_terms.append(node.text)
        elif isinstance(node, (And, Or)):
            for child in node.children:
                collect_terms(child)

    collect_terms(expr)

    return expr, search_terms, exclude_terms


def extract_or_groups(expr: Expr) -> list:
    """Extract OR groups for multi-search strategy.

    For OR expressions, make separate searches per OR branch.
    Returns list of (search_terms, exclude_terms) pairs.

    Example:
        '(diffusion OR transformer) AND image NOT detection'
        → [  (['diffusion', 'image'], ['detection']),
             (['transformer', 'image'], ['detection'])  ]
    """
    if not isinstance(expr, Or):
        positive = []
        negative = []

        def collect(node):
            if isinstance(node, Term):
                if node.negated:
                    negative.append(node.text)
                else:
                    positive.append(node.text)
            elif isinstance(node, And):
                for child in node.children:
                    collect(child)

        collect(expr)
        return [(positive, negative)]

    groups = []
    for child in expr.children:
        positive = []
        negative = []

        def collect_leaf(node):
            if isinstance(node, Term):
                if node.negated:
                    negative.append(node.text)
                else:
                    positive.append(node.text)
            elif isinstance(node, And):
                for c in node.children:
                    collect_leaf(c)
            elif isinstance(node, Or):
                for c in node.children:
                    collect_leaf(c)

        collect_leaf(child)
        groups.append((positive, negative))

    return groups


def evaluate_term(term: str, text: str) -> bool:
    """Check if a term matches in text (case-insensitive substring)."""
    return term.lower() in text.lower()


def evaluate_expr(expr: Expr, text: str) -> bool:
    """Evaluate a boolean expression against a text string (title + snippet)."""
    if isinstance(expr, Term):
        found = evaluate_term(expr.text, text)
        return not found if expr.negated else found
    elif isinstance(expr, And):
        return all(evaluate_expr(child, text) for child in expr.children)
    elif isinstance(expr, Or):
        return any(evaluate_expr(child, text) for child in expr.children)
    return False


def build_search_query(search_terms: list) -> str:
    """Build an API-friendly search query from extracted terms."""
    return ' '.join(search_terms) if search_terms else ''


def filter_results(expr: Expr, results: list, limit: int = 10) -> list:
    """Post-filter search results against a boolean expression.

    Args:
        expr: Expression tree from parse_query()
        results: List of search result objects (Pydantic models with title + snippet)
        limit: Maximum results to return
    """
    matched = []
    for r in results:
        title = r.title if hasattr(r, 'title') else r.get('title', '')
        snippet = r.snippet if hasattr(r, 'snippet') else r.get('snippet', '')
        text = f'{title} {snippet}'
        if evaluate_expr(expr, text):
            matched.append(r)
        if len(matched) >= limit:
            break
    return matched
