# Planejamento Estratégico Definitivo: Agente IA de Mercado de Capitais

Este plano detalha a construção do **Agente Monitor de Divergência de Teses**, projetado para uma competição com prazo de 1 mês. O foco está na robustez analítica, simplicidade na interface e altíssima credibilidade dos dados (sem parecer um cenário fabricado).

## 1. Visão Geral do Produto e Decisões Estratégicas

*   **A "Máquina do Tempo" (Backtest Histórico):** A apresentação não dependerá de notícias do dia. Usaremos teses de investimento reais (extraídas de relatórios de casas de research do passado) cruzadas com Fatos Relevantes históricos da CVM. O LLM fará o cruzamento e a geração do alerta **ao vivo** durante a demonstração, provando sua capacidade em tempo real.
*   **A "Workstation do Analista" (Interface):** Desenvolvida em **Streamlit**. Será uma "Caixa de Entrada Inteligente" (Alert Inbox) contendo as empresas monitoradas e os alertas classificados por risco, com visão lado a lado (Fato Novo vs. Tese Afetada).
*   **Sistema de Severidade (5 Níveis):** Em vez de um score abstrato de 0-100, o agente classificará a divergência em 5 categorias acionáveis: 🔴 *Muito Alto*, 🟠 *Alto*, 🟡 *Médio*, 🔵 *Baixo*, e 🟢 *Muito Baixo/Neutro*.
*   **Fora de Escopo (MVP):** Chat interativo com o agente (ficará listado como evolução futura no roadmap).

## 2. Cenários de Demonstração (Casos Históricos Reais)

Para a banca, provaremos o sistema em 4 cenários baseados no passado da B3:

| Cenário (Severidade) | Ativo | Input 1: Tese Histórica Pública | Input 2: Fato Relevante Histórico | Comportamento do Agente ao Vivo |
| :--- | :--- | :--- | :--- | :--- |
| **1. Quebra de Tese Crítica** (🔴 Muito Alto) | `PETR4` | *Tese:* Alto pagamento de dividendos extraordinários; disciplina rígida de capital (Ex: Relatórios de fev/2024). | *Fato Relevante:* Conselho retém 100% dos dividendos extraordinários. | O agente aponta violação direta do pilar central e sugere reavaliação imediata da ação. |
| **2. M&A Transformacional** (🟠 Alto) | `WEGE3` | *Tese:* Crescimento orgânico e estabilidade histórica de margens de 18%. | *Fato Relevante:* Compra da área de motores da Regal Rexnord por US$ 400M. | O agente identifica impacto de curto prazo no endividamento/margem e mudança tática, exigindo revisão do analista. |
| **3. Confirmação / Reforço** (🟢 Neutro) | `ITUB4` | *Tese:* Controle de inadimplência e digitalização eficiente. | *Notícia/Resultado:* Balanço do trimestre confirmando ROE de 21% e NPL estável. | O agente classifica como reforço da tese. Vai para a inbox apenas como *Log Informativo*. |
| **4. Ruído / Boato** (🔵 Baixo) | `VALE3` | *Tese:* Foco em minério premium. | *Notícia da Mídia:* Rumor sobre troca de diretoria sem fonte oficial. | Filtrado pelo agente como rumor sem base material no momento. |

## 3. Arquitetura do Sistema

### Fluxo de Dados e Processamento
1.  **Repositório de Teses (Base de Conhecimento):** Um arquivo estruturado (JSON/YAML) com as premissas de empresas (Pilares, Riscos, Gatilhos).
2.  **Motor de Simulação (O Injetor):** Um script que, com 1 clique no Streamlit, dispara um texto bruto da CVM/Notícia.
3.  **Processamento LLM (Pipeline de Avaliação):**
    *   **Passo 1 (Materialidade):** O modelo avalia se a notícia tem materialidade financeira.
    *   **Passo 2 (Divergência):** Cruza a notícia material com os pilares da tese cadastrada para aquela empresa.
    *   **Passo 3 (Output Estruturado):** Gera o JSON com Severidade, Pilar Afetado, Racional e Citações Exatas.
4.  **Frontend (Streamlit):** Consome o JSON gerado e exibe visualmente na *Inbox de Alertas*.

### Estrutura do Json do Alerta (Output do LLM)
```json
{
  "ticker": "PETR4",
  "severidade": "MUITO ALTO",
  "pilar_afetado": "Distribuição de dividendos extraordinários recorrentes",
  "racional_agente": "A decisão de reter 100% da reserva estatutária anula a premissa de yield elevado de curto prazo que ancorava o valuation da empresa.",
  "citacao_fato": "O CA propôs que 100% do saldo restante, equivalente a R$ 43,9 bilhões, seja destinado à reserva de remuneração do capital...",
  "citacao_tese": "Expectativa de pagamento de proventos equivalentes a 100% do FCF."
}
```

## 4. Cronograma de Execução (4 Semanas)

### Semana 1: Fundação de Dados e Modelagem de Prompts
*   Mapear os 4 cenários reais (procurar relatórios antigos e Fatos Relevantes exatos).
*   Estruturar o JSON das teses e o JSON desejado como output.
*   Desenvolver os prompts (Usar *Structured Outputs* com a API do Google Gemini).

### Semana 2: Core do Agente e Backend
*   Desenvolver o orquestrador Python que recebe a notícia, injeta a tese junto no prompt, bate na API do LLM e devolve a resposta estruturada.
*   Tratamento de exceções e timeouts da API.

### Semana 3: Interface no Streamlit
*   Criar o layout base: Menu lateral com carteira de ativos e painel central para o feed de alertas.
*   Implementar cartões dinâmicos com cores baseadas no nível de severidade (ex: vermelho para *Muito Alto*).
*   Adicionar botões de ação para o analista (Aceitar/Descartar alerta).

### Semana 4: Polimento e Roteiro da Demonstração
*   Refinamento visual e revisão dos prompts para garantir 100% de consistência nas classificações.
*   Testes de fluxo para a gravação do vídeo e demonstração ao vivo para a banca.

## 5. Plano de Validação (User Review Required)
## 6. Refatoração Estrutural (Clean Architecture)

Para elevar a qualidade do projeto a um nível profissional (Software Engineering Best Practices), reestruturaremos o diretório `src/` modularizando as responsabilidades.

### User Review Required
> [!IMPORTANT]
> **Aprovação da Nova Arquitetura**
> A refatoração mudará a localização dos arquivos e atualizará os scripts de inicialização (`run_demo.sh` e `deploy_gcp.sh`). Confirme se a estrutura abaixo está de acordo com o esperado antes de eu executar os comandos de movimentação de pastas.

### Estrutura Proposta (`src/`)

A organização atual plana (todos os scripts juntos) será migrada para:

*   **`src/api/`** (Camada de Entrega / Interfaces Externas)
    *   `main.py`: O servidor FastAPI, expondo apenas as rotas (`/analyze`, `/auto-analyze`, `/pubsub`).
*   **`src/core/`** (Regras de Domínio e Configurações)
    *   `models.py`: Schemas Pydantic (Entidades do Domínio).
    *   `config.py`: Centralização do carregamento de variáveis de ambiente (`.env`).
*   **`src/agents/`** (Lógica de IA e Orquestração)
    *   `orchestrator.py`: O antigo `agent.py` renomeado, responsável por coordenar os sub-agentes do ADK.
    *   `tools.py`: Ferramentas autônomas isoladas (ex: integração com o Google Search Grounding).
    *   `prompts.py`: Centralização de todos os textos e instruções (separando texto de código).
*   **`src/data/`** (Camada de Dados)
    *   `repository.py`: Nosso banco de dados mockado, isolado do resto do sistema.
*   **`src/frontend/`** (Interface do Usuário)
    *   `app.py`: Interface Streamlit, que consome puramente a API.
*   **`tests/`** (Mover para fora do `src/` seguindo o padrão Python)
    *   Moveremos `test_backend.py`, `test_all_scenarios.py` e `test_phase1.py` para uma pasta raiz `/tests/`.

### Plano de Verificação
- Garantir que todos os `imports` foram atualizados para a notação de pacote correta (`from src.core.models import ...`).
- Rodar a suíte de testes (`pytest tests/`) para garantir que nenhuma dependência foi quebrada.
- Rodar o `./run_demo.sh` atualizado e testar o fluxo de ponta a ponta.
