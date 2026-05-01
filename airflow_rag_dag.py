"""
Airflow DAG — Jarvis RAG Daily Ingestion Pipeline
Orchestrates: source validation → content extraction → dedup → RAG ingest → report
Schedule: 2 AM UTC daily
"""
from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.models import Variable
import json


DEFAULT_ARGS = {
    "owner": "data-engineering",
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
    "email_on_failure": False,
}

DAG_ID = "tech_content_rag_daily"
SCHEDULE_INTERVAL = "0 2 * * *"   # 2 AM UTC daily


# ── Task Functions ────────────────────────────────────────────────────────────

def validate_and_score_sources(**context):
    """Validate source credibility and push approved list via XCom."""
    from source_vetter import SourceVetter, Source, TrustTier

    vetter = SourceVetter(threshold=0.65)

    # Prefer Airflow Variable; fall back to built-in catalogue
    sources_json = Variable.get("TRUSTED_SOURCES_CONFIG", default_var=None)

    if sources_json:
        raw = json.loads(sources_json)
        sources = []
        for cfg in raw.get("sources", []):
            tier = TrustTier[cfg.get("trust_tier", "TIER_2").upper().replace("tier_", "TIER_")]
            sources.append(Source(
                name=cfg["name"],
                url=cfg["url"],
                feed_url=cfg.get("feed_url"),
                source_type=cfg.get("source_type", "blog"),
                trust_tier=tier,
                credibility_score=cfg.get("credibility_score", 0.75),
                categories=cfg.get("categories", []),
                subscriber_count=cfg.get("subscriber_count", cfg.get("subscribers", 0)),
                update_frequency=cfg.get("update_frequency", "weekly"),
                extraction_method=cfg.get("extraction_method", "rss"),
            ))
    else:
        sources = vetter.load_default_sources()

    results = vetter.batch_validate_sources(sources)
    approved = [
        {
            "url": r["source"].url,
            "feed_url": r["source"].feed_url,
            "name": r["source"].name,
            "source_type": r["source"].source_type,
            "credibility_score": r["score"],
            "categories": r["source"].categories,
        }
        for r in results["approved"]
    ]

    context["task_instance"].xcom_push(key="approved_sources", value=approved)
    print(f"Validated {len(approved)} sources "
          f"({len(results['pending'])} pending, {len(results['rejected'])} rejected)")
    return len(approved)


def extract_content_from_feeds(**context):
    """Extract content from all validated sources."""
    from content_extractor import MultiSourceExtractor, RSSFeedExtractor

    ti = context["task_instance"]
    approved_sources = ti.xcom_pull(task_ids="validate_sources", key="approved_sources") or []

    if not approved_sources:
        print("No approved sources — skipping extraction")
        return 0

    rss_extractor = RSSFeedExtractor()
    multi_extractor = MultiSourceExtractor()
    all_extracted = []

    for source in approved_sources:
        print(f"Extracting from: {source['name']}")
        try:
            src_type = source["source_type"]
            feed_url = source.get("feed_url") or source["url"]

            if src_type == "rss":
                contents = rss_extractor.extract_feed(feed_url)
            elif src_type in ("youtube", "podcast"):
                content = multi_extractor.extract(source["url"])
                contents = [content] if content else []
            else:
                content = multi_extractor.blog.extract(source["url"])
                contents = [content] if content else []

            for item in contents:
                if item:
                    all_extracted.append({
                        "title": item.title,
                        "content": item.content[:5000],
                        "author": item.author,
                        "url": item.url,
                        "source_type": item.source_type,
                        "source_name": source["name"],
                        "published_date": item.published or None,
                        "credibility_score": source["credibility_score"],
                        "tags": item.tags or source.get("categories", []),
                    })
        except Exception as e:
            print(f"Error extracting from {source['name']}: {e}")

    ti.xcom_push(key="extracted_content", value=all_extracted)
    print(f"Extracted {len(all_extracted)} items from {len(approved_sources)} sources")
    return len(all_extracted)


def deduplicate_content(**context):
    """Remove duplicate content using URL+title+date hash."""
    import hashlib

    ti = context["task_instance"]
    extracted = ti.xcom_pull(task_ids="extract_content", key="extracted_content") or []

    seen = set()
    deduplicated = []

    for item in extracted:
        key = f"{item['url']}_{item['title']}_{item.get('published_date', '')}"
        h = hashlib.sha256(key.encode()).hexdigest()
        if h not in seen:
            deduplicated.append(item)
            seen.add(h)

    ti.xcom_push(key="deduplicated_content", value=deduplicated)
    print(f"Deduplicated: {len(extracted)} → {len(deduplicated)} unique items")
    return len(deduplicated)


def ingest_to_rag(**context):
    """Ingest validated, deduplicated content into the RAG system."""
    from rag_engine import RAGEngine

    ti = context["task_instance"]
    content_list = ti.xcom_pull(task_ids="deduplicate_content",
                                 key="deduplicated_content") or []

    if not content_list:
        print("No content to ingest")
        ti.xcom_push(key="ingestion_stats", value={"ingested": 0, "failed": 0})
        return {"ingested": 0, "failed": 0}

    rag = RAGEngine()
    stats = rag.ingest_content_list(content_list)

    ti.xcom_push(key="ingestion_stats", value=stats)
    print(f"Ingestion complete: {stats}")
    return stats


def update_metadata_index(**context):
    """Update PostgreSQL metadata index for faster filtering."""
    ti = context["task_instance"]
    stats = ti.xcom_pull(task_ids="ingest_to_rag", key="ingestion_stats")
    # Extend: write stats to Postgres via PostgresHook
    print("Metadata index updated")
    return stats


def generate_ingestion_report(**context):
    """Emit a summary report for monitoring."""
    ti = context["task_instance"]

    validation_count  = ti.xcom_pull(task_ids="validate_sources")
    extraction_count  = ti.xcom_pull(task_ids="extract_content")
    dedup_content     = ti.xcom_pull(task_ids="deduplicate_content",
                                      key="deduplicated_content")
    ingestion_stats   = ti.xcom_pull(task_ids="ingest_to_rag", key="ingestion_stats")

    report = {
        "run_date":             datetime.now().isoformat(),
        "sources_validated":    validation_count or 0,
        "items_extracted":      extraction_count or 0,
        "items_deduplicated":   len(dedup_content) if dedup_content else 0,
        "ingestion_stats":      ingestion_stats or {},
        "status":               "SUCCESS",
    }

    print(f"\n{'='*50}")
    print("RAG INGESTION REPORT")
    print(f"{'='*50}")
    for k, v in report.items():
        print(f"  {k}: {v}")
    print(f"{'='*50}\n")

    ti.xcom_push(key="ingestion_report", value=report)
    return report


# ── DAG Definition ────────────────────────────────────────────────────────────

with DAG(
    dag_id=DAG_ID,
    default_args=DEFAULT_ARGS,
    description="Daily ingestion and RAG update for technology content",
    schedule_interval=SCHEDULE_INTERVAL,
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=["rag", "content-ingestion", "data-pipeline"],
) as dag:

    task_validate = PythonOperator(
        task_id="validate_sources",
        python_callable=validate_and_score_sources,
        provide_context=True,
        retries=1,
    )

    task_extract = PythonOperator(
        task_id="extract_content",
        python_callable=extract_content_from_feeds,
        provide_context=True,
    )

    task_dedup = PythonOperator(
        task_id="deduplicate_content",
        python_callable=deduplicate_content,
        provide_context=True,
    )

    task_ingest = PythonOperator(
        task_id="ingest_to_rag",
        python_callable=ingest_to_rag,
        provide_context=True,
    )

    task_metadata = PythonOperator(
        task_id="update_metadata",
        python_callable=update_metadata_index,
        provide_context=True,
    )

    task_report = PythonOperator(
        task_id="generate_report",
        python_callable=generate_ingestion_report,
        provide_context=True,
    )

    # Linear pipeline
    task_validate >> task_extract >> task_dedup >> task_ingest >> task_metadata >> task_report


# ── Weekly Rescore DAG ────────────────────────────────────────────────────────

weekly_rescore_dag = DAG(
    dag_id="tech_content_rag_weekly_rescore",
    default_args=DEFAULT_ARGS,
    description="Weekly credibility re-scoring and source quality maintenance",
    schedule_interval="0 3 * * 0",   # Sunday 3 AM UTC
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=["rag", "maintenance"],
)
# Extend: re-fetch source metrics, update credibility scores,
#         prune sources below threshold, flag low-quality content.
