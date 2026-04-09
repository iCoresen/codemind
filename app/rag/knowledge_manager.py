import logging
import uuid
from typing import List, Dict, Any
from app.rag.embedding_service import EmbeddingService
from app.rag.vector_store import ChromaVectorStore
from app.rag.document_parser import DocumentParser

logger = logging.getLogger("codemind.rag.manager")

class KnowledgeManager:
    def __init__(
        self,
        vector_store: ChromaVectorStore,
        embedding_service: EmbeddingService,
        document_parser: DocumentParser
    ):
        self.vector_store = vector_store
        self.embedding_service = embedding_service
        self.document_parser = document_parser

    async def ingest_document(self, file_path: str) -> None:
        """Parse a document and store its chunks into the RAG vector store"""
        try:
            chunks = self.document_parser.parse_file(file_path)
            if not chunks:
                logger.warning(f"No chunks extracted from {file_path}")
                return

            documents = []
            ids = []
            metadatas = []
            
            for chunk in chunks:
                doc_id = str(uuid.uuid4())
                ids.append(doc_id)
                documents.append(chunk["text"])
                # store the ID in metadata as well to sync memory
                meta = chunk["metadata"]
                meta["id"] = doc_id
                metadatas.append(meta)

            embeddings = await self.embedding_service.get_embeddings(documents)
            
            self.vector_store.add_knowledge_docs(
                ids=ids,
                documents=documents,
                embeddings=embeddings,
                metadatas=metadatas
            )
            
            logger.info(f"Ingested {len(chunks)} chunks from {file_path}")
            
        except Exception as e:
            logger.error(f"Failed to ingest knowledge document {file_path}: {e}")
            raise

    def load_all_docs_for_bm25(self) -> List[Dict[str, Any]]:
        """Load all docs from collection to initialize BM25"""
        try:
            results = self.vector_store.docs_collection.get(include=["documents", "metadatas"])
            docs = []
            if results and results["documents"]:
                for i in range(len(results["documents"])):
                    docs.append({
                        "id": results["ids"][i],
                        "text": results["documents"][i],
                        "metadata": results["metadatas"][i]
                    })
            return docs
        except Exception as e:
            logger.error(f"Failed to load docs for BM25: {e}")
            return []
