"""Glob-like path-metadata patterns (``--path-metadata``), translated into the regular
expressions that ``--path-metadata-regex`` takes"""

import re

__all__ = ["path_metadata_pattern_to_regex"]

# Tokens of a path-metadata pattern, tried in order: escaped braces, a '{name}'
# placeholder, '**', '*', '?' and a '[...]' character class
_PATTERN_TOKEN_RE = re.compile(
    r"(?P<lbrace>\{\{)|(?P<rbrace>\}\})|\{(?P<field>[^{}]*)\}|(?P<globstar>\*\*/?)"
    r"|(?P<star>\*)|(?P<qmark>\?)|(?P<charclass>\[!?\]?[^\]]*\])"
)


def path_metadata_pattern_to_regex(pattern: str) -> str:
    """Translates a glob-like path-metadata pattern into the equivalent regular
    expression, as taken by ``--path-metadata-regex``/``PathMetadataRegex``.

    * ``{name}`` matches one path segment (or part of one), i.e. ``[^/]+``, and stores
      it in the metadata field ``name``. ``name`` must be a valid Python identifier. A
      field repeated in the same pattern must have the same value each time
    * ``*`` matches any characters within a segment, ``**`` any characters across
      segments (``**/`` zero or more whole segments), ``?`` a single character within
      a segment, and ``[...]``/``[!...]`` a (negated) character class, as in a shell
      glob
    * ``{{`` and ``}}`` match literal braces, every other character matches itself
    * a pattern starting with ``/`` must match the whole path; otherwise it only needs
      to match its trailing segments, e.g. ``{cohort}/*.dcm`` matches
      ``/data/incoming/cohort-A/1.dcm``

    Parameters
    ----------
    pattern : str
        the glob-like pattern, e.g. ``'{subject}/{session}/*'``

    Returns
    -------
    str
        the regular expression, with a named group for each field in ``pattern``

    Raises
    ------
    ValueError
        if a placeholder's name isn't a valid identifier, or a brace is unmatched
    """
    parts: list[str] = []
    fields: set[str] = set()
    pos = 0
    for match in _PATTERN_TOKEN_RE.finditer(pattern):
        literal = pattern[pos : match.start()]
        if "{" in literal or "}" in literal:
            raise ValueError(
                f"Unmatched brace in path-metadata pattern '{pattern}' (use '{{{{' or "
                "'}}' for a literal brace)"
            )
        parts.append(re.escape(literal))
        pos = match.end()
        kind = match.lastgroup
        if kind == "lbrace":
            parts.append(re.escape("{"))
        elif kind == "rbrace":
            parts.append(re.escape("}"))
        elif kind == "field":
            name = match.group("field")
            if not name.isidentifier():
                raise ValueError(
                    f"'{{{name}}}' in path-metadata pattern '{pattern}' isn't a valid "
                    "field name: it must be a valid Python identifier (letters, digits "
                    "and underscores, not starting with a digit)"
                )
            if name in fields:
                parts.append(f"(?P={name})")
            else:
                fields.add(name)
                parts.append(f"(?P<{name}>[^/]+)")
        elif kind == "globstar":
            # '**/' matches zero or more whole segments, a bare '**' anything at all
            parts.append("(?:.*/)?" if match.group().endswith("/") else ".*")
        elif kind == "star":
            parts.append("[^/]*")
        elif kind == "qmark":
            parts.append("[^/]")
        else:
            charclass = match.group("charclass")[1:-1]
            negate = charclass.startswith("!")
            if negate:
                charclass = charclass[1:]
            charclass = (
                charclass.replace("\\", "\\\\").replace("[", "\\[").replace("]", "\\]")
            )
            if charclass.startswith("^"):
                charclass = "\\" + charclass
            parts.append(f"[^/{charclass}]" if negate else f"[{charclass}]")
    literal = pattern[pos:]
    if "{" in literal or "}" in literal:
        raise ValueError(
            f"Unmatched brace in path-metadata pattern '{pattern}' (use '{{{{' or '}}}}' "
            "for a literal brace)"
        )
    parts.append(re.escape(literal))
    body = "".join(parts)
    if not pattern.startswith("/"):
        body = "(?:.*/)?" + body
    return body + "$"
