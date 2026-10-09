"""The JSON nesting guard reads a multi-megabyte result.json in milliseconds
and counts exactly what the character loop it replaced counted."""

from __future__ import annotations

import json
import random
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
        '"[\\',  # an open string whose last character is a lone backslash
        '{"a": "[[[\\',
        '"\\\\',
        '"\\\\\\',
        '["x\\\n"]]',
    ],
)
def test_the_regex_scan_counts_like_the_character_loop(text: str) -> None:
    assert json_nesting_depth(text) == _by_the_character(text)


def test_the_regex_scan_counts_like_the_character_loop_on_arbitrary_text() -> None:
    """Valid or not, whatever the alphabet of brackets, quotes and escapes makes."""
    rng = random.Random(7)
    alphabet = list('{}[]"\\ab\n1:,')
    for _ in range(3000):
        text = "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 40)))
        assert json_nesting_depth(text) == _by_the_character(text), repr(text)


@pytest.mark.parametrize(
    "shape",
    ["one long string", "a long string of escapes", "a string that never closes"],
)
def test_one_huge_string_is_scanned_in_linear_time_and_memory(shape: str) -> None:
    """A result.json below the size limit can be one string of tens of megabytes.

    The first regex backtracked one frame per character: 40 MB took 34 s and
    4.8 GiB, 8 MB about 4 s and 1 GiB. Possessive quantifiers read it in a
    few tens of milliseconds, like the loop would, in constant memory.
    """
    megabytes = 8_000_000
    text = {
        "one long string": '{"a":"' + "x" * megabytes + '"}',
        "a long string of escapes": '{"a":"' + "\\n" * (megabytes // 2) + '"}',
        "a string that never closes": '{"a":"' + "x" * megabytes,
    }[shape]
    start = time.perf_counter()
    assert json_nesting_depth(text) == 1
    assert time.perf_counter() - start < 1.5


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
