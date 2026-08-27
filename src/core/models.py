from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field

class SeverityLevel(str, Enum):
    MUITO_ALTO = "MUITO_ALTO"
    ALTO = "ALTO"
    MEDIO = "MEDIO"
    BAIXO = "BAIXO"
    NEUTRO = "NEUTRO"

class ThesisPillar(BaseModel):
    title: str = Field(..., description="Short title of the thesis pillar (e.g., 'High Dividend Yield')")
    description: str = Field(..., description="Detailed description of the premise or assumption")

class InvestmentThesis(BaseModel):
    ticker: str = Field(..., description="Stock ticker (e.g., PETR4)")
    company_name: str = Field(..., description="Full name of the company")
    pillars: List[ThesisPillar] = Field(..., description="List of core premises that sustain the investment thesis")
    risk_factors: List[str] = Field(default_factory=list, description="Known risks to the thesis")

class DivergenceAlert(BaseModel):
    ticker: str = Field(..., description="Stock ticker")
    severity: SeverityLevel = Field(..., description="Classification of the divergence risk")
    affected_pillar: Optional[str] = Field(None, description="The specific thesis pillar that was affected, if any")
    rationale: str = Field(..., description="Agent's reasoning for why this news impacts or confirms the thesis")
    quotes_from_thesis: List[str] = Field(default_factory=list, description="Exact quotes from the thesis document that prove the point")

class TriageResult(BaseModel):
    ticker: Optional[str] = Field(None, description="Extracted stock ticker from the news, if present")
    is_material: bool = Field(..., description="True if the news has material financial or strategic impact")
