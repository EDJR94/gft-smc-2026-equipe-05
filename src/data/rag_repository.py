import os
import re
from typing import List, Dict, Any, Optional
import chromadb
from pypdf import PdfReader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from chromadb.utils import embedding_functions

# Caminhos base
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(BASE_DIR, "data", "tese_investimentos")
DB_DIR = os.path.join(BASE_DIR, ".chroma_db")

# Configurações do Vertex AI Search (Google Cloud)
PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT", "gft-brazil-bu-gcp")
DATA_STORE_ID = os.environ.get("DATA_STORE_ID", "data-store-neomedallion_1789142566980")
LOCATION = os.environ.get("DATA_STORE_LOCATION", "global")
COLLECTION = os.environ.get("DATA_STORE_COLLECTION", "default_collection")


class RAGRepository:
    def __init__(self):
        self.project_id = PROJECT_ID
        self.data_store_id = DATA_STORE_ID
        self.location = LOCATION
        self.collection_name = COLLECTION

        # Sessão autenticada do Google Cloud para o Vertex AI Search
        self._search_session = None

        # ChromaDB (Armazenamento local mantido como fallback transparente)
        self.chroma_client = chromadb.PersistentClient(path=DB_DIR)
        self.embedding_function = embedding_functions.DefaultEmbeddingFunction()
        self.collection = self.chroma_client.get_or_create_collection(
            name="smc_theses",
            embedding_function=self.embedding_function
        )
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1500,
            chunk_overlap=300,
            separators=["\n\n", "\n", ".", " ", ""]
        )

        # Auto-ingestão defensiva em background: não bloqueia o startup nem causa cold start timeouts
        try:
            if self.collection.count() == 0:
                import threading
                print("[RAG] Base local do ChromaDB vazia. Disparando indexação defensiva em background...")
                t = threading.Thread(target=self.ingest_documents, daemon=True)
                t.start()
        except Exception as e:
            print(f"[RAG] Aviso ao inicializar base local do ChromaDB: {e}")

    def get_covered_tickers(self) -> List[str]:
        """Retorna lista ordenada de tickers com teses cadastradas no repositório."""
        covered = set()
        if os.path.exists(DATA_DIR):
            for fname in os.listdir(DATA_DIR):
                if fname.startswith("."):
                    continue
                parts = fname.split("_")
                if parts and len(parts[0]) >= 2:
                    covered.add(parts[0].upper())
        try:
            if self.collection.count() > 0:
                metas = self.collection.get(include=["metadatas"])
                if metas and metas.get("metadatas"):
                    for m in metas["metadatas"]:
                        if m and m.get("ticker") and m["ticker"] not in ("UNKNOWN", ""):
                            covered.add(m["ticker"].upper())
        except Exception:
            pass
        return sorted(list(covered))

    def has_thesis(self, ticker: str) -> bool:
        """Verifica se existe tese de investimento cadastrada para o ticker."""
        if not ticker or ticker == "UNKNOWN":
            return False
        clean_ticker = ticker.strip().upper()
        if clean_ticker in self.get_covered_tickers():
            return True
        doc = self._find_document_text("", clean_ticker)
        return doc is not None and len(doc.strip()) > 0


    def _get_search_session(self):
        """Retorna uma sessão HTTP autenticada via Google Application Default Credentials (ADC)."""
        if self._search_session is None:
            try:
                import google.auth
                from google.auth.transport.requests import AuthorizedSession
                credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
                self._search_session = AuthorizedSession(credentials)
            except Exception as e:
                print(f"[RAG] Aviso: Não foi possível autenticar sessão Vertex AI: {e}")
                self._search_session = False
        return self._search_session if self._search_session is not False else None

    def _clean_snippet_text(self, text: str) -> str:
        """Limpa tags HTML, entidades &nbsp; e espaços excessivos do snippet."""
        if not text:
            return ""
        cleaned = re.sub(r"<[^>]+>", "", text)
        cleaned = cleaned.replace("&nbsp;", " ")
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned

    def _find_document_text(self, source_or_title: str, ticker: str) -> Optional[str]:
        """Localiza e lê o arquivo da tese correspondente no diretório de teses."""
        if not os.path.exists(DATA_DIR):
            return None

        # 1. Tenta pelo nome base direto
        basename = os.path.basename(source_or_title) if source_or_title else ""
        candidates = []
        if basename:
            candidates.append(basename)
            if not basename.endswith(".txt"):
                candidates.append(f"{basename}.txt")
        if ticker and ticker != "UNKNOWN":
            candidates.append(f"{ticker}_tese.txt")
            candidates.append(f"{ticker}.txt")

        for cand in candidates:
            cand_path = os.path.join(DATA_DIR, cand)
            if os.path.isfile(cand_path):
                return self._extract_text_from_file(cand_path)

        # 2. Varre o diretório procurando arquivo correspondente ao ticker
        if ticker and ticker != "UNKNOWN":
            try:
                for fname in os.listdir(DATA_DIR):
                    if ticker.upper() in fname.upper() and fname.lower().endswith(('.txt', '.pdf', '.md')):
                        return self._extract_text_from_file(os.path.join(DATA_DIR, fname))
            except Exception as e:
                print(f"[RAG] Erro ao listar arquivos em {DATA_DIR}: {e}")

        return None

    def _expand_snippet_to_paragraphs(self, doc_text: Optional[str], snippet: str) -> List[str]:
        """
        Dada a tese completa e o snippet retornado pelo Vertex AI Search,
        localiza os parágrafos completos correspondentes, eliminando cortes abruptos e reticências.
        """
        clean_s = self._clean_snippet_text(snippet)
        if not doc_text:
            return [clean_s] if clean_s else []

        # Segmentos significativos separados por reticências
        fragments = [f.strip() for f in clean_s.split("...") if len(f.strip()) >= 12]
        
        # Palavras significativas (>= 4 letras)
        query_words = set([w.lower() for w in re.findall(r"\b[a-zA-ZÀ-ÿ]{4,}\b", clean_s)])

        paragraphs = [p.strip() for p in doc_text.split("\n\n") if p.strip()]
        filtered_paras = [p for p in paragraphs if not (p.upper().startswith("TESE DE INVESTIMENTO:") and len(p) < 80)]
        if not filtered_paras:
            filtered_paras = paragraphs

        scored = []
        for idx, p in enumerate(filtered_paras):
            score = 0
            # Correspondência exata de frases
            for frag in fragments:
                if frag.lower() in p.lower():
                    score += 15
            # Sobreposição de termos-chave
            p_words = set([w.lower() for w in re.findall(r"\b[a-zA-ZÀ-ÿ]{4,}\b", p)])
            overlap = len(query_words.intersection(p_words))
            score += overlap

            if score >= 3:
                scored.append((score, idx, p))

        if not scored:
            return [clean_s]

        scored.sort(key=lambda x: x[0], reverse=True)
        return [item[2] for item in scored[:2]]

    def _search_vertex_ai(self, ticker: str, query: str, top_k: int = 4) -> List[Dict[str, Any]]:
        """Executa busca semântica no Vertex AI Search e expande os trechos para parágrafos completos."""
        session = self._get_search_session()
        if not session or not self.data_store_id:
            return []

        search_query = f"{ticker} {query}".strip()
        url = (
            f"https://discoveryengine.googleapis.com/v1/projects/{self.project_id}/"
            f"locations/{self.location}/collections/{self.collection_name}/"
            f"dataStores/{self.data_store_id}/servingConfigs/default_search:search"
        )
        payload = {
            "query": search_query,
            "pageSize": top_k,
            "contentSearchSpec": {
                "snippetSpec": {"maxSnippetCount": 3}
            }
        }
        headers = {"X-Goog-User-Project": self.project_id}

        try:
            res = session.post(url, json=payload, headers=headers, timeout=15)
            if res.status_code != 200:
                print(f"[RAG] Vertex AI Search HTTP {res.status_code}: {res.text[:200]}")
                return []

            data = res.json()
            formatted_results = []
            seen_texts = set()

            for r in data.get("results", []):
                doc = r.get("document", {})
                struct = doc.get("derivedStructData", {})
                title = struct.get("title", f"Tese {ticker}")
                link = struct.get("link", "")
                source_ident = link or title

                doc_text = self._find_document_text(source_ident, ticker)
                snippets = struct.get("snippets", [])
                if snippets:
                    for s in snippets:
                        raw_snippet = s.get("snippet", "")
                        if not raw_snippet:
                            continue

                        expanded_paragraphs = self._expand_snippet_to_paragraphs(doc_text, raw_snippet)
                        for para in expanded_paragraphs:
                            cleaned_para = para.strip()
                            if cleaned_para and cleaned_para not in seen_texts:
                                seen_texts.add(cleaned_para)
                                formatted_results.append({
                                    "content": cleaned_para,
                                    "metadata": {
                                        "source": source_ident,
                                        "title": title,
                                        "ticker": ticker,
                                        "engine": "vertex_ai_search"
                                    }
                                })

            return formatted_results
        except Exception as e:
            print(f"[RAG] Erro ao consultar Vertex AI Search: {e}")
            return []

    def _search_chroma(self, ticker: str, query: str, top_k: int = 4) -> List[Dict[str, Any]]:
        """Executa busca local no ChromaDB (fallback)."""
        where_filter = {"ticker": ticker} if ticker and ticker != "UNKNOWN" else None
        try:
            results = self.collection.query(
                query_texts=[query],
                n_results=top_k,
                where=where_filter
            )
            formatted_results = []
            if results and results["documents"] and len(results["documents"][0]) > 0:
                for i in range(len(results["documents"][0])):
                    doc = results["documents"][0][i]
                    meta = results["metadatas"][0][i] if results["metadatas"] else {}
                    meta["engine"] = "chromadb_local"
                    formatted_results.append({
                        "content": doc,
                        "metadata": meta
                    })
            return formatted_results
        except Exception as e:
            print(f"[RAG] Erro ao buscar no ChromaDB: {e}")
            return []

    def search_thesis(self, ticker: str, query: str, top_k: int = 4) -> List[Dict[str, Any]]:
        """
        Busca principal via Vertex AI Search (Cloud Native).
        Caso retorne vazio ou falhe, recorre ao ChromaDB local com fallback automático.
        """
        print(f"[RAG] Buscando via Vertex AI Search (DataStore: {self.data_store_id}) para {ticker}...")
        results = self._search_vertex_ai(ticker, query, top_k)
        if results:
            print(f"[RAG] Sucesso no Vertex AI Search: {len(results)} fragmentos recuperados da nuvem.")
            return results

        print("[RAG] Fallback para ChromaDB local...")
        return self._search_chroma(ticker, query, top_k)

    def _extract_text_from_file(self, filepath: str) -> str:
        """Extrai texto de PDFs ou arquivos TXT."""
        ext = filepath.lower().split('.')[-1]
        text = ""
        try:
            if ext == 'pdf':
                reader = PdfReader(filepath)
                for page in reader.pages:
                    text += page.extract_text() + "\n"
            elif ext == 'txt' or ext == 'md':
                with open(filepath, 'r', encoding='utf-8') as f:
                    text = f.read()
        except Exception as e:
            print(f"[RAG] Erro ao extrair {filepath}: {e}")
        return text

    def ingest_documents(self):
        """Lê os documentos locais para o ChromaDB (usado para alimentar a base local)."""
        if not os.path.exists(DATA_DIR):
            return

        files = os.listdir(DATA_DIR)
        existing_docs = self.collection.get(include=["metadatas"])
        existing_sources = set()
        if existing_docs and existing_docs["metadatas"]:
            for meta in existing_docs["metadatas"]:
                if meta and "source" in meta:
                    existing_sources.add(meta["source"])

        new_docs_count = 0
        for filename in files:
            if filename.startswith(".") or not filename.lower().endswith(('.pdf', '.txt', '.md')):
                continue
                
            filepath = os.path.join(DATA_DIR, filename)
            ticker = "UNKNOWN"
            if "PETR4" in filename.upper(): ticker = "PETR4"
            elif "WEG" in filename.upper() or "WEGE3" in filename.upper(): ticker = "WEGE3"
            elif "ITUB4" in filename.upper() or "ITAÚ" in filename.upper(): ticker = "ITUB4"
            elif "VALE3" in filename.upper(): ticker = "VALE3"
            elif "NUBANK" in filename.upper() or "NU" in filename.upper(): ticker = "NU"
            elif "AMERICANAS" in filename.upper() or "AMER3" in filename.upper(): ticker = "AMER3"

            if filename in existing_sources:
                continue

            text = self._extract_text_from_file(filepath)
            if not text.strip():
                continue

            chunks = self.text_splitter.split_text(text)
            ids = [f"{filename}_chunk_{i}" for i in range(len(chunks))]
            metadatas = [{"source": filename, "ticker": ticker, "chunk_index": i} for i in range(len(chunks))]
            self.collection.add(documents=chunks, metadatas=metadatas, ids=ids)
            new_docs_count += len(chunks)

        if new_docs_count > 0:
            print(f"[RAG] {new_docs_count} fragmentos locais indexados no ChromaDB.")


# Instância singleton
rag_db = RAGRepository()
