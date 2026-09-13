from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from company_intel.config import Settings
from company_intel.extractor import Extractor, UsageLedger, tool_schema, two_sentences, validate_evidence
from company_intel.schema import CompanyFacts


def facts_data():
    return {"company_overview": "Acme builds API tools. Its platform serves developers.",
            "target_audience": "Developers", "contact_points": [{"type": "sales", "email": "sales@acme.com"}],
            "leadership": [{"name": "Ada Lovelace", "role": "CEO", "linkedin_url": None, "source": "site"}],
            "confidence_score": 0.9}


EVIDENCE = "PAGE: https://acme.com/team\nAda Lovelace\nCEO\nAcme builds API tools for developers. sales@acme.com"


def response(data, input_tokens=100, output_tokens=50):
    block = SimpleNamespace(type="tool_use", name="emit_company_intel", input=data)
    return SimpleNamespace(id="msg_test", usage=SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens),
                           stop_reason="tool_use", content=[block])


def test_contract_excludes_computed_metadata_and_is_strict():
    tool = tool_schema()
    assert tool["strict"] is True
    properties = tool["input_schema"]["properties"]
    assert set(properties) == set(CompanyFacts.model_fields)
    assert tool["input_schema"]["additionalProperties"] is False
    assert "token_usage" not in properties


def test_unsupported_entities_removed_and_confidence_capped():
    data = facts_data()
    data["contact_points"][0]["email"] = "invented@acme.com"
    data["leadership"][0]["name"] = "Fictional Person"
    errors = []
    validated = validate_evidence(CompanyFacts.model_validate(data), EVIDENCE, errors)
    assert validated.contact_points == []
    assert validated.leadership == []
    assert validated.confidence_score == 0.6
    assert len(errors) == 2


def test_name_and_role_need_same_page_and_profile_needs_literal_evidence():
    data = facts_data()
    data["leadership"][0]["linkedin_url"] = "https://linkedin.com/in/invented"
    data["leadership"][0]["source"] = "search"
    validated = validate_evidence(CompanyFacts.model_validate(data), EVIDENCE, [])
    assert validated.leadership[0].linkedin_url is None
    assert validated.leadership[0].source == "site"
    split_evidence = "PAGE: a\nAda Lovelace\nPAGE: b\nCEO"
    assert not validate_evidence(CompanyFacts.model_validate(data), split_evidence, []).leadership


@pytest.mark.parametrize("text,valid", [("Acme makes tools. Developers use them.", True),
    ("Acme Inc. makes tools. Developers use them.", True), ("Only one sentence.", False),
    ("One. Two. Three.", False), ("No sentence punctuation", False)])
def test_two_sentence_overview(text, valid):
    assert two_sentences(text) is valid


async def test_extraction_counts_real_usage_and_sends_strict_tool():
    messages = SimpleNamespace(count_tokens=AsyncMock(return_value=SimpleNamespace(input_tokens=200)),
                               create=AsyncMock(return_value=response(facts_data())))
    ledger = UsageLedger()
    extractor = Extractor(SimpleNamespace(messages=messages), Settings(), ledger)
    facts = await extractor.extract("acme.com", EVIDENCE, [])
    assert facts.leadership[0].name == "Ada Lovelace"
    assert ledger.tokens() == {"input_tokens": 100, "output_tokens": 50}
    assert ledger.cost(Settings()) == 0.00035
    kwargs = messages.create.await_args.kwargs
    assert kwargs["tools"][0]["strict"] is True
    assert kwargs["tool_choice"]["name"] == "emit_company_intel"
    assert "<html" not in kwargs["messages"][0]["content"]


async def test_validation_retry_usage_is_not_lost():
    invalid = facts_data()
    invalid["company_overview"] = "Only one sentence."
    messages = SimpleNamespace(count_tokens=AsyncMock(return_value=SimpleNamespace(input_tokens=200)),
                               create=AsyncMock(side_effect=[response(invalid), response(facts_data())]))
    ledger = UsageLedger()
    errors = []
    await Extractor(SimpleNamespace(messages=messages), Settings(), ledger).extract("acme.com", EVIDENCE, errors)
    assert ledger.input_tokens == 200 and ledger.output_tokens == 100
    assert len(ledger.calls) == 2 and errors


async def test_provider_count_shrinks_context_before_generation():
    messages = SimpleNamespace(count_tokens=AsyncMock(side_effect=[SimpleNamespace(input_tokens=20000),
        SimpleNamespace(input_tokens=9000)]), create=AsyncMock(return_value=response(facts_data())))
    extractor = Extractor(SimpleNamespace(messages=messages), Settings(), UsageLedger())
    await extractor.extract("acme.com", EVIDENCE + " filler" * 5000, [])
    assert messages.count_tokens.await_count == 2
    assert len(extractor.context_sent) < len(EVIDENCE + " filler" * 5000)


async def test_api_failure_does_not_invent_usage():
    messages = SimpleNamespace(count_tokens=AsyncMock(side_effect=ValueError("API unavailable")), create=AsyncMock())
    ledger = UsageLedger()
    with pytest.raises(ValueError):
        await Extractor(SimpleNamespace(messages=messages), Settings(), ledger).extract("acme.com", EVIDENCE, [])
    assert ledger.tokens() == {"input_tokens": 0, "output_tokens": 0}
    messages.create.assert_not_awaited()
