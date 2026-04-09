import os
import logging
import chromadb
from chromadb.config import Settings
from typing import List, Dict, Any, Optional

logger = logging.getLogger("codemind.rag.vectorstore")

class ChromaVectorStore:
    def __init__(self, persist_directory: str = "./data/chroma"):
        self.persist_directory = persist_directory
        os.makedirs(self.persist_directory, exist_ok=True)
        
        self.client = chromadb.PersistentClient(path=self.persist_directory)
        self.collection_name = "commits"
        self.docs_collection_name = "docs"
        self.collection = self.client.get_or_create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"}
        )
        self.docs_collection = self.client.get_or_create_collection(
            name=self.docs_collection_name,
            metadata={"hnsw:space": "cosine"}
        )

    def add_documents(
        self,
        ids: List[str],
        documents: List[str],
        embeddings: List[List[float]],
        metadatas: Optional[List[Dict[str, Any]]] = None
    ) -> None:
        if not ids:
            return
            
        try:
            # Check if ids already exist (naive approach, can be optimized)
            existing = self.collection.get(ids=ids)
            existing_ids = set(existing["ids"])
            
            new_ids = []
            new_docs = []
            new_embs = []
            new_metas = []
            
            for i, doc_id in enumerate(ids):
                if doc_id not in existing_ids:
                    new_ids.append(doc_id)
                    new_docs.append(documents[i])
                    new_embs.append(embeddings[i])
                    if metadatas:
                        new_metas.append(metadatas[i])
                        
            if new_ids:
                if metadatas:
                    self.collection.add(
                        ids=new_ids,
                        embeddings=new_embs,
                        documents=new_docs,
                        metadatas=new_metas
                    )
                else:
                    self.collection.add(
                        ids=new_ids,
                        embeddings=new_embs,
                        documents=new_docs
                    )
                logger.info(f"Added {len(new_ids)} new documents to vector store.")
        except Exception as e:
            logger.error(f"Failed to add documents to vector store: {e}")
            raise

    def add_knowledge_docs(
        self,
        ids: List[str],
        documents: List[str],
        embeddings: List[List[float]],
        metadatas: Optional[List[Dict[str, Any]]] = None
    ) -> None:
        try:
            self.docs_collection.add(
                ids=ids,
                embeddings=embeddings,
                documents=documents,
                metadatas=metadatas
            )
        except Exception as e:
            logger.error(f"Failed to add knowledge docs: {e}")
            raise

    def query(
        self,
        query_embeddings: List[List[float]],
        n_results: int = 5,
        where: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        try:
            return self.collection.query(
                query_embeddings=query_embeddings,
                n_results=n_results,
                where=where,
                include=["documents", "metadatas", "distances"]
            )
        except Exception as e:
            logger.error(f"Failed to query vector store: {e}")
            raise

    def query_docs(
        self,
        query_embeddings: List[List[float]],
        n_results: int = 5,
        where: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Query knowledge document collection"""
        try:
            return self.docs_collection.query(
                query_embeddings=query_embeddings,
                n_results=n_results,
                where=where,
                include=["documents", "metadatas", "distances"]
            )
        except Exception as e:
            logger.error(f"Failed to query docs vector store: {e}")
            raise