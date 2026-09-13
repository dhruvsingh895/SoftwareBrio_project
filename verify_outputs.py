"""Validate saved live artifacts without invoking the browser or any API."""

import argparse
import json
import re
from pathlib import Path

from company_intel.extractor import literal_in, two_sentences, validate_evidence
from company_intel.schema import CompanyFacts, CompanyIntel
from company_intel.urls import canonical_url, domain_slug


def verify(directory: Path) -> dict:
    summary = json.loads((directory / "summary.json").read_text(encoding="utf-8"))
    combined = json.loads((directory / "output.json").read_text(encoding="utf-8"))
    assert combined == summary["records"], "Combined output differs from the run records"
    assert summary["complete"], "Batch contains incomplete records"
    assert summary["provider"] == "nvidia" and summary["free_tier_only"], "Expected the free-tier submission run"
    assert summary["pricing"]["input_usd_per_token"] == summary["pricing"]["output_usd_per_token"] == 0
    checks = []
    for row, record in zip(summary["domains"], summary["records"], strict=True):
        domain = record["domain"]
        slug = domain_slug(domain)
        on_disk = json.loads((directory / f"{slug}.json").read_text(encoding="utf-8"))
        assert record == on_disk
        validated = CompanyIntel.model_validate(on_disk, strict=True)
        evidence = json.loads((directory / "evidence" / slug / "crawl.json").read_text(encoding="utf-8"))
        context = (directory / "evidence" / slug / "context.txt").read_text(encoding="utf-8")
        assert context and not re.search(r"</?(?:html|script|style|svg|nav|footer)\b", context, re.I)
        assert len(evidence["attempted_urls"]) <= 8
        assert all(canonical_url(url, domain) for url in evidence["attempted_urls"])
        assert row["pages_crawled"] == len(evidence["pages"]) == len(validated.pages_crawled)
        assert validated.estimated_cost_usd == 0 and 0 < validated.confidence_score <= 1
        assert row["status"] == evidence["status"] == "completed"
        assert evidence["llm_calls"] and two_sentences(validated.company_overview)
        for counter in ("input_tokens", "output_tokens"):
            assert validated.token_usage[counter] > 0
            assert row[counter] == validated.token_usage[counter] == sum(call[counter] for call in evidence["llm_calls"])
        facts = CompanyFacts.model_validate({key: record[key] for key in CompanyFacts.model_fields}, strict=True)
        for person in facts.leadership:
            if person.source == "search":
                assert any(entry.get("status") == "matched" and entry.get("linkedin_url") == person.linkedin_url
                           and literal_in(person.name, entry.get("snippet", ""))
                           and literal_in(domain.split(".")[0], entry.get("snippet", ""))
                           for entry in evidence["linkedin_search"])
                person.linkedin_url = None
        cards = [card for page in evidence["pages"] for card in page.get("profile_evidence", [])]
        errors = []
        result = validate_evidence(facts, context, errors, cards)
        assert not errors, errors
        assert len(result.contact_points) == len(facts.contact_points)
        assert len(result.leadership) == len(facts.leadership)
        checks.append({"domain": domain, "schema_valid": True, "record_matches_summary": True,
                       "clean_context_chars": len(context), "pages": len(evidence["pages"]),
                       "attempts": len(evidence["attempted_urls"]), "actual_llm_calls": len(evidence["llm_calls"]),
                       "token_usage": validated.token_usage, "two_sentence_overview": True,
                       "literal_entity_evidence_valid": True,
                       "associated_site_profiles": sum(p.source == "site" and bool(p.linkedin_url) for p in validated.leadership),
                       "search_statuses": [entry["status"] for entry in evidence["linkedin_search"]]})
    assert summary["total_estimated_cost_usd"] == 0
    for counter in ("input_tokens", "output_tokens"):
        assert summary["total_" + counter] == sum(row[counter] for row in summary["domains"])
    return {"directory": directory.name, "all_records_valid": True, "checks": checks}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directories", nargs="*", type=Path, default=[Path("output"), Path("output-agentic")])
    args = parser.parse_args()
    print(json.dumps([verify(directory) for directory in args.directories], indent=2))
