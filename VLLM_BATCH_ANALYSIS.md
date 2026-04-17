# Patent Batch Analysis with vLLM

## Overview
Analyzes patents using local vLLM API (google/gemma-4-26B-A4B-it) instead of OpenRouter.
Processes all patents without analysis from the database.

## Quick Reference

### Check Status
```bash
# View current progress (last log lines)
docker exec patent_risk_website_2-web-1 tail -20 /app/analyze_patents.log

# Check how many patents analyzed
docker exec patent_risk_website_2-web-1 sh -c 'cd /app && python -c
  \"import django; import os; os.environ.setdefault(\"DJANGO_SETTINGS_MODULE\", \"config.settings\");
  django.setup(); from accounts.models import Analysis; print(Analysis.objects.count())\"'

# Check GPU usage
docker exec vllm-api-server nvidia-smi
```

### Stop the Process
```bash
# Find the process
docker top patent_risk_website_2-web-1 | grep analyze_patents

# Kill it (process name may vary, use PID from first column)
docker exec patent_risk_website_2-web-1 kill <PID>
```

### Start/Restart the Process
```bash
# Start in background (runs even after disconnect)
docker exec -d patent_risk_website_2-web-1 sh -c 'cd /app && python -u analyze_patents_batch.py > /app/analyze_patents.log 2>&1'

# Restart web container first if needed
docker restart patent_risk_website_2-web-1
```

### Test Single Patent
```bash
docker exec patent_risk_website_2-web-1 python /app/analyze_patent_test.py
```

## Architecture

- **vLLM API**: `http://172.19.0.3:8000` (internal Docker network)
- **Web container**: `patent_risk_website_2-web-1` on network `patent_risk_website_2_default`
- **vLLM container**: `vllm-api-server` (port 8000 internal, 8090 host)

## Processing Rate

- ~0.5 patents/second
- 180,579 patents remaining (as of last check)
- Estimated time: ~6,200 minutes (~4.3 days)

## Notes

- Process uses unbuffered output (`python -u`) for real-time logging
- Use `tail -f` or periodic `cat` to monitor progress
- Analysis results are saved to the `Analysis` table in the database