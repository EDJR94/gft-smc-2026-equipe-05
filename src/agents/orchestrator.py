import src.core.config
import asyncio
import json
import re
from typing import Optional, List, Dict


from google.adk.agents.llm_agent import Agent
from google.adk.runners import InMemoryRunner
from google.genai import types

from src.core.models import TriageResult, DivergenceAlert
from src.agents.prompts import TRIAGE_AGENT_INSTRUCTION, INVESTIGATOR_AGENT_INSTRUCTION, ANALYST_AGENT_INSTRUCTION
from src.data.rag_repository import rag_db

def _run_agent(agent: Agent, message: str) -> str:
    """Runs an ADK agent synchronously and returns the last text response."""
    runner = InMemoryRunner(agent=agent, app_name=agent.name)
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
        
    if loop and loop.is_running():
        import nest_asyncio
        nest_asyncio.apply()
        session = loop.run_until_complete(
            runner.session_service.create_session(app_name=agent.name, user_id="system")
        )
    else:
        session = asyncio.run(runner.session_service.create_session(app_name=agent.name, user_id="system"))
    content = types.Content(role="user", parts=[types.Part(text=message)])
    full_text = ""
    for event in runner.run(
        user_id=session.user_id,
        session_id=session.id,
        new_message=content,
    ):
        if event.content and event.content.parts:
            for part in event.content.parts:
                if hasattr(part, "text") and part.text:
                    full_text += part.text
    return full_text.strip()


def _parse_json_response(raw: str, model_class):
    """Extracts a JSON block from LLM text defensively and parses it into a Pydantic model."""
    text = raw.strip()
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0].strip()
    elif "```" in text:
        text = text.split("```")[1].split("```")[0].strip()

    # 1. Tenta validar o texto tratado diretamente
    try:
        return model_class.model_validate_json(text)
    except Exception:
        pass

    # 2. Fallback defensivo: extrai bloco entre chaves mais externas
    match = re.search(r"(\{.*\})", text, re.DOTALL)
    if match:
        try:
            return model_class.model_validate_json(match.group(1))
        except Exception:
            pass

    # 3. Fallback tolerante com json.loads
    try:
        parsed_dict = json.loads(text)
        return model_class.model_validate(parsed_dict)
    except Exception as e:
        print(f"[Orchestrator] Falha ao processar JSON para {model_class.__name__}: {e}. Conteúdo recebido:\n{raw[:300]}")
        raise



class ThesisMonitorOrchestrator:
    def __init__(self):
        self.triage_agent = Agent(
            model="gemini-2.5-flash",
            name="TriageAgent",
            instruction=TRIAGE_AGENT_INSTRUCTION,
        )
        self.investigator_agent = Agent(
            model="gemini-2.5-flash",
            name="InvestigatorAgent",
            instruction=INVESTIGATOR_AGENT_INSTRUCTION,
        )
        self.analyst_agent = Agent(
            model="gemini-2.5-pro",
            name="AnalystAgent",
            instruction=ANALYST_AGENT_INSTRUCTION,
        )

    def fetch_latest_news_with_sources(self, ticker: str) -> tuple[str, List[Dict[str, str]]]:
        """
        Uses Gemini with Google Search Grounding to find the latest material facts
        and extracts ground-truth web sources (links and titles).
        """
        from google import genai
        from google.genai import types
        try:
            client = genai.Client()
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=f"Busque no Google as últimas notícias e fatos relevantes das últimas 48h sobre a empresa {ticker} (B3). Traga apenas o texto bruto dos fatos mais importantes, focando em materialidade financeira.",
                config=types.GenerateContentConfig(
                    tools=[types.Tool(google_search=types.GoogleSearch())]
                )
            )

            sources: List[Dict[str, str]] = []
            seen_urls = set()

            if response.candidates:
                cand = response.candidates[0]
                meta = getattr(cand, "grounding_metadata", None)
                if meta and getattr(meta, "grounding_chunks", None):
                    for chunk in meta.grounding_chunks:
                        web = getattr(chunk, "web", None)
                        if web and getattr(web, "uri", None):
                            url = web.uri
                            if url not in seen_urls:
                                seen_urls.add(url)
                                title = getattr(web, "title", "") or getattr(web, "domain", "") or "Fonte da Notícia"
                                domain = getattr(web, "domain", "")
                                sources.append({
                                    "title": title,
                                    "url": url,
                                    "domain": domain
                                })

            news_text = response.text or ""
            return news_text, sources[:6]
        except Exception as e:
            print(f"Erro na busca automática com fontes: {e}")
            return f"Erro ao buscar notícias para {ticker}.", []

    def fetch_latest_news(self, ticker: str) -> str:
        """Uses Gemini with Google Search Grounding to find the latest material facts."""
        news_text, _ = self.fetch_latest_news_with_sources(ticker)
        return news_text

    def process_news(self, news_text: str, ticker_hint: Optional[str] = None) -> Optional[DivergenceAlert]:
        """
        Orchestrates the multi-agent RAG workflow.
        Returns a DivergenceAlert if news is material and a thesis exists, otherwise None.
        """
        # --- Agente 1: Triage ---
        print("[+] Agente 1: Iniciando Triagem...")
        triage_prompt = f"""
Analyze the following news and respond ONLY with a JSON object matching this schema:
{json.dumps(TriageResult.model_json_schema(), indent=2)}

NEWS:
{news_text}
"""
        raw_triage = _run_agent(self.triage_agent, triage_prompt)
        triage_result = _parse_json_response(raw_triage, TriageResult)
        
        # Use hint if triage failed to find ticker
        final_ticker = triage_result.ticker or ticker_hint
        print(f"    -> Ticker={final_ticker}, Material={triage_result.is_material}")

        if not triage_result.is_material:
            print("[-] Notícia descartada: sem materialidade financeira.")
            return None

        if not final_ticker:
            print("[-] Ticker não encontrado. Abortando fluxo.")
            return None

        # --- Verificação de Cobertura de Tese ---
        if not rag_db.has_thesis(final_ticker):
            print(f"[-] Ativo fora de cobertura: Nenhuma tese cadastrada para '{final_ticker}'. Abortando divergência.")
            return None

        # --- Agente 2: Investigator (Query Expansion) ---
        print(f"[+] Agente 2: Investigador gerando query de busca para o RAG...")
        investigator_prompt = f"TICKER: {final_ticker}\nNEWS:\n{news_text}"
        search_query = _run_agent(self.investigator_agent, investigator_prompt).strip().strip('"').strip("'")
        print(f"    -> Query Gerada: '{search_query}'")
        
        # --- Busca no RAG (Vertex AI Search / ChromaDB) ---
        print(f"[+] RAG: Buscando contextos para '{final_ticker}'...")
        rag_results = rag_db.search_thesis(ticker=final_ticker, query=search_query, top_k=4)
        
        if not rag_results:
            doc_text = rag_db._find_document_text("", final_ticker)
            if doc_text:
                rag_context = doc_text[:3000]
            else:
                print(f"[-] Nenhuma tese ou contexto encontrado para {final_ticker}. Abortando.")
                return None
        else:
            rag_context_list = []
            for i, r in enumerate(rag_results):
                source = r['metadata'].get('source', 'Unknown')
                rag_context_list.append(f"--- CHUNK {i+1} (Source: {source}) ---\n{r['content']}")
            rag_context = "\n\n".join(rag_context_list)
            print(f"    -> Recuperados {len(rag_results)} chunks de contexto.")

        # --- Agente 3: Analyst ---
        print(f"[+] Agente 3: Analisando divergência para {final_ticker}...")
        analyst_prompt = f"""
Analyze the following news against the retrieved thesis chunks and respond ONLY with a JSON object matching this schema:
{json.dumps(DivergenceAlert.model_json_schema(), indent=2)}

INCOMING NEWS:
{news_text}

RETRIEVED THESIS CONTEXT FOR {final_ticker}:
{rag_context}
"""
        raw_analysis = _run_agent(self.analyst_agent, analyst_prompt)
        
        # O Analyst pode retornar o ticker que ele processou
        result = _parse_json_response(raw_analysis, DivergenceAlert)
        if not result.ticker:
            result.ticker = final_ticker
            
        return result
