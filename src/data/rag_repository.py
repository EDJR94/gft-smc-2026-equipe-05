import os
from typing import List, Dict, Any
import chromadb
from chromadb.config import Settings
from pypdf import PdfReader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from chromadb.utils import embedding_functions

# Caminhos base
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(BASE_DIR, "data", "tese_investimentos")
DB_DIR = os.path.join(BASE_DIR, ".chroma_db")

class RAGRepository:
    def __init__(self):
        # Inicializa o ChromaDB com armazenamento persistente
        self.chroma_client = chromadb.PersistentClient(path=DB_DIR)
        
        # Usa o modelo de embedding padrão do Chroma (leve, roda local sem custo)
        self.embedding_function = embedding_functions.DefaultEmbeddingFunction()
        
        # Obtém ou cria a coleção para as teses
        self.collection = self.chroma_client.get_or_create_collection(
            name="smc_theses",
            embedding_function=self.embedding_function
        )
        
        # Inicializa o quebrador de texto para os documentos
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1500,
            chunk_overlap=300,
            separators=["\n\n", "\n", ".", " ", ""]
        )

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
        """Lê todos os documentos na pasta data/tese_investimentos e alimenta o banco vetorial."""
        print("[RAG] Verificando novos documentos para indexação...")
        
        if not os.path.exists(DATA_DIR):
            print(f"[RAG] Pasta não encontrada: {DATA_DIR}")
            return

        files = os.listdir(DATA_DIR)
        
        # Verifica quais documentos já estão no banco para não duplicar
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
            
            # Simple heuristic to extract ticker from filename
            ticker = "UNKNOWN"
            if "PETR4" in filename.upper(): ticker = "PETR4"
            elif "WEG" in filename.upper() or "WEGE3" in filename.upper(): ticker = "WEGE3"
            elif "ITUB4" in filename.upper() or "ITAÚ" in filename.upper(): ticker = "ITUB4"
            elif "VALE3" in filename.upper(): ticker = "VALE3"
            elif "NUBANK" in filename.upper() or "NU" in filename.upper(): ticker = "NU"
            elif "AMERICANAS" in filename.upper() or "AMER3" in filename.upper(): ticker = "AMER3"

            if filename in existing_sources:
                continue

            print(f"[RAG] Lendo e indexando: {filename} (Ticker: {ticker})")
            text = self._extract_text_from_file(filepath)
            
            if not text.strip():
                continue

            chunks = self.text_splitter.split_text(text)
            
            # Prepara os dados para o ChromaDB
            ids = [f"{filename}_chunk_{i}" for i in range(len(chunks))]
            metadatas = [{"source": filename, "ticker": ticker, "chunk_index": i} for i in range(len(chunks))]
            
            self.collection.add(
                documents=chunks,
                metadatas=metadatas,
                ids=ids
            )
            new_docs_count += len(chunks)

        if new_docs_count > 0:
            print(f"[RAG] Sucesso! {new_docs_count} novos fragmentos adicionados ao ChromaDB.")
        else:
            print("[RAG] Banco vetorial já atualizado.")

    def search_thesis(self, ticker: str, query: str, top_k: int = 4) -> List[Dict[str, Any]]:
        """Busca os fragmentos mais relevantes da tese de investimento para um dado Ticker e Query."""
        # Filtro opcional: se o ticker for válido, filtra. Senão, busca global.
        where_filter = {"ticker": ticker} if ticker and ticker != "UNKNOWN" else None
        
        try:
            results = self.collection.query(
                query_texts=[query],
                n_results=top_k,
                where=where_filter
            )
            
            # Formata a resposta
            formatted_results = []
            if results and results["documents"] and len(results["documents"][0]) > 0:
                for i in range(len(results["documents"][0])):
                    doc = results["documents"][0][i]
                    meta = results["metadatas"][0][i] if results["metadatas"] else {}
                    formatted_results.append({
                        "content": doc,
                        "metadata": meta
                    })
            return formatted_results
            
        except Exception as e:
            print(f"[RAG] Erro ao buscar tese: {e}")
            return []

# Singleton para uso na aplicação
rag_db = RAGRepository()

# Ao inicializar o módulo, garantimos que os PDFs presentes já sejam ingeridos.
# (Em produção, isso rodaria em um job de ingestão separado, mas aqui facilita a demo)
rag_db.ingest_documents()
