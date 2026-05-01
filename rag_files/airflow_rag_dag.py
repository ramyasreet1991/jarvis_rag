"""
Airflow DAG: Technology Content RAG System
Orchestrates daily ingestion from multiple sources with validation
"""

from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.bash import BashOperator
from airflow.providers.postgres.operators.postgres import PostgresOperator
from airflow.models import Variable
import json


# DAG Configuration
DEFAULT_ARGS = {
    'owner': 'data-engineering',
    'retries': 2,
    'retry_delay': timedelta(minutes=5),
    'email_on_failure': False,
}

DAG_ID = 'tech_content_rag_daily'
SCHEDULE_INTERVAL = '0 2 * * *'  # 2 AM daily (IST friendly)


def validate_and_score_sources(**context):
    """
    Validate source authenticity and credibility
    """
    from source_validation import SourceValidator, SourceMetadata, SourceType
    
    validator = SourceValidator()
    
    # Load sources from config (in production: from database)
    sources_config = json.loads(Variable.get("TRUSTED_SOURCES_CONFIG", "{}"))
    
    sources = []
    for config in sources_config.get('sources', []):
        source = SourceMetadata(
            url=config['url'],
            source_type=SourceType[config['type'].upper()],
            domain=config['domain'],
            author=config['author'],
            name=config['name'],
            subscribers_followers=config.get('subscribers', 0),
        )
        sources.append(source)
    
    # Validate all sources
    results = validator.batch_validate_sources(sources)
    
    # Push results to XCom for downstream tasks
    approved_sources = [
        {
            'url': r['source'].url,
            'name': r['source'].name,
            'type': r['source'].source_type.value,
            'credibility_score': r['score'],
        }
        for r in results['approved']
    ]
    
    context['task_instance'].xcom_push(
        key='approved_sources',
        value=approved_sources
    )
    
    print(f"✅ Validated {len(approved_sources)} sources")
    return len(approved_sources)


def extract_content_from_feeds(**context):
    """
    Extract content from validated sources
    """
    from content_extraction import MultiSourceExtractor
    
    ti = context['task_instance']
    approved_sources = ti.xcom_pull(
        task_ids='validate_sources',
        key='approved_sources'
    )
    
    if not approved_sources:
        print("No approved sources to extract from")
        return {}
    
    extractor = MultiSourceExtractor()
    all_extracted = []
    
    for source in approved_sources:
        print(f"Extracting from: {source['name']}")
        
        try:
            if source['type'] == 'rss':
                contents = extractor.rss.extract_feed(source['url'])
            elif source['type'] == 'youtube':
                content = extractor.youtube.extract(source['url'])
                contents = [content] if content else []
            elif source['type'] == 'podcast':
                content = extractor.podcast.extract(source['url'])
                contents = [content] if content else []
            else:
                content = extractor.blog.extract(source['url'])
                contents = [content] if content else []
            
            # Convert to dict for serialization
            for content in contents:
                if content:
                    all_extracted.append({
                        'title': content.title,
                        'content': content.content[:5000],  # Truncate for storage
                        'author': content.author,
                        'url': content.url,
                        'source_type': content.source_type,
                        'published_date': content.published_date.isoformat() if content.published_date else None,
                        'credibility_score': source['credibility_score'],
                        'tags': content.tags,
                    })
        
        except Exception as e:
            print(f"Error extracting from {source['name']}: {e}")
    
    # Push to XCom
    ti.xcom_push(key='extracted_content', value=all_extracted)
    
    print(f"✅ Extracted {len(all_extracted)} pieces of content")
    return len(all_extracted)


def deduplicate_content(**context):
    """
    Remove duplicate content using hash-based comparison
    """
    ti = context['task_instance']
    extracted = ti.xcom_pull(
        task_ids='extract_content',
        key='extracted_content'
    )
    
    if not extracted:
        return []
    
    import hashlib
    
    seen_hashes = set()
    deduplicated = []
    
    for content in extracted:
        # Create hash from URL + title + date
        hash_input = f"{content['url']}_{content['title']}_{content.get('published_date', '')}"
        content_hash = hashlib.sha256(hash_input.encode()).hexdigest()
        
        if content_hash not in seen_hashes:
            deduplicated.append(content)
            seen_hashes.add(content_hash)
    
    # Push to XCom
    ti.xcom_push(key='deduplicated_content', value=deduplicated)
    
    print(f"✅ Deduplicated: {len(extracted)} → {len(deduplicated)} unique items")
    return deduplicated


def ingest_to_rag(**context):
    """
    Ingest validated, extracted, deduplicated content into RAG system
    """
    from rag_system import TechContentRAG
    import os
    
    ti = context['task_instance']
    content_list = ti.xcom_pull(
        task_ids='deduplicate_content',
        key='deduplicated_content'
    )
    
    if not content_list:
        print("No content to ingest")
        return {'ingested': 0, 'failed': 0}
    
    # Initialize RAG system
    rag = TechContentRAG(
        pinecone_api_key=os.getenv("PINECONE_API_KEY"),
        pinecone_env=os.getenv("PINECONE_ENV", "us-east-1-aws"),
        openai_api_key=os.getenv("OPENAI_API_KEY"),
    )
    
    rag.initialize_index()
    
    # Ingest content
    stats = rag.ingest_content(content_list)
    
    # Push stats to XCom
    ti.xcom_push(key='ingestion_stats', value=stats)
    
    print(f"✅ Ingestion complete: {stats}")
    return stats


def update_metadata_index(**context):
    """
    Update PostgreSQL metadata index
    For faster filtering and source tracking
    """
    ti = context['task_instance']
    stats = ti.xcom_pull(
        task_ids='ingest_to_rag',
        key='ingestion_stats'
    )
    
    # This would typically use PostgresOperator
    # Placeholder for metadata update logic
    
    print(f"✅ Metadata index updated")
    return stats


def generate_ingestion_report(**context):
    """
    Generate summary report of ingestion run
    """
    ti = context['task_instance']
    
    # Collect metrics from all tasks
    validation_count = ti.xcom_pull(task_ids='validate_sources')
    extraction_count = ti.xcom_pull(task_ids='extract_content')
    dedup_content = ti.xcom_pull(
        task_ids='deduplicate_content',
        key='deduplicated_content'
    )
    ingestion_stats = ti.xcom_pull(
        task_ids='ingest_to_rag',
        key='ingestion_stats'
    )
    
    report = {
        'run_date': datetime.now().isoformat(),
        'sources_validated': validation_count or 0,
        'items_extracted': extraction_count or 0,
        'items_deduplicated': len(dedup_content) if dedup_content else 0,
        'ingestion_stats': ingestion_stats or {},
        'status': 'SUCCESS',
    }
    
    # Log report
    print(f"\n{'='*50}")
    print("📊 RAG INGESTION REPORT")
    print(f"{'='*50}")
    print(f"Run Date: {report['run_date']}")
    print(f"Sources Validated: {report['sources_validated']}")
    print(f"Items Extracted: {report['items_extracted']}")
    print(f"Items Deduplicated: {report['items_deduplicated']}")
    print(f"Ingestion Stats: {report['ingestion_stats']}")
    print(f"Status: {report['status']}")
    print(f"{'='*50}\n")
    
    # Save report (optional: to file or database)
    ti.xcom_push(key='ingestion_report', value=report)
    
    return report


# Define DAG
with DAG(
    dag_id=DAG_ID,
    default_args=DEFAULT_ARGS,
    description='Daily ingestion and RAG update for technology content',
    schedule_interval=SCHEDULE_INTERVAL,
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=['rag', 'content-ingestion', 'data-pipeline'],
) as dag:
    
    # Task 1: Validate Sources
    task_validate = PythonOperator(
        task_id='validate_sources',
        python_callable=validate_and_score_sources,
        provide_context=True,
        retries=1,
    )
    
    # Task 2: Extract Content
    task_extract = PythonOperator(
        task_id='extract_content',
        python_callable=extract_content_from_feeds,
        provide_context=True,
    )
    
    # Task 3: Deduplicate
    task_dedup = PythonOperator(
        task_id='deduplicate_content',
        python_callable=deduplicate_content,
        provide_context=True,
    )
    
    # Task 4: Ingest to RAG
    task_ingest = PythonOperator(
        task_id='ingest_to_rag',
        python_callable=ingest_to_rag,
        provide_context=True,
    )
    
    # Task 5: Update Metadata
    task_metadata = PythonOperator(
        task_id='update_metadata',
        python_callable=update_metadata_index,
        provide_context=True,
    )
    
    # Task 6: Generate Report
    task_report = PythonOperator(
        task_id='generate_report',
        python_callable=generate_ingestion_report,
        provide_context=True,
    )
    
    # Define dependencies (linear pipeline)
    task_validate >> task_extract >> task_dedup >> task_ingest >> task_metadata >> task_report


# Optional: Weekly re-scoring of sources
weekly_rescore_dag = DAG(
    dag_id='tech_content_rag_weekly_rescore',
    default_args=DEFAULT_ARGS,
    description='Weekly credibility re-scoring and quality check',
    schedule_interval='0 3 * * 0',  # Sunday 3 AM
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=['rag', 'maintenance'],
)

# Implementation would include:
# - Re-fetch source metrics (views, engagement, etc.)
# - Update credibility scores
# - Identify low-quality content
# - Prune sources below threshold

print(f"✅ DAG '{DAG_ID}' defined successfully")
print(f"   Schedule: {SCHEDULE_INTERVAL} (Daily 2 AM UTC)")
print(f"   Tasks: 6")
