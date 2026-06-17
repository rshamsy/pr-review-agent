"""Regex-based pre-scanner for role/auth patterns in PR diffs."""

from __future__ import annotations

import re

from pydantic import BaseModel, Field

# Context lines to extract around each match
_CONTEXT_LINES = 5


class RoleDetectionResult(BaseModel):
    has_role_patterns: bool = False
    detected_roles: list[str] = Field(default_factory=list)
    role_snippets: list[str] = Field(default_factory=list)
    auth_patterns: list[str] = Field(default_factory=list)


# Patterns grouped by category
_ROLE_ACCESS_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    # Direct role checks
    ("role_check", re.compile(r"(?:user|session|req|request|ctx)\.role\b", re.IGNORECASE)),
    ("role_comparison", re.compile(r"\brole\s*(?:===?|!==?|==)\s*", re.IGNORECASE)),
    # Boolean role helpers
    ("role_helper", re.compile(r"\b(?:isAdmin|is_admin|isBuyer|is_buyer|isSupplier|is_supplier|isManager|is_manager|isUser|is_user)\b")),
    # Permission / authorization
    ("permission", re.compile(r"\b(?:permission|authorize|authorization|guard)\b", re.IGNORECASE)),
    ("access_check", re.compile(r"\b(?:canAccess|can_access|hasPermission|has_permission|checkRole|check_role|hasRole|has_role)\b")),
    # Framework auth decorators / HOCs
    ("framework_auth", re.compile(r"(?:\b(?:useSession|getServerSession|withAuth)\b|@(?:login_required|permission_required|roles_required|requires_auth|auth_required)\b)")),
    # Middleware near auth terms
    ("auth_middleware", re.compile(r"\bmiddleware\b.*(?:auth|role|permission)|(?:auth|role|permission).*\bmiddleware\b", re.IGNORECASE)),
]

# Role string literals to detect
_ROLE_LITERAL_PATTERN = re.compile(
    r"""(?:["'])(?P<role>admin|administrator|supplier|buyer|manager|user|editor|viewer|moderator|owner|member|superadmin|super_admin)(?:["'])""",
    re.IGNORECASE,
)

# Role names from identifiers like `Role.ADMIN`, `ROLE_SUPPLIER`, `UserRole.Buyer`
_ROLE_IDENTIFIER_PATTERN = re.compile(
    r"\b(?:Role|ROLE|UserRole|user_role)[._](?P<role>[A-Za-z_]+)\b"
)


def detect_role_patterns(diff_text: str) -> RoleDetectionResult:
    """Scan diff text for role/auth patterns and extract relevant snippets."""
    lines = diff_text.splitlines()
    match_positions: list[tuple[int, str]] = []  # (line_index, pattern_name)
    auth_patterns_found: set[str] = set()
    detected_roles: set[str] = set()

    for i, line in enumerate(lines):
        # Skip diff metadata lines
        if line.startswith("diff --git") or line.startswith("index ") or line.startswith("---") or line.startswith("+++"):
            continue

        for pattern_name, pattern in _ROLE_ACCESS_PATTERNS:
            if pattern.search(line):
                match_positions.append((i, pattern_name))
                auth_patterns_found.add(pattern_name)

        # Extract role names from string literals
        for m in _ROLE_LITERAL_PATTERN.finditer(line):
            detected_roles.add(m.group("role").lower())

        # Extract role names from identifiers
        for m in _ROLE_IDENTIFIER_PATTERN.finditer(line):
            role_name = m.group("role").lower().strip("_")
            if role_name not in ("type", "enum", "class", "model", "schema"):
                detected_roles.add(role_name)

    if not match_positions:
        return RoleDetectionResult(has_role_patterns=False)

    # Extract context snippets around matches, deduplicating overlapping regions
    snippets = _extract_snippets(lines, [pos for pos, _ in match_positions])

    return RoleDetectionResult(
        has_role_patterns=True,
        detected_roles=sorted(detected_roles),
        role_snippets=snippets,
        auth_patterns=sorted(auth_patterns_found),
    )


def _extract_snippets(lines: list[str], match_indices: list[int]) -> list[str]:
    """Extract context snippets around match positions, merging overlapping ranges."""
    if not match_indices:
        return []

    total = len(lines)
    # Build merged ranges
    ranges: list[tuple[int, int]] = []
    for idx in sorted(set(match_indices)):
        start = max(0, idx - _CONTEXT_LINES)
        end = min(total, idx + _CONTEXT_LINES + 1)
        if ranges and start <= ranges[-1][1]:
            # Merge with previous range
            ranges[-1] = (ranges[-1][0], max(ranges[-1][1], end))
        else:
            ranges.append((start, end))

    # Cap total snippets to avoid excessive output
    snippets: list[str] = []
    for start, end in ranges[:20]:
        snippet = "\n".join(lines[start:end])
        snippets.append(snippet)

    return snippets
