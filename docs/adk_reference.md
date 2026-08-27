# Referência Oficial: Google Agent Development Kit (ADK)

O **Agent Development Kit (ADK)** é o framework open-source oficial do Google focado em desenvolvimento de agentes de IA *code-first*. Ele foi projetado para facilitar a criação, avaliação e o deploy de sistemas multi-agentes.

## Instalação

```bash
pip install google-adk
```

## Como Criar um Agente (Quickstart)

Com o ADK, você trata o agente como engenharia de software pura. Você define a lógica, as "tools" (ferramentas) e o modelo usando Python.

### 1. Definindo as Ferramentas (Tools)
Ferramentas são simples funções Python tipadas e com *docstrings* claras (o Gemini lê a docstring para entender o que a ferramenta faz).

```python
def consultar_vertex_search(ticker: str, pergunta: str) -> str:
    """Consulta o banco de dados vetorial (Vertex AI Search) para buscar as premissas da tese de investimento."""
    # Lógica de chamada ao Vertex AI Search
    return "A premissa da Petrobras é distribuir 100% dos dividendos."

def realizar_pesquisa_live(query: str) -> str:
    """Usa o Google Search Grounding para buscar notícias quentes do mercado no dia de hoje."""
    # Lógica de integração com o Google Search
    return "Notícia de hoje..."
```

### 2. Criando a Classe do Agente
Você importa a classe `Agent` e vincula as ferramentas a ela.

```python
from google.adk.agents.llm_agent import Agent

agente_divergencia = Agent(
    model='gemini-1.5-pro', # Ou gemini-2.5-pro dependendo da disponibilidade
    name='Agente_Monitor_Teses',
    instruction='''
    Você é um agente sênior de equity research.
    Seu objetivo é ler um Fato Relevante e verificar se ele fere as premissas originais da tese de investimento da empresa.
    Use suas ferramentas para consultar a tese base no banco de dados e as notícias atuais se necessário.
    Classifique a divergência de Muito Baixa a Muito Alta.
    ''',
    tools=[consultar_vertex_search, realizar_pesquisa_live]
)
```

### 3. Executando o Agente
Você invoca o agente passando a notícia (o input).

```python
input_noticia = "O Conselho da Petrobras decidiu reter 100% dos dividendos."
resposta = agente_divergencia.run(input_noticia)
print(resposta)
```

## Benefícios do ADK para o Nosso Projeto
1. **Orquestração Flexível:** Permite criar lógicas de loop ou múltiplos agentes (ex: um agente só pesquisa, outro agente só classifica o risco).
2. **Deploy Agnóstico:** O agente construído via ADK é facilmente envelopado e feito deploy no **Cloud Run**, o que casa perfeitamente com a opção A da nossa arquitetura.
3. **Padrão Oficial do Google:** A banca do Hackathon valoriza absurdamente o uso do ADK, pois mostra adoção do framework oficial focado em agentes.
