import asyncio
import json
from typing import Optional

from google.adk.agents.llm_agent import Agent
from google.adk.runners import InMemoryRunner
from google.genai import types

from src.core.models import TriageResult, DivergenceAlert, InvestmentThesis
from src.agents.prompts import TRIAGE_AGENT_INSTRUCTION, ANALYST_AGENT_INSTRUCTION


def _run_agent(agent: Agent, message: str) -> str:
    """Runs an ADK agent synchronously and returns the last text response."""
    runner = InMemoryRunner(agent=agent, app_name=agent.name)
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
        
    if loop and loop.is_running():
        # This is a hacky way to run async code synchronously when a loop is already running.
        # But wait, better yet, the ADK runner provides a synchronous API for running!
        # Actually `runner.run()` is a sync generator, but `create_session` is async.
        # The safest way is to run it in a new thread, or just use asyncio.run in a thread.
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
    """Extracts a JSON block from LLM text and parses it into a Pydantic model."""
    # Strip markdown code fences if present
    text = raw
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0]
    elif "```" in text:
        text = text.split("```")[1].split("```")[0]
    return model_class.model_validate_json(text.strip())


class ThesisMonitorOrchestrator:
    def __init__(self):
        self.triage_agent = Agent(
            model="gemini-2.5-flash",
            name="TriageAgent",
            instruction=TRIAGE_AGENT_INSTRUCTION,
        )
        self.analyst_agent = Agent(
            model="gemini-2.5-pro",
            name="AnalystAgent",
            instruction=ANALYST_AGENT_INSTRUCTION,
        )

    def fetch_latest_news(self, ticker: str) -> str:
        """Uses Gemini with Google Search Grounding to find the latest material facts."""
        from google import genai
        from google.genai import types
        try:
            client = genai.Client()
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=f"Busque no Google as últimas notícias e fatos relevantes das últimas 48h sobre a empresa {ticker} (B3). Traga apenas o texto bruto dos fatos mais importantes, sem formatação ou conversa, focando em materialidade financeira.",
                config=types.GenerateContentConfig(
                    tools=[types.Tool(google_search=types.GoogleSearch())]
                )
            )
            return response.text
        except Exception as e:
            print(f"Erro na busca automática: {e}")
            return f"Erro ao buscar notícias para {ticker}."

    def process_news(
        self, news_text: str, cached_thesis: Optional[InvestmentThesis] = None
    ) -> Optional[DivergenceAlert]:
        """
        Orchestrates the multi-agent workflow.
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
        print(f"    -> Ticker={triage_result.ticker}, Material={triage_result.is_material}")

        if not triage_result.is_material:
            print("[-] Notícia descartada: sem materialidade financeira.")
            return None

        if not cached_thesis:
            print(f"[-] Ticker '{triage_result.ticker}' sem tese cadastrada. Coverage Filter ativado.")
            return None

        # --- Agente 3: Analyst ---
        print(f"[+] Agente 3: Analisando divergência para {cached_thesis.ticker}...")
        analyst_prompt = f"""
Analyze the following news against the investment thesis and respond ONLY with a JSON object matching this schema:
{json.dumps(DivergenceAlert.model_json_schema(), indent=2)}

INCOMING NEWS:
{news_text}

INVESTMENT THESIS FOR {cached_thesis.ticker} ({cached_thesis.company_name}):
{cached_thesis.model_dump_json(indent=2)}
"""
        raw_analysis = _run_agent(self.analyst_agent, analyst_prompt)
        return _parse_json_response(raw_analysis, DivergenceAlert)
