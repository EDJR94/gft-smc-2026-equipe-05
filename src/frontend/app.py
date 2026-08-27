import os
import streamlit as st
import requests

API_URL = os.environ.get("BACKEND_URL", "http://localhost:8080/analyze")

st.set_page_config(
    page_title="SMC Thesis Monitor",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for Severity Cards
st.markdown("""
<style>
.severity-card {
    padding: 1.5rem;
    border-radius: 8px;
    color: white;
    margin-bottom: 1rem;
    box-shadow: 0 4px 6px rgba(0,0,0,0.1);
}
.severity-MUITO_ALTO { background: linear-gradient(135deg, #d32f2f, #b71c1c); }
.severity-ALTO { background: linear-gradient(135deg, #f57c00, #e65100); }
.severity-MEDIO { background: linear-gradient(135deg, #fbc02d, #f57f17); color: #333; }
.severity-BAIXO { background: linear-gradient(135deg, #1976d2, #0d47a1); }
.severity-NEUTRO { background: linear-gradient(135deg, #388e3c, #1b5e20); }
.metric-box {
    background-color: #f0f2f6;
    padding: 10px;
    border-radius: 5px;
    border-left: 5px solid #000;
    margin-top: 10px;
}
</style>
""", unsafe_allow_html=True)

# Sidebar
with st.sidebar:
    st.image("https://upload.wikimedia.org/wikipedia/commons/thumb/c/c1/Google_%22G%22_logo.svg/120px-Google_%22G%22_logo.svg.png", width=50)
    st.title("Ativos Monitorados")
    st.markdown("---")
    st.markdown("🟢 **PETR4** - Petróleo Brasileiro S.A.")
    st.markdown("🟢 **WEGE3** - WEG S.A.")
    st.markdown("🟢 **ITUB4** - Itaú Unibanco")
    st.markdown("🟢 **VALE3** - Vale S.A.")
    st.markdown("---")
    st.caption("powered by Google Agent Development Kit (ADK) & Vertex AI")

# Main Content
st.title("Caixa de Entrada de Alertas - SMC")
st.markdown("Simule a chegada de um Fato Relevante ou Notícia do mercado para cruzar com a Tese de Investimentos vigente.")

import json

# Carregar massa de testes
massa_path = os.path.join(os.path.dirname(__file__), "..", "..", "tests", "data", "massa_testes.json")
try:
    with open(massa_path, "r", encoding="utf-8") as f:
        massa_testes = json.load(f)["test_cases"]
except Exception:
    massa_testes = []

with st.expander("📝 Injetar Nova Notícia (Manual, Google ou Mock)", expanded=True):
    # ABA 1: Manual ou Automático
    st.markdown("### Busca Livre ou Inserção Manual")
    col1, col2 = st.columns([1, 4])
    with col1:
        ticker_manual = st.selectbox("Ticker Afetado", ["PETR4", "WEGE3", "ITUB4", "VALE3"], key="ticker_manual")
    with col2:
        news_text_manual = st.text_area("Texto da Notícia / Fato Relevante da CVM", height=100, placeholder="Cole aqui o texto do fato relevante ou use a busca automática...")
    
    bcol1, bcol2 = st.columns(2)
    with bcol1:
        submit_manual = st.button("Processar Texto Colado", type="secondary", use_container_width=True)
    with bcol2:
        submit_auto = st.button("🤖 Pesquisar no Google e Analisar (Auto)", type="primary", use_container_width=True)

    st.markdown("---")
    
    # ABA 2: Cenários Mockados
    st.markdown("### 🧪 Simular Casos de Teste da Banca")
    if massa_testes:
        cenarios_dict = {f"{c['ticker']} - {c['description']}": c for c in massa_testes}
        cenario_selecionado = st.selectbox("Escolha um cenário histórico para simular:", list(cenarios_dict.keys()))
        submit_mock = st.button("Executar Cenário Mockado", type="primary", use_container_width=True)
    else:
        submit_mock = False
        st.warning("Massa de testes não encontrada.")

st.markdown("---")
st.subheader("📬 Inbox de Alertas")

if submit_manual or submit_auto or submit_mock:
    is_auto = submit_auto
    
    # Determine the payload based on which button was clicked
    if submit_mock:
        selected_case = cenarios_dict[cenario_selecionado]
        ticker = selected_case["ticker"]
        news_text = selected_case["news_text"]
        msg = f"Agentes simulando cenário mockado para {ticker}..."
    else:
        ticker = ticker_manual
        news_text = news_text_manual
        msg = f"Agente Autônomo buscando notícias para {ticker} no Google..." if is_auto else f"Agentes analisando cruzamento de tese para {ticker}..."

    if not is_auto and not news_text.strip():
        st.warning("Por favor, insira o texto da notícia para a análise manual.")
    else:
        msg = f"Agente Autônomo buscando notícias para {ticker} no Google..." if is_auto else f"Agentes analisando cruzamento de tese para {ticker}..."
        with st.spinner(msg):
            try:
                if is_auto:
                    # Rota de Auto-Busca via Google Search Grounding
                    url = API_URL.replace("/analyze", "/auto-analyze")
                    response = requests.post(url, json={"ticker": ticker})
                else:
                    response = requests.post(API_URL, json={"ticker": ticker, "news_text": news_text})
                    
                if response.status_code == 200:
                    data = response.json()
                    
                    if is_auto and data.get("news_found"):
                        st.info("📰 **Notícia Encontrada pelo Agente no Google:**\n\n" + data["news_found"])
                        
                    if data.get("status") == "success" and data.get("result"):
                        res = data["result"]
                        sev = res.get("severity", "NEUTRO")
                        
                        # Render Severity Card
                        st.markdown(f"""
                        <div class="severity-card severity-{sev}">
                            <h2 style="margin-top:0; color:inherit;">Alerta de Divergência: {ticker}</h2>
                            <h4 style="color:inherit; opacity:0.9;">Severidade: {sev.replace('_', ' ')}</h4>
                            <p style="font-size:1.1em; line-height:1.5;">{res.get('rationale')}</p>
                        </div>
                        """, unsafe_allow_html=True)
                        
                        # Render Side-by-Side Analysis
                        st.markdown("### Evidências da Divergência")
                        col_tese, col_fato = st.columns(2)
                        
                        with col_tese:
                            st.markdown("#### 📜 Pilar da Tese Afetado")
                            st.info(f"**{res.get('affected_pillar', 'Nenhum pilar específico mapeado')}**")
                            for quote in res.get('quotes_from_thesis', []):
                                st.markdown(f"> *\"{quote}\"*")
                                
                        with col_fato:
                            st.markdown("#### 📰 Fato Novo Observado")
                            for quote in res.get('quotes_from_news', []):
                                st.error(f"> *\"{quote}\"*")
                                
                        # Action Buttons
                        st.markdown("<br>", unsafe_allow_html=True)
                        b1, b2, b3 = st.columns([1,1,3])
                        b1.button("✅ Ciente (Arquivar)")
                        b2.button("⚠️ Revisar Tese (Criar Task)")
                        
                    else:
                        st.info("A notícia foi processada, mas não gerou alertas críticos (filtrada pelo agente).")
                else:
                    st.error(f"Erro na API: {response.text}")
            except requests.exceptions.ConnectionError:
                st.error("Falha de conexão com o Backend. O servidor FastAPI (main.py) está rodando na porta 8080?")

# Show empty inbox if no submission
if not submit_manual and not submit_auto and not submit_mock:
    st.caption("Nenhum alerta pendente no momento. As notícias processadas aparecerão aqui se divergirem da tese.")
