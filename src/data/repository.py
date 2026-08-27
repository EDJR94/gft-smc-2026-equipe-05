from typing import Optional
from src.core.models import InvestmentThesis, ThesisPillar

# Mock Database of Investment Theses for the Demo Scenarios
_THESES_DB = {
    "PETR4": InvestmentThesis(
        ticker="PETR4",
        company_name="Petróleo Brasileiro S.A.",
        pillars=[
            ThesisPillar(
                title="Distribuição de Dividendos Extraordinários",
                description="Com a desalavancagem e forte geração de caixa do pré-sal, espera-se uma farta distribuição de dividendos extraordinários aos acionistas no curto/médio prazo.",
            ),
            ThesisPillar(
                title="Foco em E&P no Pré-sal",
                description="Alocação de capital rigorosa com foco prioritário em Exploração e Produção nas bacias do pré-sal, onde a empresa possui grande vantagem competitiva.",
            )
        ],
        risk_factors=[
            "Queda abrupta no preço do barril de petróleo tipo Brent.",
            "Interferência política na política de preços e retenção de caixa.",
            "Mudança brusca na estratégia de alocação de capital para energias renováveis de baixo retorno."
        ]
    ),
    "WEGE3": InvestmentThesis(
        ticker="WEGE3",
        company_name="WEG S.A.",
        pillars=[
            ThesisPillar(
                title="Crescimento Orgânico Consistente",
                description="Manutenção de altas taxas de crescimento orgânico em todos os mercados, com expansão contínua da capacidade fabril global.",
            ),
            ThesisPillar(
                title="Margens Elevadas e Estáveis",
                description="Estabilidade do ROIC em patamares próximos a 30% e manutenção da margem EBITDA histórica, sustentada por ganhos de eficiência.",
            )
        ],
        risk_factors=[
            "Desaceleração severa na economia global industrial.",
            "M&A transformacional que traga alto endividamento ou pressão nas margens de curto prazo.",
            "Guerra de preços com competidores asiáticos em motores elétricos."
        ]
    ),
    "ITUB4": InvestmentThesis(
        ticker="ITUB4",
        company_name="Itaú Unibanco Holding S.A.",
        pillars=[
            ThesisPillar(
                title="Rentabilidade Premium Recorrente",
                description="Manutenção de ROE sistematicamente acima de 20%, evidenciando eficiência e poder de precificação.",
            ),
            ThesisPillar(
                title="Controle de Qualidade de Ativos",
                description="Controle rigoroso da inadimplência (NPL), mantendo o custo de crédito estabilizado mesmo em cenários de juros altos.",
            )
        ],
        risk_factors=[
            "Deterioração macroeconômica abrupta gerando explosão de inadimplência.",
            "Mudanças regulatórias (ex: limites de juros no rotativo ou mudanças estruturais em cartões).",
            "Perda agressiva de market share para fintechs em linhas de alta rentabilidade."
        ]
    ),
    "VALE3": InvestmentThesis(
        ticker="VALE3",
        company_name="Vale S.A.",
        pillars=[
            ThesisPillar(
                title="Foco em Minério Premium (Pelotas/Carajás)",
                description="Estratégia de value-over-volume, focando em minério de alta qualidade que garante prêmio de preço constante.",
            ),
            ThesisPillar(
                title="Retorno de Caixa via Dividendos e Recompra",
                description="Geração de fluxo de caixa livre forte usado quase integralmente para dividendos robustos e programas de recompra de ações agressivos.",
            )
        ],
        risk_factors=[
            "Queda prolongada na demanda de aço da China devido a crise imobiliária.",
            "Novos desastres ambientais envolvendo barragens de rejeitos.",
            "Intervenção governamental na sucessão do CEO causando instabilidade na governança."
        ]
    )
}

def get_thesis_by_ticker(ticker: str) -> Optional[InvestmentThesis]:
    """Retrieve the cached thesis for a given ticker."""
    return _THESES_DB.get(ticker.upper())
