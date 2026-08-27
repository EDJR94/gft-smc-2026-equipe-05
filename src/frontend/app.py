import os
import json
import time
import requests
import streamlit as st

API_URL = os.environ.get("BACKEND_URL", "http://localhost:8080/analyze")

st.set_page_config(
    page_title="SMC Thesis Monitor",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Estilo Clean & Minimalista
st.markdown("""
<style>
    /* Estilo geral */
    .main {
        background-color: #f8f9fa;
    }
    .stApp {
        max-width: 1200px;
        margin: 0 auto;
    }
    
    /* Card de Alerta */
    .alert-card {
        background: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 12px;
        padding: 1.5rem;
        margin-bottom: 1.5rem;
        box-shadow: 0 2px 4px rgba(0,0,0,0.04);
        transition: transform 0.2s ease, box-shadow 0.2s ease;
    }
    .alert-card:hover {
        box-shadow: 0 4px 12px rgba(0,0,0,0.08);
    }
    
    /* Badges de Severidade */
    .badge {
        display: inline-block;
        padding: 0.25rem 0.75rem;
        border-radius: 9999px;
        font-size: 0.85rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }
    .badge-MUITO_ALTO { background-color: #fee2e2; color: #dc2626; border: 1px solid #fecaca; }
    .badge-ALTO { background-color: #ffedd5; color: #ea580c; border: 1px solid #fed7aa; }
    .badge-MEDIO { background-color: #fef9c3; color: #ca8a04; border: 1px solid #fef08a; }
    .badge-BAIXO { background-color: #e0f2fe; color: #0284c7; border: 1px solid #bae6fd; }
    .badge-NEUTRO { background-color: #dcfce7; color: #16a34a; border: 1px solid #bbf7d0; }

    .ticker-badge {
        background-color: #f1f5f9;
        color: #334155;
        font-weight: 700;
        padding: 0.25rem 0.6rem;
        border-radius: 6px;
        font-size: 0.9rem;
        border: 1px solid #cbd5e1;
    }

    /* Blocos de Comparação lado a lado */
    .compare-box {
        background-color: #f8fafc;
        border: 1px solid #e2e8f0;
        border-radius: 8px;
        padding: 1rem;
        height: 100%;
    }
    .compare-title {
        font-size: 0.85rem;
        font-weight: 700;
        text-transform: uppercase;
        color: #64748b;
        margin-bottom: 0.5rem;
    }
</style>
""", unsafe_allow_html=True)

# Carregar Massa de Testes
massa_path = os.path.join(os.path.dirname(__file__), "..", "..", "tests", "data", "massa_testes.json")
try:
    with open(massa_path, "r", encoding="utf-8") as f:
        massa_testes = json.load(f)["test_cases"]
except Exception:
    massa_testes = []

# Sidebar Simples com Carteira Monitorada
with st.sidebar:
    st.markdown("### 🏢 Carteira Monitorada")
    st.caption("Ativos acompanhados pelo Agente:")
    st.markdown("""
    - **PETR4** · *Petrobras*
    - **WEGE3** · *WEG S.A.*
    - **ITUB4** · *Itaú Unibanco*
    - **VALE3** · *Vale S.A.*
    """)
    st.divider()
    st.caption("Powered by **Google ADK & Vertex AI**")

# Cabeçalho Principal
st.title("⚡ SMC Thesis Monitor")
st.markdown("Monitoramento autônomo de teses de investimento em tempo real via **Google ADK & Vertex AI**.")

st.markdown("")

# Sessão de Controle / Simulação
col_btn, col_info = st.columns([1, 2])

with col_btn:
    simular = st.button("🚀 Simular Ingestão de Notícias (Cloud Storage / PubSub)", type="primary", use_container_width=True)

with col_info:
    if st.button("🧹 Limpar Painel", use_container_width=False):
        st.session_state["alerts_history"] = []
        st.rerun()

# Inicializar estado se necessário
if "alerts_history" not in st.session_state:
    st.session_state["alerts_history"] = []

# Execução da Simulação
if simular:
    st.session_state["alerts_history"] = []
    progress_bar = st.progress(0, text="Iniciando fluxo de eventos do Cloud Storage...")
    
    total = len(massa_testes)
    
    for idx, cenario in enumerate(massa_testes):
        ticker = cenario["ticker"]
        news_text = cenario["news_text"]
        desc = cenario["description"]
        
        progress_bar.progress((idx + 1) / total, text=f"📥 [{idx+1}/{total}] Ingerindo fato relevante de **{ticker}** ({desc})...")
        
        try:
            res = requests.post(API_URL, json={"ticker": ticker, "news_text": news_text}, timeout=60)
            if res.status_code == 200:
                data = res.json()
                if data.get("status") == "success" and data.get("result"):
                    result = data["result"]
                    st.session_state["alerts_history"].append({
                        "ticker": ticker,
                        "description": desc,
                        "news_text": news_text,
                        "severity": result.get("severity", "NEUTRO"),
                        "rationale": result.get("rationale", ""),
                        "affected_pillar": result.get("affected_pillar", "Pilar Geral"),
                        "quotes_from_thesis": result.get("quotes_from_thesis", []),
                        "quotes_from_news": result.get("quotes_from_news", [])
                    })
        except Exception as e:
            st.error(f"Erro ao processar {ticker}: {str(e)}")
            
    progress_bar.empty()
    st.success(f"✨ Simulação concluída! {len(st.session_state['alerts_history'])} eventos processados pelo Agente.")

st.divider()

# Exibição dos Alertas
st.subheader("📬 Feed de Divergências e Alertas")

alerts = st.session_state.get("alerts_history", [])

if not alerts:
    st.info("Nenhuma notícia processada ainda. Clique no botão **'🚀 Simular Ingestão de Notícias'** acima para iniciar o fluxo.")
else:
    for idx, alert in enumerate(alerts):
        sev = alert["severity"]
        sev_label = sev.replace("_", " ")
        
        with st.container():
            st.markdown(f"""
            <div class="alert-card">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.75rem;">
                    <div>
                        <span class="ticker-badge">{alert['ticker']}</span>
                        <span style="font-weight: 600; font-size: 1.1rem; margin-left: 0.5rem; color: #1e293b;">{alert['description']}</span>
                    </div>
                    <span class="badge badge-{sev}">{sev_label}</span>
                </div>
                <div style="font-size: 1rem; color: #334155; margin-bottom: 1.25rem; line-height: 1.6;">
                    <b>Diagnóstico do Agente:</b> {alert['rationale']}
                </div>
            </div>
            """, unsafe_allow_html=True)
            
            # Comparativo Tese vs Fato Relevante para checagem manual
            col1, col2 = st.columns(2)
            
            with col1:
                st.markdown("**📜 Tese de Investimento (Cadastrada)**")
                st.info(f"**Pilar Impactado:** {alert['affected_pillar']}")
                if alert['quotes_from_thesis']:
                    st.caption("Trecho da Tese:")
                    for q in alert['quotes_from_thesis']:
                        st.markdown(f"> *\"{q}\"*")
            
            with col2:
                st.markdown("**📰 Fato Relevante Recebido**")
                st.warning(alert['news_text'])
                if alert['quotes_from_news']:
                    st.caption("Evidência Extraída pelo Agente:")
                    for q in alert['quotes_from_news']:
                        st.markdown(f"> *\"{q}\"*")
            
            st.markdown("<br>", unsafe_allow_html=True)
            st.divider()
