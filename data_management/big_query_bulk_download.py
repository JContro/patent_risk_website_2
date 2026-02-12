import os
from google.cloud import bigquery
import pandas as pd

# CONFIGURATION
# Replace with your actual Google Cloud Project ID
PROJECT_ID = "patent-risk-250624" 

# 1. Initialize the BigQuery Client with your project ID
client = bigquery.Client(project=PROJECT_ID)

# 2. Optimized SQL Query
# We use a smaller limit (10) for the first test run
sql_query = """
SELECT 
    *
FROM 
    `patents-public-data.patents.publications`
WHERE 
    publication_date > 20250110

"""

print(f"Connecting to BigQuery via project: {PROJECT_ID}...")

try:
    # 3. Execute and convert
    query_job = client.query(sql_query)
    df = query_job.to_dataframe()

    # 4. Save to Parquet (Better for large text)
    output_file = "patent_sample.parquet"
    df.to_parquet(output_file, compression='snappy')
    

    print(f"Successfully downloaded {len(df)} patents.")
    print(f"Files saved: {output_file} and patent_sample.csv")

except Exception as e:
    print(f"Error encountered: {e}")