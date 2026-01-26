from __future__ import annotations

from pydantic import BaseModel, Field


class EvidenceRef(BaseModel):
    type: str
    id: str | None = None
    description: str | None = None


class RiskFlag(BaseModel):
    code: str
    severity: str = Field(pattern="^(low|medium|high)$")
    message: str
    evidence: list[EvidenceRef] = Field(default_factory=list)


class RiskScan(BaseModel):
    flags: list[RiskFlag] = Field(default_factory=list)
