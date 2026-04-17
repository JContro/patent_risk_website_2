#!/usr/bin/env python3
import os
import sys
import django
import json
from datetime import datetime

sys.stdout = os.fdopen(sys.stdout.fileno(), 'w', buffering=1)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from accounts.models import Patent, Analysis
from accounts.vllm_service import analyse_patent_with_vllm
from django.conf import settings
from django.db import transaction


def _parse_json_response(raw_response):
    if not raw_response:
        return None
    text = raw_response.strip()
    if text.startswith('```json'):
        text = text[7:]
    elif text.startswith('```'):
        text = text[3:]
    if text.endswith('```'):
        text = text[:-3]
    json_start = text.find('{')
    json_array_start = text.find('[')
    if json_start != -1 and (json_array_start == -1 or json_start < json_array_start):
        json_start_obj = text.find('{', json_start)
        json_end = max(text.rfind('}'), text.rfind('}]'))
        if json_end > json_start_obj:
            text = text[json_start_obj:json_end+1]
    elif json_array_start != -1:
        json_end = max(text.rfind(']'), text.rfind('}\n'))
        if json_end > json_array_start:
            text = text[json_array_start:json_end+1]
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    try:
        start = text.find('[')
        end = text.rfind(']')
        if start != -1 and end != -1 and end > start:
            return json.loads(text[start:end+1])
    except:
        pass
    return None


def run_batch_analysis(limit=None, batch_size=10):
    prompt_template = getattr(settings, 'PATENT_ANALYSIS_PROMPT', '')
    if not prompt_template:
        print('ERROR: PATENT_ANALYSIS_PROMPT not configured')
        return
    
    patents_without_analysis = Patent.objects.filter(analysis__isnull=True)
    total_count = patents_without_analysis.count()
    
    if total_count == 0:
        print('No patents without analysis')
        return
    
    print(f'Found {total_count} patents without analysis')
    print('Using vLLM API at http://172.19.0.3:8000')
    print('-' * 60)
    
    if limit:
        patents_to_analyze = list(patents_without_analysis[:limit])
        print(f'Limited to {limit} patents')
    else:
        patents_to_analyze = list(patents_without_analysis)
    
    analyzed_count = 0
    error_count = 0
    start_time = datetime.now()
    
    for i, patent in enumerate(patents_to_analyze):
        try:
            raw_response = analyse_patent_with_vllm(patent, prompt_template)
            parsed_risks = None
            if raw_response:
                parsed_risks = _parse_json_response(raw_response)
            with transaction.atomic():
                Analysis.objects.update_or_create(
                    patent=patent,
                    defaults={
                        'raw_response': raw_response,
                        'parsed_risks': parsed_risks
                    }
                )
            analyzed_count += 1
            if (analyzed_count % batch_size) == 0 or analyzed_count == 1:
                elapsed = (datetime.now() - start_time).total_seconds()
                rate = analyzed_count / elapsed if elapsed > 0 else 0
                remaining = (total_count - analyzed_count) / rate if rate > 0 else 0
                ts = datetime.now().strftime("%H:%M:%S")
                print(f"[{ts}] Analyzed {analyzed_count}/{len(patents_to_analyze)} patents ({rate:.1f}/sec, ~{remaining/60:.1f} min remaining)")
        except Exception as e:
            error_count += 1
            print(f'ERROR patent {patent.patent_id}: {str(e)[:100]}')
    
    elapsed = (datetime.now() - start_time).total_seconds()
    print('-' * 60)
    print(f'Complete! Analyzed: {analyzed_count}, Errors: {error_count}, Time: {elapsed/60:.1f} min')


if __name__ == '__main__':
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else None
    run_batch_analysis(limit=limit)
