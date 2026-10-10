"""Risk-analysis results cached per filing, so the app shows a filing's last
analysis again without new LLM calls. Files live in data/cache (generated,
not committed), one per filing, keyed by its accession number."""
import json
from datetime import datetime

from config import DATA_DIR

CACHE_DIR = DATA_DIR / "cache"


def cache_path(filing, cache_dir=CACHE_DIR):
    return cache_dir / f"risk_{filing['ticker']}_{filing['accession']}.json"


def save_results(filing, results, source, created=None, cache_dir=CACHE_DIR):
    """results: overall, scores_dict {category: (score, reason)}, summary (or
    None), read_from and evidence, as the app holds them. source says where the
    result came from (an app run or an evaluation run)."""
    record = {"ticker": filing["ticker"], "accession": filing["accession"],
              "created": created or datetime.now().strftime("%Y-%m-%d %H:%M"),
              "source": source,
              "results": {**results, "scores_dict": {
                  category: list(value) for category, value in results["scores_dict"].items()}}}
    path = cache_path(filing, cache_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=1, ensure_ascii=False), encoding="utf-8")
    return path


def load_results(filing, cache_dir=CACHE_DIR):
    """The cached results with "created" and "source" added, or None."""
    path = cache_path(filing, cache_dir)
    if not path.exists():
        return None
    record  = json.loads(path.read_text(encoding="utf-8"))
    results = record["results"]
    results["scores_dict"] = {category: tuple(value)
                              for category, value in results["scores_dict"].items()}
    return {**results, "created": record["created"], "source": record["source"]}
