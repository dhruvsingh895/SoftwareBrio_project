"""Public record contract and the smaller contract exposed to the LLM."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Contact(StrictModel):
    type: str
    email: str


class TeamMember(StrictModel):
    name: str
    role: str
    linkedin_url: str | None = None
    source: Literal["site", "search"]


class CompanyFacts(StrictModel):
    """Only fields inferred from the provided evidence; no operational metadata."""

    company_overview: str = Field(description="Exactly two sentences, or empty if unknown.")
    target_audience: str
    contact_points: list[Contact]
    leadership: list[TeamMember]
    confidence_score: float = Field(ge=0.0, le=1.0)


class CompanyIntel(CompanyFacts):
    domain: str
    pages_crawled: list[str]
    crawl_errors: list[str]
    token_usage: dict[str, int]
    estimated_cost_usd: float = Field(ge=0.0)

    @classmethod
    def empty(cls, domain: str, errors: list[str] | None = None) -> "CompanyIntel":
        return cls(
            domain=domain, company_overview="", target_audience="",
            contact_points=[], leadership=[], confidence_score=0.0,
            pages_crawled=[], crawl_errors=list(errors or []),
            token_usage={"input_tokens": 0, "output_tokens": 0},
            estimated_cost_usd=0.0,
        )
