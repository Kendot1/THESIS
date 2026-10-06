"""Inventory public DA-CAR HTML search results; no inferred publication dates."""
import argparse
import json
from pathlib import Path
from urllib.parse import urlparse, parse_qs

from bs4 import BeautifulSoup
try:
    from .build_context import load_capture
except ImportError:
    from build_context import load_capture


def parse_results(content):
    soup = BeautifulSoup(content, "html.parser")
    results = []
    for article in soup.select("#content article"):
        title = article.select_one(".entry-title a")
        if title is None:
            continue
        url = title.get("href", "")
        parsed = urlparse(url)
        query = parse_qs(parsed.query)
        identity_keys = [key for key in ("p", "page_id") if key in query]
        ids = query[identity_keys[0]] if len(identity_keys) == 1 else []
        if parsed.hostname != "car.da.gov.ph" or len(ids) != 1 or not ids[0].isdigit():
            raise ValueError(f"Unexpected article URL: {url}")
        summary = article.select_one(".entry-summary")
        results.append({"id": "car_" + identity_keys[0] + "_" + ids[0], "url": url,
                        "title": title.get_text(" ", strip=True),
                        "summary": summary.get_text(" ", strip=True) if summary else None,
                        "historical_publication_verified": False})
    pagination = [{"url": a.get("href"), "label": a.get_text(" ", strip=True)}
                  for a in soup.select(".pagination a, .nav-links a, .navigation a")]
    return results, pagination


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--capture", required=True, type=Path)
    p.add_argument("--output", required=True, type=Path)
    args = p.parse_args()
    manifest, manifest_hash, artifacts = load_capture(args.capture)
    queries, unique = [], {}
    for source_id, (record, content) in artifacts.items():
        results, pagination = parse_results(content)
        queries.append({"source_id": source_id, "url": record["url"],
                        "artifact_sha256": record["artifact_sha256"],
                        "search_year": record.get("search_year"),
                        "search_term": record.get("search_term"),
                        "results": results, "pagination": pagination})
        for item in results:
            existing = unique.setdefault(item["id"], {**item, "discovered_in": []})
            if existing["url"] != item["url"]:
                raise ValueError("Conflicting article identity")
            existing["discovered_in"].append(source_id)
    args.output.mkdir(parents=True, exist_ok=True)
    result = {"schema_version": 1, "capture_sha256": manifest_hash,
              "queries": queries, "unique_articles": list(unique.values()),
              "acquisition_failures": [r for r in manifest["records"] if r["status"] != "archived"],
              "note": "Search filters and summaries are discovery hints, not verified publication/reference dates. Empty result is not proof that no event occurred."}
    for filename, obj in (("inventory.json", result), ("article_sources.json", {
            "schema_version": 1, "seed_documents": [{"id": k, "url": r["url"]} for k, r in unique.items()]})):
        with (args.output / filename).open("x", encoding="utf-8") as stream:
            json.dump(obj, stream, indent=2)
    print(json.dumps({"queries": len(queries), "unique_articles": len(unique),
                      "query_counts": {q["source_id"]: len(q["results"]) for q in queries},
                      "articles": [{"id": k, "title": v["title"]} for k, v in unique.items()]}, ensure_ascii=True))


if __name__ == "__main__":
    main()
