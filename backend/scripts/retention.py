"""Run on a schedule (cron / Render cron job): purge expired documents, fail stuck ones.
    python -m scripts.retention
"""
from app import repo, storage
from app.config import settings
from app.db import pool


def main() -> None:
    pool.open()
    try:
        n_stale = repo.reap_stale(settings.STALE_PROCESSING_MIN)
        purged = 0
        for d in repo.expired_documents():
            key = repo.delete_document(d["user_id"], d["id"])
            if key:
                storage.delete(key)
                repo.audit(None, "document.retention_purge", "document", d["id"])
                purged += 1
        print(f"reaped={n_stale} purged={purged}")      # counts only
    finally:
        pool.close()


if __name__ == "__main__":
    main()
