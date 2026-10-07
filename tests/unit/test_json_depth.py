"""The JSON nesting guard reads a multi-megabyte result.json in milliseconds
and counts exactly what the character loop it replaced counted."""

from __future__ import annotations

import json
import time

import pytest

from reverbscope.io.jsonutil import MAX_JSON_DEPTH, json_nesting_depth


def _by_the_character(text: str) -> int:
    """The previous implementation, kept as the reference."""
    depth = deepest = 0
    in_string = escape = False
    for char in text:
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
            continue
        if char in "{[":
            depth += 1
            deepest = max(deepest, depth)
        elif char in "}]":
            depth = max(0, depth - 1)
    return deepest


@pytest.mark.parametrize(
    "text",
    [
        '{"a": [1, 2, {"b": "[[[["}]}',
        '{"a": "\\"[", "b": [[[]]]}',
        "[",
        '"unterminated [[[[',
        '{"x": "a\\\\", "y": [[1]]}',
        '{"s": "line\nbreak [["}',
        "",
        "[[[]]]]]]]]",
        '{"k": "\\u005b"}',
        '{"deep": ' * (MAX_JSON_DEPTH + 3) + "1" + "}" * (MAX_JSON_DEPTH + 3),
        "[1, 2, 3] [[",
        '{"a": "\\\\"}]]',
        "abc",
        '{"a":"\\"}',
    ],
)
def test_the_regex_scan_counts_like_the_character_loop(text: str) -> None:
    assert json_nesting_depth(text) == _by_the_character(text)


def test_a_result_sized_document_is_scanned_quickly() -> None:
    """131072-point curves made the loop slower than json.loads itself."""
    big = json.dumps(
        {
            "frequencies_hz": [float(i) for i in range(131072)],
            "magnitude_db": [0.1234] * 131072,
            "notes": ['a "quoted" [note]'] * 1000,
        }
    )
    start = time.perf_counter()
    assert json_nesting_depth(big) == 2
    assert time.perf_counter() - start < 0.5  # the loop took about a second here
