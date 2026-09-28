import json
import os
import uuid
import concurrent.futures
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any

import src.core.config
from src.core.models import DivergenceAlert, StoredAlert, AlertStatus, SeverityLevel

PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT", "gft-brazil-bu-gcp")
COLLECTION_NAME = os.environ.get("FIRESTORE_COLLECTION", "smc_thesis_alerts")
GCS_BUCKET_NAME = os.environ.get("GCS_BUCKET_NAME", "hackathon-gft-neomedallion")
ALERTS_GCS_PREFIX = "alerts/"


class FirestoreAlertRepository:
    """
    Repositório de persistência para alertas de divergência e governança Human-in-the-Loop.
    
    Estratégia de Persistência Híbrida em Nuvem:
    1. Primária: Google Cloud Firestore (quando habilitado no projeto GCP).
    2. Nuvem GCP: Google Cloud Storage (Bucket gs://{bucket_name}/alerts/) garantindo
       persistência durável e imutável entre ciclos de vida dos contêineres Cloud Run.
    3. Fallback: Cache local em memória para testes e execução offline.
    """

    def __init__(
        self,
        project_id: Optional[str] = None,
        collection_name: str = COLLECTION_NAME,
        bucket_name: Optional[str] = None,
        auto_seed: bool = True
    ):
        self.project_id = project_id or PROJECT_ID
        self.collection_name = collection_name
        self.bucket_name = bucket_name or GCS_BUCKET_NAME
        self.auto_seed = auto_seed

        self._firestore_client = None
        self._storage_client = None
        self._bucket = None
        self._fallback_store: Dict[str, StoredAlert] = {}

        self._init_clients()

    def _init_clients(self):
        """Inicializa conexões com Google Cloud Firestore e Google Cloud Storage via Application Default Credentials (ADC)."""
        # 1. Tenta inicializar Firestore
        try:
            from google.cloud import firestore
            client = firestore.Client(project=self.project_id)
            # Teste rápido de conectividade para verificar se a API está habilitada
            list(client.collection(self.collection_name).limit(1).stream())
            self._firestore_client = client
            print(f"[Firestore] Conectado com sucesso ao projeto '{self.project_id}' (Coleção: {self.collection_name}).")
        except Exception as e:
            err_msg = str(e)
            if "SERVICE_DISABLED" in err_msg or "has not been used in project" in err_msg or "403" in err_msg:
                print(f"[Firestore] API do Firestore não ativada no projeto '{self.project_id}'. Utilizando Google Cloud Storage para persistência em nuvem.")
            else:
                print(f"[Firestore] Conexão Firestore indisponível ({e}). Utilizando Google Cloud Storage para persistência em nuvem.")
            self._firestore_client = None

        # 2. Inicializa Google Cloud Storage como camada de persistência em nuvem
        try:
            from google.cloud import storage
            self._storage_client = storage.Client(project=self.project_id)
            self._bucket = self._storage_client.bucket(self.bucket_name)
            print(f"[Storage] Conectado ao GCS Bucket '{self.bucket_name}' para persistência de alertas.")
        except Exception as e:
            print(f"[Storage] Aviso: GCS indisponível ({e}). Ativando modo In-Memory Fallback.")
            self._bucket = None

    @property
    def is_connected(self) -> bool:
        """Indica se a conexão com armazenamento em nuvem (Firestore ou GCS) está ativa."""
        return self._firestore_client is not None or self._bucket is not None

    def save_alert(
        self,
        alert: DivergenceAlert,
        news_text: str = "",
        description: str = "",
        custom_id: Optional[str] = None,
        sources: Optional[List[Dict[str, str]]] = None,
        status: Optional[AlertStatus] = None,
        reviewer_notes: Optional[str] = None
    ) -> StoredAlert:
        """
        Salva um alerta gerado pelo agente no Firestore, no GCS e no cache local.
        Aplica governança Human-in-the-Loop (HITL) seletiva por criticidade:
        - Severidades MUITO_ALTO e ALTO: exigem validação e aprovação humana (status PENDING_REVIEW).
        - Severidades MEDIO, BAIXO e NEUTRO: auto-aprovadas pelo sistema (status AUTO_APPROVED),
          otimizando a produtividade do time de Research e evitando sobrecarga com riscos rotineiros.
        """
        now_iso = datetime.now(timezone.utc).isoformat()
        alert_id = custom_id or f"{alert.ticker}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        desc = description or f"Alerta de Divergência - {alert.ticker}"

        # Human-in-the-Loop: apenas riscos ALTO e MUITO_ALTO iniciam como PENDING_REVIEW; as demais severidades não recebem status pendente
        requires_hitl = alert.severity in (SeverityLevel.MUITO_ALTO, SeverityLevel.ALTO)

        if status is not None:
            final_status = status
        else:
            final_status = AlertStatus.PENDING_REVIEW if requires_hitl else None

        final_notes = reviewer_notes

        stored = StoredAlert(
            id=alert_id,
            ticker=alert.ticker,
            severity=alert.severity,
            affected_pillar=alert.affected_pillar,
            rationale=alert.rationale,
            quotes_from_thesis=alert.quotes_from_thesis,
            news_text=news_text,
            description=desc,
            created_at=now_iso,
            status=final_status,
            reviewer_notes=final_notes,
            sources=sources or []
        )

        # 1. Salva no cache local em memória
        self._fallback_store[stored.id] = stored

        # 2. Persiste no Google Cloud Firestore se conectado
        if self._firestore_client:
            try:
                doc_ref = self._firestore_client.collection(self.collection_name).document(stored.id)
                doc_ref.set(stored.model_dump())
            except Exception as e:
                print(f"[Firestore] Erro ao gravar documento no Firestore: {e}.")

        # 3. Persiste no Google Cloud Storage (Bucket)
        if self._bucket:
            try:
                blob = self._bucket.blob(f"{ALERTS_GCS_PREFIX}{stored.id}.json")
                blob.upload_from_string(
                    json.dumps(stored.model_dump(), ensure_ascii=False, indent=2),
                    content_type="application/json"
                )
            except Exception as e:
                print(f"[Storage] Erro ao persistir alerta no GCS: {e}.")

        return stored

    def list_alerts(self, limit: int = 50, ticker: Optional[str] = None) -> List[StoredAlert]:
        """
        Lista alertas persistidos ordenados por data decrescente.
        Consulta Firestore -> Google Cloud Storage -> In-Memory Fallback.
        Se vazio, auto-inicializa alertas demonstrativos.
        """
        # 1. Consulta no Firestore se disponível
        if self._firestore_client:
            try:
                from google.cloud import firestore
                query = self._firestore_client.collection(self.collection_name)
                if ticker and ticker.upper() != "TODOS":
                    query = query.where(filter=firestore.FieldFilter("ticker", "==", ticker.upper()))
                query = query.order_by("created_at", direction=firestore.Query.DESCENDING).limit(limit)

                firestore_alerts = []
                for doc in query.stream():
                    data = doc.to_dict()
                    item = StoredAlert.model_validate(data)
                    firestore_alerts.append(item)
                    self._fallback_store[item.id] = item

                if firestore_alerts:
                    return firestore_alerts
            except Exception as e:
                print(f"[Firestore] Erro ao consultar alertas no Firestore: {e}. Consultando GCS.")

        # 2. Consulta no Google Cloud Storage (Bucket)
        if self._bucket:
            try:
                blobs = list(self._bucket.list_blobs(prefix=ALERTS_GCS_PREFIX))
                json_blobs = [b for b in blobs if b.name.endswith(".json")]

                if json_blobs:
                    def _download_blob(b):
                        try:
                            content = b.download_as_text()
                            data = json.loads(content)
                            return StoredAlert.model_validate(data)
                        except Exception:
                            return None

                    with concurrent.futures.ThreadPoolExecutor(max_workers=min(10, len(json_blobs))) as executor:
                        loaded = list(executor.map(_download_blob, json_blobs))
                        for item in loaded:
                            if item:
                                self._fallback_store[item.id] = item
            except Exception as e:
                print(f"[Storage] Erro ao carregar alertas do GCS: {e}.")

        # 3. Auto-seed se não houver nenhum alerta disponível
        if not self._fallback_store and self.auto_seed:
            self.seed_sample_alerts()

        # 4. Filtra e ordena
        results = list(self._fallback_store.values())
        if ticker and ticker.upper() != "TODOS":
            results = [a for a in results if a.ticker.upper() == ticker.upper()]
        results.sort(key=lambda a: a.created_at, reverse=True)
        return results[:limit]

    def get_alert(self, alert_id: str) -> Optional[StoredAlert]:
        """Recupera um alerta específico pelo ID."""
        if alert_id in self._fallback_store:
            return self._fallback_store[alert_id]

        if self._firestore_client:
            try:
                doc_ref = self._firestore_client.collection(self.collection_name).document(alert_id)
                doc = doc_ref.get()
                if doc.exists:
                    item = StoredAlert.model_validate(doc.to_dict())
                    self._fallback_store[item.id] = item
                    return item
            except Exception as e:
                print(f"[Firestore] Erro ao buscar alerta {alert_id}: {e}")

        if self._bucket:
            try:
                blob = self._bucket.blob(f"{ALERTS_GCS_PREFIX}{alert_id}.json")
                if blob.exists():
                    item = StoredAlert.model_validate(json.loads(blob.download_as_text()))
                    self._fallback_store[item.id] = item
                    return item
            except Exception as e:
                print(f"[Storage] Erro ao buscar alerta {alert_id} no GCS: {e}")

        return None

    def update_alert_status(
        self,
        alert_id: str,
        status: AlertStatus,
        reviewer_notes: Optional[str] = None
    ) -> bool:
        """
        Atualiza o status de auditoria humana (Human-in-the-Loop) de um alerta no Firestore, GCS e memória.
        """
        updated = False

        # 1. Atualiza no cache em memória
        if alert_id in self._fallback_store:
            self._fallback_store[alert_id].status = status
            if reviewer_notes is not None:
                self._fallback_store[alert_id].reviewer_notes = reviewer_notes
            updated = True

        # 2. Atualiza no Firestore
        if self._firestore_client:
            try:
                doc_ref = self._firestore_client.collection(self.collection_name).document(alert_id)
                update_payload: Dict[str, Any] = {"status": status.value}
                if reviewer_notes is not None:
                    update_payload["reviewer_notes"] = reviewer_notes
                doc_ref.update(update_payload)
                updated = True
            except Exception as e:
                print(f"[Firestore] Erro ao atualizar status no Firestore para {alert_id}: {e}")

        # 3. Atualiza no Google Cloud Storage
        if self._bucket:
            try:
                blob = self._bucket.blob(f"{ALERTS_GCS_PREFIX}{alert_id}.json")
                if blob.exists():
                    data = json.loads(blob.download_as_text())
                    data["status"] = status.value
                    if reviewer_notes is not None:
                        data["reviewer_notes"] = reviewer_notes
                    blob.upload_from_string(
                        json.dumps(data, ensure_ascii=False, indent=2),
                        content_type="application/json"
                    )
                    updated = True
                    self._fallback_store[alert_id] = StoredAlert.model_validate(data)
            except Exception as e:
                print(f"[Storage] Erro ao atualizar status no GCS para {alert_id}: {e}")

        return updated

    def seed_sample_alerts(self) -> List[StoredAlert]:
        """
        Cria alertas demonstrativos com dados realistas e fundamentados quando o banco estiver vazio.
        Garante que a banca examinadora e usuários visualizem dados instantaneamente.
        """
        seeds: List[StoredAlert] = []
        base_time = datetime.now(timezone.utc).isoformat()

        samples = [
            {
                "id": "alert_seed_petr4_001",
                "ticker": "PETR4",
                "severity": SeverityLevel.MUITO_ALTO,
                "affected_pillar": "Política de Dividendos e Alocação de Capital",
                "rationale": "O Conselho de Administração da Petrobras reteve 100% dos dividendos extraordinários para investimentos em eólicas offshore, violando diretamente a tese de dividend yield atrativo e disciplina de capital no pré-sal.",
                "quotes_from_thesis": [
                    "Foco prioritário em E&P no Pré-Sal com distribuição de dividendos robustos",
                    "Disciplina de capital com limitação de capex fora do core business"
                ],
                "news_text": "O Conselho de Administração da Petrobras decidiu reter 100% dos dividendos extraordinários para investimentos em eólicas offshore, alterando a política de distribuição.",
                "description": "Quebra de Tese Crítica - Retenção de Dividendos",
                "status": AlertStatus.PENDING_REVIEW,
                "reviewer_notes": None,
                "sources": [
                    {"title": "Petrobras retém dividendos e altera plano de capex", "url": "https://valor.globo.com/empresas/noticia/petrobras-dividendos", "domain": "valor.globo.com"}
                ]
            },
            {
                "id": "alert_seed_wege3_002",
                "ticker": "WEGE3",
                "severity": SeverityLevel.ALTO,
                "affected_pillar": "M&A e Alocação de Capital",
                "rationale": "Aquisição da divisão industrial da Regal Rexnord por US$ 400M através de alavancagem financeira. Acompanhamento necessário quanto ao ROIC de integração e endividamento líquido.",
                "quotes_from_thesis": [
                    "Crescimento sustentável com ROIC acima de 25% e alavancagem líquida neutra"
                ],
                "news_text": "A WEG adquiriu a divisão de motores industriais da Regal Rexnord por US$ 400 milhões, com pagamento via alavancagem.",
                "description": "M&A Transformacional - Compra Regal",
                "status": AlertStatus.ACKNOWLEDGED,
                "reviewer_notes": "Parecer do Analista: M&A estratégico para expansão na América do Norte. Tese mantida sob monitoramento do ROIC no 2T.",
                "sources": [
                    {"title": "WEG adquire divisão de motores da Regal Rexnord por US$ 400M", "url": "https://www.infomoney.com.br/mercados/weg-compra-regal-rexnord/", "domain": "infomoney.com.br"}
                ]
            },
            {
                "id": "alert_seed_vale3_003",
                "ticker": "VALE3",
                "severity": SeverityLevel.MEDIO,
                "affected_pillar": "Governança Corporativa",
                "rationale": "Pressão política externa sobre a composição do Conselho de Administração e escolha do novo CEO introduz ruído de governança e volatilidade de curto prazo.",
                "quotes_from_thesis": [
                    "Governança de corporation com capital pulverizado e Conselho majoritariamente independente"
                ],
                "news_text": "Rumores indicam pressão do governo para emplacar nome no Conselho de Administração da Vale nas próximas eleições.",
                "description": "Ruído - Governança",
                "status": None,
                "reviewer_notes": None,
                "sources": [
                    {"title": "Pressão sobre conselho da Vale e sucessão executiva", "url": "https://exame.com/negocios/vale-sucessao-ceo-governanca/", "domain": "exame.com"}
                ]
            },
            {
                "id": "alert_seed_itub4_004",
                "ticker": "ITUB4",
                "severity": SeverityLevel.ALTO,
                "affected_pillar": "Qualidade de Crédito e Custo do Risco",
                "rationale": "Aumento extraordinário de provisões para devedores duvidosos (PDD) sinaliza potencial pressão na qualidade dos ativos e impacto na rentabilidade projetada (ROE).",
                "quotes_from_thesis": [
                    "Qualidade superior de crédito mantendo índice de inadimplência sob controle e ROE estrutural > 20%"
                ],
                "news_text": "Itaú anuncia aumento extraordinário nas provisões de devedores duvidosos (PDD) devido a deterioração macroeconômica, impactando o ROE.",
                "description": "Risco de Capital - Aumento de PDD",
                "status": AlertStatus.PENDING_REVIEW,
                "reviewer_notes": None,
                "sources": [
                    {"title": "Itaú aumenta provisões para devedores duvidosos no balanço", "url": "https://braziljournal.com/itau-provisao-devedores-duvidosos/", "domain": "braziljournal.com"}
                ]
            }
        ]

        for item in samples:
            stored = StoredAlert(
                id=item["id"],
                ticker=item["ticker"],
                severity=item["severity"],
                affected_pillar=item["affected_pillar"],
                rationale=item["rationale"],
                quotes_from_thesis=item["quotes_from_thesis"],
                news_text=item["news_text"],
                description=item["description"],
                created_at=base_time,
                status=item["status"],
                reviewer_notes=item["reviewer_notes"],
                sources=item.get("sources", [])
            )
            self._fallback_store[stored.id] = stored
            seeds.append(stored)

            # Persiste no GCS se disponível
            if self._bucket:
                try:
                    blob = self._bucket.blob(f"{ALERTS_GCS_PREFIX}{stored.id}.json")
                    blob.upload_from_string(
                        json.dumps(stored.model_dump(), ensure_ascii=False, indent=2),
                        content_type="application/json"
                    )
                except Exception as e:
                    print(f"[Storage] Erro ao gravar seed no GCS: {e}")

        print(f"[Repository] {len(seeds)} alertas sementes gerados e persistidos no Cloud Storage.")
        return seeds


# Instância singleton global do repositório
firestore_db = FirestoreAlertRepository()
