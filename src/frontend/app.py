import os
import json
import time
import requests
import streamlit as st
import concurrent.futures

API_URL = os.environ.get("BACKEND_URL", "http://localhost:8080/analyze")

def get_auth_headers(target_url: str) -> dict:
    headers = {"Content-Type": "application/json"}
    try:
        from google.auth.transport.requests import Request
        import google.oauth2.id_token
        auth_req = Request()
        token = google.oauth2.id_token.fetch_id_token(auth_req, target_url)
        headers["Authorization"] = f"Bearer {token}"
    except Exception:
        pass
    return headers

def escape_markdown(text) -> str:
    """
    Escapa o caractere '$' para '\\$' para evitar que o Streamlit interprete
    valores monetários (como R$ 50,00 ou US$ 400M) como fórmulas matemáticas LaTeX / KaTeX.
    """
    if text is None:
        return ""
    s = str(text)
    s = s.replace(r"\$", "$")
    return s.replace("$", r"\$")

st.set_page_config(
    page_title="TAMY - Neo Medallion",
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

    /* Badges de Status Human-in-the-Loop */
    .badge-status {
        display: inline-block;
        padding: 0.2rem 0.6rem;
        border-radius: 6px;
        font-size: 0.78rem;
        font-weight: 700;
        margin-left: 0.5rem;
        text-transform: uppercase;
        letter-spacing: 0.04em;
    }
    .badge-PENDING_REVIEW { background-color: #fef3c7; color: #b45309; border: 1px solid #fde68a; }
    .badge-ACKNOWLEDGED { background-color: #dcfce7; color: #15803d; border: 1px solid #bbf7d0; }
    .badge-DISMISSED { background-color: #f1f5f9; color: #64748b; border: 1px solid #cbd5e1; }

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

def update_alert_status_api(alert_id: str, new_status: str, notes: str = None) -> bool:
    """Atualiza o status de auditoria humana (HITL) via API."""
    base_url = API_URL.replace("/analyze", "")
    url = f"{base_url}/alerts/{alert_id}/status"
    try:
        headers = get_auth_headers(url)
        res = requests.patch(url, json={"status": new_status, "reviewer_notes": notes}, headers=headers, timeout=25)
        if res.status_code != 200:
            print(f"[HITL] Resposta não-200 da API ({res.status_code}): {res.text}")
        return res.status_code == 200
    except Exception as e:
        print(f"[HITL] Erro ao sincronizar status com API: {e}")
        return False

def load_alerts_from_api(limit: int = 50, retries: int = 2):
    """Carrega o histórico de alertas persistidos no Firestore / Cloud Storage com retry defensivo contra cold starts."""
    base_url = API_URL.replace("/analyze", "")
    url = f"{base_url}/alerts?limit={limit}"
    last_err = None
    for attempt in range(retries):
        try:
            headers = get_auth_headers(url)
            res = requests.get(url, headers=headers, timeout=40)
            if res.status_code == 200:
                data = res.json()
                return data.get("alerts", []), None
            else:
                last_err = f"API retornou status {res.status_code}"
                print(f"[Firestore] Resposta não-200 da API ({res.status_code}): {res.text}")
        except requests.exceptions.Timeout:
            last_err = "Tempo de resposta esgotado (inicialização do backend). Tentando reconectar..."
            print(f"[Firestore] Tentativa {attempt + 1}/{retries} - Timeout de conexão.")
            time.sleep(2)
        except Exception as e:
            last_err = f"Falha de conexão: {e}"
            print(f"[Firestore] Tentativa {attempt + 1}/{retries} - Erro: {e}")
            time.sleep(1)
    return [], last_err

# Carregar Massa de Testes
massa_path = os.path.join(os.path.dirname(__file__), "..", "..", "tests", "data", "massa_testes.json")
try:
    with open(massa_path, "r", encoding="utf-8") as f:
        massa_testes = json.load(f)["test_cases"]
except Exception:
    massa_testes = []

# Cabeçalho Principal
col_title, col_team = st.columns([3, 1])
with col_title:
    st.title("⚡ TAMY - Monitor de Teses e Notícias")
with col_team:
    st.markdown("""
    <div style="text-align: right; padding-top: 1rem;">
        <span style="background: #1e293b; color: #f8fafc; padding: 0.4rem 0.9rem; border-radius: 6px; font-weight: 700; font-size: 0.85rem; letter-spacing: 0.05em; display: inline-block;">
            🏛️ EQUIPE NEO MEDALLION
        </span>
    </div>
    """, unsafe_allow_html=True)

st.markdown("")

def render_alert_detail(alert: dict):
    """Renderiza a visão detalhada de um alerta com governança Human-in-the-Loop."""
    sev = alert.get("severity", "NEUTRO")
    sev_label = sev.replace("_", " ")
    desc = escape_markdown(alert.get("description", "Análise de Fato Relevante"))
    alert_id = str(alert.get("id", ""))
    status = alert.get("status", "PENDING_REVIEW")

    # Adaptar nomenclatura de governança conforme a severidade diagnosticada
    is_risk = sev in ["MUITO_ALTO", "ALTO", "MEDIO"]
    is_critical = sev in ["MUITO_ALTO", "ALTO"]

    if status == "ACKNOWLEDGED":
        if is_critical:
            status_text = "✅ Quebra Confirmada"
        elif sev == "MEDIO":
            status_text = "✅ Risco Validado"
        else:
            status_text = "✅ Diagnóstico Validado (Tese Mantida)"
        status_class = "badge-ACKNOWLEDGED"
    elif status == "DISMISSED":
        if is_risk:
            status_text = "❌ Falso Positivo (Descartado)"
        else:
            status_text = "❌ Diagnóstico Rejeitado"
        status_class = "badge-DISMISSED"
    else:
        status_text = "⏳ Pendente de Revisão"
        status_class = "badge-PENDING_REVIEW"
    
    ticker = escape_markdown(alert.get('ticker', ''))
    rationale = escape_markdown(alert.get('rationale', ''))
    pillar = escape_markdown(alert.get('affected_pillar', 'Não especificado'))
    news_text = escape_markdown(alert.get('news_text', ''))

    st.markdown(f"""
    <div class="alert-card" style="margin-top: 1rem;">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.75rem;">
            <div>
                <span class="ticker-badge" style="font-size: 1.2rem;">{ticker}</span>
                <span style="font-weight: 700; font-size: 1.3rem; margin-left: 0.5rem; color: #0f172a;">{desc}</span>
                <span class="badge-status {status_class}">{status_text}</span>
            </div>
            <span class="badge badge-{sev}" style="font-size: 1rem; padding: 0.5rem 1rem;">{sev_label}</span>
        </div>
        <div style="font-size: 1.1rem; color: #334155; margin-bottom: 0.5rem; line-height: 1.6; padding: 1rem; background: #f8fafc; border-radius: 6px; border-left: 4px solid #94a3b8;">
            <b>Diagnóstico do Agente:</b><br>{rationale}
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    st.markdown("### 🔎 Evidências para Auditoria")
    col_tese, col_fato = st.columns(2)
    
    with col_tese:
        st.markdown("**📜 Tese de Investimento**")
        st.info(f"**Pilar Impactado:** {pillar}")
        if alert.get('quotes_from_thesis'):
            st.caption("Trechos extraídos da tese:")
            for q in alert['quotes_from_thesis']:
                clean_q = escape_markdown(str(q).replace("&nbsp;", " ").replace("\n", " ").strip())
                st.markdown(f"> *\"{clean_q}\"*")
        else:
            st.caption("Nenhum trecho conflitante direto citado.")
    
    with col_fato:
        st.markdown("**📰 Notícia / Fato Relevante**")
        st.warning(news_text)
        sources = alert.get("sources") or []
        if sources:
            st.markdown("🔗 **Fontes e Links da Notícia (Google Search):**")
            for src in sources:
                src_title = escape_markdown(src.get("title") or src.get("domain") or "Artigo de Notícia")
                src_url = src.get("url", "")
                src_domain = src.get("domain", "")
                badge_domain = f" `{src_domain}`" if src_domain else ""
                if src_url:
                    st.markdown(f"- 🌐 [{src_title}]({src_url}){badge_domain}")

    st.markdown("---")
    st.markdown("### 🧑‍💼 Parecer do Analista (Human-in-the-Loop)")

    if is_critical:
        st.caption("O agente diagnosticou potencial **quebra ou impacto severo** na tese. Registre sua validação:")
        btn_ack_text = "✅ Confirmar Quebra de Tese"
        btn_dism_text = "❌ Descartar como Falso Positivo"
        ack_toast = "Quebra de tese confirmada pelo analista."
        dism_toast = "Alerta descartado como falso positivo."
    elif sev == "MEDIO":
        st.caption("O agente identificou **risco moderado ou ruído**. Registre sua validação:")
        btn_ack_text = "✅ Validar Alerta de Risco"
        btn_dism_text = "❌ Descartar como Ruído"
        ack_toast = "Alerta de risco validado pelo analista."
        dism_toast = "Alerta descartado como ruído irrelevante."
    else:
        st.caption("O agente avaliou este evento como **neutro / alinhado com a tese** (sem quebra). Registre sua validação:")
        btn_ack_text = "✅ Validar Diagnóstico (Tese Mantida)"
        btn_dism_text = "❌ Discordar do Diagnóstico"
        ack_toast = "Diagnóstico do agente validado (tese de investimento preservada)."
        dism_toast = "Diagnóstico do agente rejeitado pelo analista."

    analyst_note = st.text_input(
        "Anotação do Analista (opcional):",
        value=alert.get("reviewer_notes") or "",
        key=f"note_input_{alert_id}",
        placeholder="Ex: Alinhamento confirmado com a gestão; manter monitoramento de rotina..."
    )

    col_btn_ack, col_btn_dism, col_space = st.columns([2, 2, 2])
    with col_btn_ack:
        if st.button(btn_ack_text, key=f"btn_hitl_ack_{alert_id}", use_container_width=True):
            note_to_save = analyst_note.strip() or f"Validado pelo analista ({status_text})."
            if alert_id:
                update_alert_status_api(alert_id, "ACKNOWLEDGED", notes=note_to_save)
            alert["status"] = "ACKNOWLEDGED"
            alert["reviewer_notes"] = note_to_save
            st.toast(ack_toast, icon="✅")
            st.rerun()

    with col_btn_dism:
        if st.button(btn_dism_text, key=f"btn_hitl_dism_{alert_id}", use_container_width=True):
            note_to_save = analyst_note.strip() or f"Descartado pelo analista ({status_text})."
            if alert_id:
                update_alert_status_api(alert_id, "DISMISSED", notes=note_to_save)
            alert["status"] = "DISMISSED"
            alert["reviewer_notes"] = note_to_save
            st.toast(dism_toast, icon="ℹ️")
            st.rerun()

    if alert.get("reviewer_notes"):
        st.info(f"📝 **Parecer Registrado do Analista:** {alert['reviewer_notes']}")


# Inicializar estados de sessão
if "current_view" not in st.session_state:
    st.session_state["current_view"] = "feed"
if "selected_idx" not in st.session_state:
    st.session_state["selected_idx"] = None
if "live_result" not in st.session_state:
    st.session_state["live_result"] = None
if "current_page" not in st.session_state:
    st.session_state["current_page"] = 1

# Carregamento automático na abertura da aplicação
if "alerts_loaded" not in st.session_state:
    loaded, _ = load_alerts_from_api(limit=100)
    st.session_state["alerts_history"] = loaded if loaded else []
    st.session_state["alerts_loaded"] = True
elif "alerts_history" not in st.session_state:
    st.session_state["alerts_history"] = []

tab_simulacao, tab_avulsa = st.tabs(["📊 Simulação em Lote", "🧪 Auditoria Live"])

# ==============================================================================
# ABA 1: SIMULAÇÃO EM LOTE
# ==============================================================================
with tab_simulacao:
    col_btn, col_refresh, col_info = st.columns([1, 1, 2])
    
    with col_btn:
        simular = st.button("🚀 Simular Lote", type="primary", use_container_width=False)
    
    with col_refresh:
        if st.button("🔄 Atualizar Feed", key="btn_atualizar_feed", use_container_width=False):
            with st.spinner("Atualizando alertas do Cloud Firestore..."):
                loaded, err_msg = load_alerts_from_api(limit=100)
                if loaded:
                    st.session_state["alerts_history"] = loaded
                    st.session_state["current_view"] = "feed"
                    st.session_state["selected_idx"] = None
                    st.session_state["current_page"] = 1
                    st.success(f"☁️ {len(loaded)} alertas sincronizados!")
                    st.rerun()
                elif err_msg:
                    st.warning(f"⚠️ {err_msg}")
                else:
                    st.info("Nenhum alerta novo encontrado.")

    with col_info:
        if st.button("🧹 Limpar Painel", key="btn_limpar_simulacao", use_container_width=False):
            st.session_state["alerts_history"] = []
            st.session_state["current_view"] = "feed"
            st.session_state["selected_idx"] = None
            st.session_state["current_page"] = 1
            st.rerun()

    # Execução da Simulação
    if simular:
        st.session_state["current_view"] = "feed"
        st.session_state["selected_idx"] = None
        st.session_state["current_page"] = 1
        
        progress_bar = st.progress(0, text="Iniciando fluxo de eventos do Cloud Storage...")
        total = len(massa_testes)
        new_alerts = []
        
        def fetch_and_process(idx, cenario):
            ticker = cenario["ticker"]
            news_text = cenario["news_text"]
            desc = cenario["description"]
            try:
                headers = get_auth_headers(API_URL)
                res = requests.post(API_URL, json={"ticker": ticker, "news_text": news_text}, headers=headers, timeout=60)
                if res.status_code == 200:
                    data = res.json()
                    if data.get("status") == "success" and data.get("result"):
                        result = data["result"]
                        alert_meta = data.get("alert") or {}
                        return {
                            "id": alert_meta.get("id") or f"alert_{idx}",
                            "ticker": ticker,
                            "description": desc,
                            "news_text": news_text,
                            "severity": result.get("severity", "NEUTRO"),
                            "rationale": result.get("rationale", ""),
                            "affected_pillar": result.get("affected_pillar", "Pilar Geral"),
                            "quotes_from_thesis": result.get("quotes_from_thesis", []),
                            "status": alert_meta.get("status", "PENDING_REVIEW"),
                            "created_at": alert_meta.get("created_at", ""),
                            "order_idx": idx
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
                        new_alerts.append(res)
                        
        new_alerts.sort(key=lambda x: x.get("order_idx", 0))
        
        # Sincronizar com o banco para manter os alertas anteriores junto com os novos
        loaded, _ = load_alerts_from_api(limit=100)
        if loaded:
            st.session_state["alerts_history"] = loaded
        else:
            existing = [a for a in st.session_state.get("alerts_history", []) if a.get("id") not in {n.get("id") for n in new_alerts}]
            st.session_state["alerts_history"] = new_alerts + existing

        st.session_state["current_page"] = 1
        progress_bar.empty()
        st.success(f"✨ Simulação concluída! {len(new_alerts)} novos eventos processados e integrados ao histórico.")

    st.divider()
    alerts = st.session_state["alerts_history"]

    # FEED DE ALERTAS COM PAGINAÇÃO (10 POR PÁGINA)
    if st.session_state["current_view"] == "feed":
        st.subheader("📬 Alertas Gerados")
        
        if not alerts:
            st.info("Nenhum Alerta no momento. Clique em 'Simular Lote' ou em 'Atualizar Feed'.")
        else:
            col_filt1, col_filt2 = st.columns([1, 2])
            with col_filt1:
                filtro_sev = st.selectbox("Filtrar por Risco:", ["TODOS", "MUITO_ALTO", "ALTO", "MEDIO", "BAIXO", "NEUTRO"], key="filtro_simulacao")

            filtered_alerts = [
                a for a in alerts 
                if filtro_sev == "TODOS" or a.get("severity") == filtro_sev
            ]
            
            PAGE_SIZE = 10
            total_alerts = len(filtered_alerts)
            total_pages = max(1, (total_alerts + PAGE_SIZE - 1) // PAGE_SIZE)
            
            if st.session_state.get("last_filtro") != filtro_sev:
                st.session_state["last_filtro"] = filtro_sev
                st.session_state["current_page"] = 1
                
            if st.session_state["current_page"] > total_pages:
                st.session_state["current_page"] = 1
                
            start_idx = (st.session_state["current_page"] - 1) * PAGE_SIZE
            end_idx = min(start_idx + PAGE_SIZE, total_alerts)
            page_alerts = filtered_alerts[start_idx:end_idx]

            with col_filt2:
                st.markdown(
                    f"<div style='margin-top: 1.8rem; font-size: 0.9rem; color: #64748b; text-align: right;'>"
                    f"Total: <b>{total_alerts}</b> alertas &nbsp;•&nbsp; Página <b>{st.session_state['current_page']}</b> de <b>{total_pages}</b> (10 por página)"
                    f"</div>",
                    unsafe_allow_html=True
                )
                
            for alert in page_alerts:
                sev = alert["severity"]
                sev_label = sev.replace("_", " ")
                status = alert.get("status", "PENDING_REVIEW")
                if status == "ACKNOWLEDGED":
                    if sev in ["MUITO_ALTO", "ALTO"]:
                        status_text = "✅ Quebra Validada"
                    elif sev == "MEDIO":
                        status_text = "✅ Risco Validado"
                    else:
                        status_text = "✅ Validado (Neutro)"
                    status_class = "badge-ACKNOWLEDGED"
                elif status == "DISMISSED":
                    status_text = "❌ Descartado"
                    status_class = "badge-DISMISSED"
                else:
                    status_text = "⏳ Pendente"
                    status_class = "badge-PENDING_REVIEW"

                with st.container():
                    col_info, col_btn = st.columns([4, 1])
                    with col_info:
                        card_ticker = escape_markdown(alert.get('ticker', ''))
                        card_desc = escape_markdown(alert.get('description', ''))
                        st.markdown(f"""
                        <div style="padding: 1rem; background: #ffffff; border: 1px solid #e2e8f0; border-radius: 8px; margin-bottom: 0.5rem; display: flex; align-items: center; justify-content: space-between;">
                            <div>
                                <span class="ticker-badge">{card_ticker}</span>
                                <span style="font-weight: 600; margin-left: 0.5rem; color: #1e293b;">{card_desc}</span>
                                <span class="badge-status {status_class}">{status_text}</span>
                            </div>
                            <span class="badge badge-{sev}">{sev_label}</span>
                        </div>
                        """, unsafe_allow_html=True)
                    with col_btn:
                        st.markdown("<div style='margin-top: 1rem;'></div>", unsafe_allow_html=True)
                        if st.button("Ver Auditoria 🔍", key=f"btn_detalhe_{alert['id']}", use_container_width=True):
                            st.session_state["selected_idx"] = alert["id"]
                            st.session_state["current_view"] = "details"
                            st.rerun()

            # Controles de Paginação
            if total_pages > 1:
                st.markdown("<div style='margin-top: 1rem;'></div>", unsafe_allow_html=True)
                col_prev, col_page_info, col_next = st.columns([1, 2, 1])
                with col_prev:
                    if st.button("⬅️ Anterior", disabled=(st.session_state["current_page"] <= 1), key="btn_page_prev", use_container_width=True):
                        st.session_state["current_page"] -= 1
                        st.rerun()
                with col_page_info:
                    st.markdown(
                        f"<div style='text-align: center; font-size: 0.95rem; color: #475569; padding-top: 0.4rem;'>"
                        f"Exibindo <b>{start_idx + 1}-{end_idx}</b> de <b>{total_alerts}</b> alertas"
                        f"</div>",
                        unsafe_allow_html=True
                    )
                with col_next:
                    if st.button("Próxima ➡️", disabled=(st.session_state["current_page"] >= total_pages), key="btn_page_next", use_container_width=True):
                        st.session_state["current_page"] += 1
                        st.rerun()

    # DETALHES DO ALERTA
    elif st.session_state["current_view"] == "details":
        alert = next((a for a in alerts if a["id"] == st.session_state["selected_idx"]), None)
        
        if st.button("⬅ Voltar para o Feed", key="btn_voltar_feed"):
            st.session_state["current_view"] = "feed"
            st.session_state["selected_idx"] = None
            st.rerun()
            
        if alert:
            render_alert_detail(alert)

# ==============================================================================
# ABA 2: AUDITORIA AVULSA (LIVE / CUSTOM NEWS)
# ==============================================================================
with tab_avulsa:
    st.subheader("🧪 Testar Notícia ao Vivo")
    col_t1, col_t2 = st.columns([1, 2])
    with col_t1:
        custom_ticker = st.text_input("Ticker do Ativo (ex: PETR4, VALE3, ITUB4, WEGE3):", value="PETR4").strip().upper()
        st.caption("📌 Teses cadastradas: `PETR4`, `VALE3`, `WEGE3`, `ITUB4`, `NU`, `AMER3`")

    with col_t2:
        st.markdown("<div style='margin-top: 1.8rem;'></div>", unsafe_allow_html=True)
        buscar_google = st.button("🌐 Buscar Últimas Notícias via Google Grounding", key="btn_google_grounding")

    auto_url = API_URL.replace("/analyze", "/auto-analyze")

    if buscar_google and custom_ticker:
        with st.spinner(f"🔍 Consultando Google Search Grounding para {custom_ticker}..."):
            try:
                headers = get_auth_headers(auto_url)
                res = requests.post(auto_url, json={"ticker": custom_ticker}, headers=headers, timeout=60)
                if res.status_code == 200:
                    data = res.json()
                    news_found = data.get("news_found", "")
                    sources = data.get("sources", [])
                    result = data.get("result")
                    alert_meta = data.get("alert") or {}
                    has_thesis = data.get("has_thesis", True)
                    covered_tickers = data.get("covered_tickers", [])
                    
                    if not has_thesis:
                        st.session_state["live_result"] = None
                        cov_str = ", ".join(covered_tickers) if covered_tickers else "PETR4, VALE3, WEGE3, ITUB4, NU, AMER3"
                        st.warning(
                            f"⚠️ **Ativo Fora de Cobertura ({custom_ticker})**\n\n"
                            f"Nenhuma tese de investimento encontrada no repositório para o ticker **{custom_ticker}**.\n\n"
                            f"O **TAMY (Neo Medallion)** audita divergências estritamente contra premissas de teses cadastradas pelo time de Equity Research.\n\n"
                            f"📌 **Ativos com Teses Cobertas:** `{cov_str}`"
                        )
                        if news_found:
                            with st.expander(f"📰 Notícia Localizada via Google Search ({custom_ticker})", expanded=True):
                                st.write(news_found)
                        if sources:
                            st.markdown("🔗 **Fontes e Links da Notícia (Google Search):**")
                            for s in sources:
                                s_title = escape_markdown(s.get("title") or s.get("domain") or "Link da Notícia")
                                s_url = s.get("url", "")
                                s_domain = s.get("domain", "")
                                s_badge = f" `[{s_domain}]`" if s_domain else ""
                                if s_url:
                                    st.markdown(f"- 🌐 [{s_title}]({s_url}){s_badge}")
                    elif result:
                        st.session_state["live_result"] = {
                            "id": alert_meta.get("id", f"live_{custom_ticker}"),
                            "ticker": custom_ticker,
                            "description": f"Auditoria Live - Notícia Google Grounding ({custom_ticker})",
                            "news_text": news_found,
                            "sources": sources,
                            "severity": result.get("severity", "NEUTRO"),
                            "rationale": result.get("rationale", ""),
                            "affected_pillar": result.get("affected_pillar", "Pilar Geral"),
                            "quotes_from_thesis": result.get("quotes_from_thesis", []),
                            "status": alert_meta.get("status", "PENDING_REVIEW")
                        }
                    else:
                        st.session_state["live_result"] = None
                        st.info(f"ℹ️ A notícia para **{custom_ticker}** foi avaliada pelo Agente de Triagem como **NÃO MATERIAL** para a tese de investimento.")
                        if news_found:
                            with st.expander(f"📰 Notícia Descartada pela Triagem ({custom_ticker})"):
                                st.write(news_found)
                        if sources:
                            st.markdown("🔗 **Fontes Consultadas no Google Search:**")
                            for s in sources:
                                s_title = escape_markdown(s.get("title") or s.get("domain") or "Link da Notícia")
                                s_url = s.get("url", "")
                                s_domain = s.get("domain", "")
                                s_badge = f" `[{s_domain}]`" if s_domain else ""
                                if s_url:
                                    st.markdown(f"- 🌐 [{s_title}]({s_url}){s_badge}")
                else:
                    st.error(f"Erro na API ({res.status_code}): {res.text}")
            except Exception as e:
                st.error(f"Falha de conexão com a API: {e}")

    custom_news = st.text_area(
        "Ou cole o texto do Fato Relevante / Notícia:",
        height=140,
        placeholder="Cole aqui o texto da notícia corporativa para o agente cruzar com a tese cadastrada..."
    )

    col_act1, col_act2 = st.columns([1, 3])
    with col_act1:
        analisar_custom = st.button("⚡ Analisar Notícia", type="primary", key="btn_analisar_custom")
    with col_act2:
        if st.button("Limpar Resultado", key="btn_limpar_live"):
            st.session_state["live_result"] = None
            st.rerun()

    if analisar_custom and custom_news:
        with st.spinner(f"⚡ Agente TAMY analisando divergências para {custom_ticker}..."):
            try:
                headers = get_auth_headers(API_URL)
                res = requests.post(API_URL, json={"ticker": custom_ticker, "news_text": custom_news}, headers=headers, timeout=60)
                if res.status_code == 200:
                    data = res.json()
                    result = data.get("result")
                    alert_meta = data.get("alert") or {}
                    has_thesis = data.get("has_thesis", True)
                    covered_tickers = data.get("covered_tickers", [])
                    if not has_thesis:
                        st.session_state["live_result"] = None
                        cov_str = ", ".join(covered_tickers) if covered_tickers else "PETR4, VALE3, WEGE3, ITUB4, NU, AMER3"
                        st.warning(
                            f"⚠️ **Ativo Fora de Cobertura ({custom_ticker})**\n\n"
                            f"Nenhuma tese de investimento encontrada no repositório para o ticker **{custom_ticker}**.\n\n"
                            f"O **TAMY (Neo Medallion)** audita divergências estritamente contra premissas de teses cadastradas pelo time de Equity Research.\n\n"
                            f"📌 **Ativos com Teses Cobertas:** `{cov_str}`"
                        )
                    elif result:
                        st.session_state["live_result"] = {
                            "id": alert_meta.get("id", f"live_{custom_ticker}"),
                            "ticker": custom_ticker,
                            "description": f"Auditoria Avulsa ({custom_ticker})",
                            "news_text": custom_news,
                            "severity": result.get("severity", "NEUTRO"),
                            "rationale": result.get("rationale", ""),
                            "affected_pillar": result.get("affected_pillar", "Pilar Geral"),
                            "quotes_from_thesis": result.get("quotes_from_thesis", []),
                            "status": alert_meta.get("status", "PENDING_REVIEW")
                        }
                    else:
                        st.session_state["live_result"] = None
                        st.info("ℹ️ O Agente de Triagem avaliou a notícia como NÃO MATERIAL para a tese de investimento.")
                else:
                    st.error(f"Erro da API ({res.status_code}): {res.text}")
            except Exception as e:
                st.error(f"Falha na comunicação: {e}")

    if st.session_state["live_result"]:
        st.divider()
        st.subheader("📊 Resultado da Auditoria em Tempo Real")
        render_alert_detail(st.session_state["live_result"])


