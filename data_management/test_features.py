#!/usr/bin/env python3
"""Test script to verify the new filtering features work correctly."""

import re
from datetime import datetime

# Test CPC pattern with symbol prefix
def cpc_pattern_to_regex(pattern):
    if ':' in pattern:
        pattern = pattern.split(':', 1)[1]
    escaped = re.escape(pattern).replace(r'\*', '.*')
    return re.compile(f'^{escaped}$', re.IGNORECASE)

# Test date parsing
def parse_date(date_str):
    clean_date = re.sub(r'[^\d\-/]', '', date_str)
    formats = ['%Y%m%d', '%Y-%m-%d', '%m/%d/%Y', '%d/%m/%Y']
    for fmt in formats:
        try:
            return datetime.strptime(clean_date, fmt)
        except ValueError:
            continue
    return None

print("=" * 60)
print("Testing new filtering features")
print("=" * 60)

print("\n1. CPC Pattern with 'class_cpc.symbol:' prefix:")
pattern = cpc_pattern_to_regex('class_cpc.symbol:G06N*')
print(f"   Input: class_cpc.symbol:G06N*")
print(f"   Regex: {pattern.pattern}")
test_codes = ['G06N3/00', 'G06N20/00', 'G06F21/00', 'g06n5/043']
for code in test_codes:
    match = pattern.match(code)
    print(f"   {code}: {'MATCH' if match else 'NO MATCH'}")

print("\n2. Date Parsing:")
test_dates = ['04/01/2021', '20210401', '2021-04-01', '04/01/2025']
for d in test_dates:
    parsed = parse_date(d)
    print(f"   {d} -> {parsed}")

print("\n3. Simple date range check:")
start = parse_date('04/01/2021')
end = parse_date('04/01/2025')
test_patent_dates = [
    ('2021-03-15', False),  # Before start
    ('2021-04-02', True),   # After start
    ('2023-06-15', True),   # In range
    ('2025-04-01', True),   # At end
    ('2025-04-02', False),  # After end
]
for date_str, expected in test_patent_dates:
    pdate = parse_date(date_str)
    in_range = start <= pdate <= end
    status = "PASS" if in_range == expected else "FAIL"
    print(f"   {date_str} (in range {start.date()} to {end.date()}): {in_range} [{status}]")

print("\n" + "=" * 60)
print("All tests completed!")
print("=" * 60)
