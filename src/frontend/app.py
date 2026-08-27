import os
import json
import time
import requests
import streamlit as st
import concurrent.futures

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

# Cabeçalho Principal
st.title("⚡ SMC Thesis Monitor")
st.markdown("Monitoramento autônomo de teses de investimento em tempo real via **Google ADK & Vertex AI**.")

st.markdown("")

# Sessão de Controle / Simulação
col_btn, col_info = st.columns([1, 2])

with col_btn:
    simular = st.button("🚀 Simular", type="primary", use_container_width=False)

with col_info:
    if st.button("🧹 Limpar Painel", use_container_width=False):
        st.session_state["alerts_history"] = []
        st.rerun()

# Inicializar estados se necessário
if "alerts_history" not in st.session_state:
    st.session_state["alerts_history"] = []
if "current_view" not in st.session_state:
    st.session_state["current_view"] = "feed"
if "selected_idx" not in st.session_state:
    st.session_state["selected_idx"] = None

# Execução da Simulação
if simular:
    st.session_state["alerts_history"] = []
    st.session_state["current_view"] = "feed"
    st.session_state["selected_idx"] = None
    
    progress_bar = st.progress(0, text="Iniciando fluxo de eventos do Cloud Storage...")
    total = len(massa_testes)
    
    def fetch_and_process(idx, cenario):
        ticker = cenario["ticker"]
        news_text = cenario["news_text"]
        desc = cenario["description"]
        try:
            res = requests.post(API_URL, json={"ticker": ticker, "news_text": news_text}, timeout=60)
            if res.status_code == 200:
                data = res.json()
                if data.get("status") == "success" and data.get("result"):
                    result = data["result"]
                    return {
                        "id": idx,
                        "ticker": ticker,
                        "description": desc,
                        "news_text": news_text,
                        "severity": result.get("severity", "NEUTRO"),
                        "rationale": result.get("rationale", ""),
                        "affected_pillar": result.get("affected_pillar", "Pilar Geral"),
                        "quotes_from_thesis": result.get("quotes_from_thesis", [])
                    }
        except Exception as e:
            return {"error": f"Erro ao processar {ticker}: {str(e)}"}
        return None

    with concurrent.futures.ThreadPoolExecutor(max_workers=min(10, total)) as executor:
        futures = {executor.submit(fetch_and_process, idx, cenario): idx for idx, cenario in enumerate(massa_testes)}
        completed = 0
        for future in concurrent.futures.as_completed(futures):
            completed += 1
            progress_bar.progress(completed / total, text=f"📥 Processando eventos em paralelo... [{completed}/{total}]")
            res = future.result()
            if res:
                if "error" in res:
                    st.error(res["error"])
                else:
                    st.session_state["alerts_history"].append(res)
                    
    # Reordenar para manter a ordem da massa de testes
    st.session_state["alerts_history"].sort(key=lambda x: x["id"])
    
    progress_bar.empty()
    st.success(f"✨ Simulação concluída! {len(st.session_state['alerts_history'])} eventos processados pelo Agente.")

st.divider()

alerts = st.session_state["alerts_history"]

# ==========================================
# VISÃO: FEED DE ALERTAS (MASTER)
# ==========================================
if st.session_state["current_view"] == "feed":
    st.subheader("📬 Feed de Divergências e Alertas")
    
    if not alerts:
        st.info("Nenhum Alerta no momento. Clique em 'Simular' para gerar eventos.")
    else:
        # Filtros
        col_filt1, col_filt2 = st.columns([1, 3])
        with col_filt1:
            filtro_sev = st.selectbox("Filtrar por Risco:", ["TODOS", "MUITO_ALTO", "ALTO", "MEDIO", "BAIXO", "NEUTRO"])
            
        for alert in alerts:
            sev = alert["severity"]
            if filtro_sev != "TODOS" and sev != filtro_sev:
                continue
                
            sev_label = sev.replace("_", " ")
            
            # Renderização de card super limpo
            with st.container():
                col_info, col_btn = st.columns([4, 1])
                with col_info:
                    st.markdown(f"""
                    <div style="padding: 1rem; background: #ffffff; border: 1px solid #e2e8f0; border-radius: 8px; margin-bottom: 0.5rem; display: flex; align-items: center; justify-content: space-between;">
                        <div>
                            <span class="ticker-badge">{alert['ticker']}</span>
                            <span style="font-weight: 600; margin-left: 0.5rem; color: #1e293b;">{alert['description']}</span>
                        </div>
                        <span class="badge badge-{sev}">{sev_label}</span>
                    </div>
                    """, unsafe_allow_html=True)
                with col_btn:
                    st.markdown("<div style='margin-top: 1rem;'></div>", unsafe_allow_html=True)
                    if st.button("Ver Análise Completa 🔍", key=f"btn_detalhe_{alert['id']}", use_container_width=True):
                        st.session_state["selected_idx"] = alert["id"]
                        st.session_state["current_view"] = "details"
                        st.rerun()

# ==========================================
# VISÃO: DETALHES DO ALERTA (DETAIL)
# ==========================================
elif st.session_state["current_view"] == "details":
    alert = next((a for a in alerts if a["id"] == st.session_state["selected_idx"]), None)
    
    if st.button("⬅ Voltar para o Feed"):
        st.session_state["current_view"] = "feed"
        st.session_state["selected_idx"] = None
        st.rerun()
        
    if alert:
        sev = alert["severity"]
        sev_label = sev.replace("_", " ")
        
        st.markdown(f"""
        <div class="alert-card" style="margin-top: 1rem;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.75rem;">
                <div>
                    <span class="ticker-badge" style="font-size: 1.2rem;">{alert['ticker']}</span>
                    <span style="font-weight: 700; font-size: 1.4rem; margin-left: 0.5rem; color: #0f172a;">{alert['description']}</span>
                </div>
                <span class="badge badge-{sev}" style="font-size: 1rem; padding: 0.5rem 1rem;">{sev_label}</span>
            </div>
            <div style="font-size: 1.1rem; color: #334155; margin-bottom: 0.5rem; line-height: 1.6; padding: 1rem; background: #f8fafc; border-radius: 6px; border-left: 4px solid #94a3b8;">
                <b>Diagnóstico do Agente:</b><br>{alert['rationale']}
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        st.markdown("### 🔎 Evidências para Auditoria Manual")
        
        col_tese, col_fato = st.columns(2)
        
        with col_tese:
            st.markdown("**📜 Tese de Investimento (Base)**")
            st.info(f"**Pilar Impactado:** {alert['affected_pillar']}")
            if alert['quotes_from_thesis']:
                st.caption("Trechos extraídos da tese:")
                for q in alert['quotes_from_thesis']:
                    st.markdown(f"> *\"{q}\"*")
        
        with col_fato:
            st.markdown("**📰 Notícia / Fato Relevante (Mercado)**")
            st.warning(alert['news_text'])
