#!/usr/bin/env python3
"""
Look up stock tickers for patent applicant/assignee organizations.

This script:
  1. Extracts all distinct organization names from Patent.applicants JSONField
  2. Creates Entity records for any organization not yet in the Entity table
  3. Batches entity names and sends them to an LLM (via OpenRouter) to find
     stock market ticker symbols for publicly traded companies
  4. Saves tickers back to the Entity table

Usage:
  python lookup_tickers.py [--limit N] [--batch-size 50] [--resume]

Options:
  --limit N         Only process N entities (for testing)
  --batch-size N    Number of names per API call (default: 50)
  --resume          Skip entities that already have tickers set
  --no-create       Skip creating Entity records (only lookup existing ones)
  --backend vllm    Use vLLM instead of OpenRouter (default: openrouter)
"""

import os
import sys
import django
import json
import time
import re
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from accounts.models import Entity, Patent
from django.conf import settings
from django.db import transaction
from django.db.models import Count


# ---------------------------------------------------------------------------
# LLM API call — generic OpenRouter or vLLM
# ---------------------------------------------------------------------------

def call_llm(prompt, *, backend='openrouter', model=None, temperature=0.1):
    """
    Call an LLM API and return the response text.
    Uses OpenRouter by default (requires OPENROUTER_API_KEY in .env).
    Falls back to vLLM if backend='vllm'.
    """
    import requests

    if backend == 'openrouter':
        api_key = settings.OPENROUTER_API_KEY
        if not api_key:
            raise ValueError("OPENROUTER_API_KEY not set in .env")
        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://patentrisk.com",
            "X-Title": "Patent Ticker Lookup",
        }
        model = model or "deepseek/deepseek-v3.2"
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
            "response_format": {"type": "json_object"},
        }
    else:
        vllm_url = getattr(settings, 'VLLM_API_URL', 'http://vllm-api-server:8000')
        url = f"{vllm_url}/v1/chat/completions"
        model = model or "google/gemma-4-26B-A4B-it"
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
            "max_tokens": 4096,
        }
        headers = {"Content-Type": "application/json"}

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=120)
        response.raise_for_status()
        result = response.json()
        if 'choices' in result and len(result['choices']) > 0:
            return result['choices'][0]['message']['content']
        return str(result)
    except Exception as e:
        raise Exception(f"LLM API call failed: {e}")


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------

TICKER_PROMPT = """You are a financial data extraction assistant. Given a list of company organization names, your job is to identify which are publicly traded corporations and return their stock ticker symbols.

Rules:
- Only return a ticker if the company is PUBLICLY TRADED on a major stock exchange (NYSE, NASDAQ, LSE, TSE, HKEX, Euronext, etc.)
- For multinational parent companies, prefer the primary ticker (usually on the company's home exchange)
- If a company is a subsidiary of a publicly traded parent, return the parent's ticker AND set "is_subsidiary": true
- If a company is private, a university, a research institute, a government entity, a non-profit, or otherwise not publicly traded, set "ticker": null
- For tickers, use the standard uppercase format (e.g., "AAPL", "MSFT", "GOOGL", "TSLA")
- Pay attention: many company names look official but are actually small consulting firms or LLCs — they are NOT publicly traded
- Be conservative — only assign a ticker when you are confident the company is publicly traded
- If unsure, default to null

Return a JSON object with key "companies" — an array of objects, one per input company, in the same order as provided:
{
  "companies": [
    {
      "name": "<exact input company name>",
      "ticker": "<ticker or null>",
      "exchange": "<exchange name or null>",
      "is_subsidiary": false,
      "notes": "<brief reason or null>"
    }
  ]
}

Input companies:
{company_names}
"""


# ---------------------------------------------------------------------------
# Data extraction helpers
# ---------------------------------------------------------------------------

def extract_distinct_organizations():
    """
    Extract all unique organization names from Patent.applicants JSON field.
    Returns a set of normalized (cleaned) organization name strings.
    """
    print("[1/4] Extracting distinct organization names from patents...")
    org_names = set()
    processed = 0

    for patent in Patent.objects.filter(applicants__isnull=False).iterator(chunk_size=500):
        for applicant in patent.applicants:
            org = applicant.get('organization')
            if org:
                name = org.strip()
                if name:
                    org_names.add(name)
        processed += 1
        if processed % 20000 == 0:
            print(f"  Scanned {processed} patents... ({len(org_names)} unique orgs found)")

    print(f"  Complete: {len(org_names)} distinct organization names from {processed} patents")
    return org_names


def ensure_entity_records(org_names, *, entity_type='applicant'):
    """
    Create Entity records for organization names that don't exist yet.

    Handles case-variant dedup: if "Apple Inc." and "APPLE INC." both exist,
    the first one encountered is kept and subsequent variants are skipped.
    Also merges existing case-variant duplicates before creating new records.

    Returns the count of newly created records.
    """
    print(f"[2/4] Ensuring Entity records exist (type={entity_type})...")

    # ---- Merge any existing case-variant duplicates ----
    _merge_case_duplicates(entity_type)

    # ---- Build set of existing names (case-insensitive) ----
    existing = set(
        Entity.objects.filter(entity_type=entity_type)
        .values_list('name', flat=True)
    )
    existing_upper = {n.upper() for n in existing}

    # ---- Create only truly new names ----
    to_create = []
    for org_name in org_names:
        if org_name.upper() not in existing_upper:
            existing_upper.add(org_name.upper())
            to_create.append(Entity(name=org_name, entity_type=entity_type))

    if to_create:
        Entity.objects.bulk_create(to_create, batch_size=500, ignore_conflicts=True)
        print(f"  Created {len(to_create)} new Entity records")
    else:
        print("  No new Entity records needed")

    # ---- Final sanity: print duplicate count ----
    _report_duplicates(entity_type)

    return len(to_create)


def _merge_case_duplicates(entity_type='applicant'):
    """
    Merge case-variant duplicate Entity records.
    Keeps the record with the shortest name (usually the most normalized form)
    and reassigns any patents from duplicates to the kept record.
    """
    from django.db.models.functions import Lower
    from django.db.models import Count

    dupes = (
        Entity.objects.filter(entity_type=entity_type)
        .annotate(lower_name=Lower('name'))
        .values('lower_name')
        .annotate(c=Count('entity_id'))
        .filter(c__gt=1)
    )

    merged_count = 0
    for group in dupes:
        variants = list(
            Entity.objects.filter(entity_type=entity_type, name__iexact=group['lower_name'])
            .order_by('name')  # deterministic order
        )
        if len(variants) <= 1:
            continue

        # Keep the record with the shortest name (usually the most canonical)
        # or, if tied, the alphabetically first
        keeper = min(variants, key=lambda e: (len(e.name), e.name))
        to_delete = [e for e in variants if e.entity_id != keeper.entity_id]

        for dup in to_delete:
            # Reassign M2M relations
            for patent in dup.patents.all():
                keeper.patents.add(patent)
            for search in dup.searches.all():
                keeper.searches.add(search)
            dup.delete()
            merged_count += 1

    if merged_count:
        print(f"  Merged {merged_count} case-variant duplicate entities")


def _report_duplicates(entity_type='applicant'):
    """Print a count of remaining exact-name duplicates (should be 0)."""
    from django.db.models import Count
    exact_dupes = (
        Entity.objects.filter(entity_type=entity_type)
        .values('name')
        .annotate(c=Count('entity_id'))
        .filter(c__gt=1)
    )
    if exact_dupes.count() > 0:
        print(f"  WARNING: {exact_dupes.count()} exact duplicate names remain "
              f"(unique_together constraint may not be enforced on SQLite)")


def get_entities_without_tickers(*, entity_type='applicant', limit=None):
    """
    Get Entity records (for companies/applicants) that don't have tickers yet.
    Returns a list of Entity objects sorted by name.
    """
    qs = Entity.objects.filter(entity_type=entity_type, ticker__isnull=True).order_by('name')
    if limit:
        qs = qs[:limit]
    return list(qs)


# ---------------------------------------------------------------------------
# Ticker lookup (batch)
# ---------------------------------------------------------------------------

def parse_ticker_response(raw_text):
    """Parse JSON from LLM response, handling code fences and extra text."""
    if not raw_text:
        return None
    text = raw_text.strip()
    # Strip markdown code fences
    if text.startswith('```json'):
        text = text[7:]
    elif text.startswith('```'):
        text = text[3:]
    if text.endswith('```'):
        text = text[:-3]
    text = text.strip()

    # Find the outermost { ... }
    start = text.find('{')
    end = text.rfind('}')
    if start != -1 and end > start:
        text = text[start:end+1]

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def lookup_tickers_batch(entity_batch, *, backend='openrouter'):
    """
    Send a batch of entity names to the LLM and return parsed results.
    entity_batch: list of Entity objects
    Returns: dict mapping entity_id -> ticker string (or None)
    """
    names = [e.name for e in entity_batch]
    names_str = json.dumps(names, indent=2)

    prompt = TICKER_PROMPT.replace('{company_names}', names_str)

    raw = call_llm(prompt, backend=backend)
    parsed = parse_ticker_response(raw)

    if not parsed or 'companies' not in parsed:
        print(f"  WARNING: Could not parse LLM response for batch. Raw: {raw[:200]}...")
        return {}

    result = {}
    companies = parsed['companies']

    if len(companies) != len(entity_batch):
        print(f"  WARNING: Expected {len(entity_batch)} results, got {len(companies)}. "
              f"Attempting name-based matching.")

        # Build name->ticker mapping from response
        name_to_ticker = {}
        for c in companies:
            name_to_ticker[c.get('name', '').strip().upper()] = c.get('ticker')

        for entity in entity_batch:
            ticker = name_to_ticker.get(entity.name.strip().upper())
            if ticker:
                result[entity.entity_id] = ticker.upper() if isinstance(ticker, str) else ticker
            else:
                result[entity.entity_id] = None
    else:
        for entity, c in zip(entity_batch, companies):
            ticker = c.get('ticker')
            if ticker:
                result[entity.entity_id] = ticker.upper() if isinstance(ticker, str) else ticker
            else:
                result[entity.entity_id] = None

    return result


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def run_ticker_lookup(*, limit=None, batch_size=50, resume=True, create_entities=True,
                      backend='openrouter'):
    """
    Full pipeline:
      1. Extract distinct organization names from patent data
      2. Create Entity records for any new names
      3. Batch lookup tickers via LLM
      4. Save tickers to database
    """
    start_time = datetime.now()

    # ---- Step 1: Extract org names ----
    org_names = extract_distinct_organizations()
    if not org_names:
        print("No organization names found. Exiting.")
        return

    # ---- Step 2: Create Entity records ----
    if create_entities:
        ensure_entity_records(org_names)

    # ---- Step 3: Get entities needing tickers ----
    entity_type = 'applicant'
    entities = get_entities_without_tickers(entity_type=entity_type, limit=limit)
    total = len(entities)
    print(f"[3/4] Found {total} entities needing ticker lookup")

    if total == 0:
        print("  All entities already have tickers. Done.")
        return

    if limit:
        print(f"  (limited to first {limit})")

    # ---- Step 4: Batch lookup ----
    print(f"[4/4] Looking up tickers in batches of {batch_size} via {backend}...")
    analyzed = 0
    errors = 0
    tickers_found = 0
    ticker_start = time.time()

    for i in range(0, total, batch_size):
        batch = entities[i:i + batch_size]
        batch_num = (i // batch_size) + 1
        total_batches = (total + batch_size - 1) // batch_size

        try:
            results = lookup_tickers_batch(batch, backend=backend)

            # Save results to database
            with transaction.atomic():
                for entity in batch:
                    ticker = results.get(entity.entity_id)
                    if ticker:
                        entity.ticker = ticker
                        entity.save(update_fields=['ticker'])
                        tickers_found += 1
                    else:
                        # Mark as explicitly checked (save null)
                        entity.ticker = None
                        entity.save(update_fields=['ticker'])

            analyzed += len(batch)

        except Exception as e:
            errors += 1
            print(f"  ERROR batch {batch_num}/{total_batches}: {e}")
            # Avoid hammering API on repeated failures
            if errors >= 5:
                print("  Too many consecutive errors. Stopping.")
                break

        # Progress report
        elapsed = time.time() - ticker_start
        rate = analyzed / elapsed if elapsed > 0 else 0
        remaining = (total - analyzed) / rate if rate > 0 else 0
        print(f"  Batch {batch_num}/{total_batches} done | "
              f"{analyzed}/{total} entities ({rate:.1f}/sec) | "
              f"{tickers_found} tickers found | "
              f"~{remaining/60:.1f} min remaining")

    elapsed = time.time() - ticker_start
    print()
    print("=" * 60)
    print(f"TICKER LOOKUP COMPLETE")
    print(f"  Total entities processed: {analyzed}")
    print(f"  Tickers found:            {tickers_found}")
    print(f"  No ticker (private/etc):  {analyzed - tickers_found}")
    print(f"  Batch errors:             {errors}")
    print(f"  Total time:               {elapsed/60:.1f} min")
    print(f"  Average rate:             {analyzed/elapsed:.1f} entities/sec")
    print("=" * 60)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(
        description='Look up stock tickers for patent applicant organizations'
    )
    parser.add_argument('--limit', type=int, default=None,
                        help='Only process N entities (for testing)')
    parser.add_argument('--batch-size', type=int, default=50,
                        help='Number of names per API call (default: 50)')
    parser.add_argument('--resume', action='store_true', default=True,
                        help='Skip entities that already have tickers')
    parser.add_argument('--no-create', action='store_true', default=False,
                        help='Skip creating Entity records')
    parser.add_argument('--backend', choices=['openrouter', 'vllm'], default='openrouter',
                        help='LLM backend to use (default: openrouter)')

    args = parser.parse_args()

    run_ticker_lookup(
        limit=args.limit,
        batch_size=args.batch_size,
        resume=args.resume,
        create_entities=not args.no_create,
        backend=args.backend,
    )