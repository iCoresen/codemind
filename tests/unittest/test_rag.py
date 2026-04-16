import pytest
import asyncio
from unittest.mock import patch, AsyncMock, MagicMock

from app.rag.document_parser import DocumentParser
from app.rag.embedding_service import EmbeddingService
from app.rag.vector_store import ChromaVectorStore
from app.rag.evaluation import RAGEvaluator
from app.rag.retriever import RAGRetriever
from app.config import Settings


@pytest.fixture
def settings():
    return Settings(
        github_token="fake_token",
        ai_api_key="fake_key",
        ai_base_url="https://fake.api.com",
        ai_model="fake_model",
        ai_embedding_model="fake_embedding_model",
        ai_embedding_api_key="fake_embedding_key",
        ai_embedding_base_url="https://fake.embedding.api.com",
        ai_fallback_models="fake_fallback",
        ai_timeout=30,
        github_webhook_secret="fake_secret",
        server_host="0.0.0.0",
        server_port=8080,
        log_level="INFO",
        redis_url="redis://localhost:6379/0",
        changelog_soft_timeout=5,
        changelog_hard_timeout=10,
        logic_soft_timeout=15,
        logic_hard_timeout=25,
        unittest_soft_timeout=20,
        unittest_hard_timeout=30,
        default_review_level=3,
        core_keywords=["auth", "payment", "database"],
    )


@pytest.fixture
def document_parser():
    return DocumentParser(chunk_size=50, chunk_overlap=10)


@pytest.fixture
def mock_ai_handler():
    handler = MagicMock()
    handler.async_embedding = AsyncMock(return_value=[[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]])
    return handler


@pytest.fixture
def embedding_service(mock_ai_handler, settings):
    return EmbeddingService(mock_ai_handler, settings)


@pytest.fixture
def mock_vector_store():
    store = MagicMock(spec=ChromaVectorStore)
    store.collection = MagicMock()
    store.docs_collection = MagicMock()
    return store


class TestDocumentParser:
    def test_chunk_text(self, document_parser):
        text = "word " * 100
        chunks = document_parser._chunk_text(text, "test_source", "Test Section")

        assert len(chunks) > 1
        assert all("text" in chunk for chunk in chunks)
        assert all("metadata" in chunk for chunk in chunks)
        assert chunks[0]["metadata"]["section"] == "Test Section"
        assert chunks[0]["metadata"]["source"] == "test_source"

    def test_chunk_text_empty(self, document_parser):
        chunks = document_parser._chunk_text("", "test_source")
        assert chunks == []

    def test_parse_file_nonexistent(self, document_parser):
        chunks = document_parser.parse_file("/nonexistent/file.txt")
        assert chunks == []

    @patch("pathlib.Path.exists", return_value=False)
    def test_parse_file_path_not_exists(self, mock_exists, document_parser):
        result = document_parser.parse_file("/fake/path.txt")
        assert result == []

    def test_parse_markdown(self, document_parser):
        content = """# Header 1
Some content here

## Header 2
More content

### Header 3
Final content
"""
        chunks = document_parser._parse_markdown(content, "test.md")
        assert len(chunks) >= 1
        for chunk in chunks:
            assert "text" in chunk
            assert "metadata" in chunk
            assert chunk["metadata"]["type"] == "document"

    def test_parse_markdown_no_headers(self, document_parser):
        content = "Just plain text without any headers at all"
        chunks = document_parser._parse_markdown(content, "test.md")
        assert len(chunks) >= 1

    @patch.dict("sys.modules", {"fitz": None})
    @patch("app.rag.document_parser.logger")
    def test_parse_pdf_import_error(self, mock_logger):
        parser = DocumentParser()
        chunks = parser._parse_pdf("/fake.pdf")
        assert chunks == []
        mock_logger.error.assert_called_once()


class TestEmbeddingService:
    def test_init(self, embedding_service, mock_ai_handler):
        assert embedding_service.ai_handler == mock_ai_handler

    @pytest.mark.asyncio
    async def test_get_embeddings_success(self, embedding_service, mock_ai_handler):
        texts = ["hello world", "foo bar"]
        result = await embedding_service.get_embeddings(texts)

        assert len(result) == 2
        assert result[0] == [0.1, 0.2, 0.3]
        mock_ai_handler.async_embedding.assert_called_once_with(
            texts,
            model="fake_embedding_model",
            api_key="fake_embedding_key",
            base_url="https://fake.embedding.api.com",
        )

    @pytest.mark.asyncio
    async def test_get_embeddings_empty(self, embedding_service):
        result = await embedding_service.get_embeddings([])
        assert result == []

    @pytest.mark.asyncio
    async def test_get_embeddings_error(self, embedding_service, mock_ai_handler):
        mock_ai_handler.async_embedding = AsyncMock(side_effect=Exception("API Error"))

        with pytest.raises(Exception, match="API Error"):
            await embedding_service.get_embeddings(["test"])


class TestRAGEvaluator:
    def test_evaluate_retrieval_without_ground_truth(self):
        evaluator = RAGEvaluator()
        result = evaluator.evaluate_retrieval(
            query="test query", retrieved_docs=["doc1", "doc2"], context_relevance=0.8
        )

        assert result["query"] == "test query"
        assert result["retrieved_count"] == 2
        assert result["relevance_score"] == 0.8
        assert "hit_rate" not in result

    def test_evaluate_retrieval_with_ground_truth(self):
        evaluator = RAGEvaluator()
        result = evaluator.evaluate_retrieval(
            query="test query",
            retrieved_docs=["doc1", "doc2", "doc3"],
            ground_truth_docs=["doc1", "doc3"],
            context_relevance=0.5,
        )

        assert result["hit_rate"] == 1.0

    def test_evaluate_retrieval_partial_hit(self):
        evaluator = RAGEvaluator()
        result = evaluator.evaluate_retrieval(
            query="test query",
            retrieved_docs=["doc1"],
            ground_truth_docs=["doc1", "doc2", "doc3"],
            context_relevance=0.3,
        )

        assert result["hit_rate"] == 1.0 / 3.0

    def test_calculate_average_metrics_empty(self):
        evaluator = RAGEvaluator()
        metrics = evaluator.calculate_average_metrics()

        assert metrics["avg_relevance"] == 0.0
        assert metrics["avg_hit_rate"] == 0.0

    def test_calculate_average_metrics(self):
        evaluator = RAGEvaluator()
        evaluator.evaluate_retrieval(
            "q1", ["d1"], ground_truth_docs=["d1"], context_relevance=1.0
        )
        evaluator.evaluate_retrieval(
            "q2", ["d2"], ground_truth_docs=["d2"], context_relevance=0.5
        )

        metrics = evaluator.calculate_average_metrics()

        assert metrics["avg_relevance"] == 0.75
        assert metrics["avg_hit_rate"] == 1.0


class TestRAGRetriever:
    @pytest.fixture
    def retriever(self, mock_vector_store, embedding_service, settings):
        return RAGRetriever(mock_vector_store, embedding_service)

    def test_init(self, retriever, mock_vector_store, embedding_service):
        assert retriever.vector_store == mock_vector_store
        assert retriever.embedding_service == embedding_service
        assert retriever._bm25_corpus == {}

    def test_build_bm25_index(self, retriever):
        docs = [
            {"id": "1", "text": "hello world"},
            {"id": "2", "text": "foo bar"},
            {"id": "3", "text": "hello foo"},
        ]
        retriever.build_bm25_index(docs)

        assert hasattr(retriever, "bm25")
        assert hasattr(retriever, "_bm25_docs")
        assert len(retriever._bm25_docs) == 3

    @pytest.mark.asyncio
    async def test_hybrid_search_docs_empty_query(self, retriever):
        result = await retriever.hybrid_search_docs("", top_k=5)
        assert result == []

    @pytest.mark.asyncio
    async def test_hybrid_search_docs_no_bm25_index(
        self, retriever, mock_vector_store, embedding_service
    ):
        mock_embedding = [[0.1, 0.2, 0.3]]
        embedding_service.get_embeddings = AsyncMock(return_value=mock_embedding)

        mock_vector_store.query_docs.return_value = {
            "ids": [["doc1", "doc2"]],
            "documents": [["hello world", "foo bar"]],
            "metadatas": [[{"source": "test"}, {"source": "test2"}]],
            "distances": [[0.1, 0.2]],
        }

        result = await retriever.hybrid_search_docs("hello", top_k=2)

        assert len(result) <= 2
        embedding_service.get_embeddings.assert_called_once_with(["hello"])

    @pytest.mark.asyncio
    async def test_hybrid_search_docs_with_bm25(
        self, retriever, mock_vector_store, embedding_service
    ):
        docs = [
            {"id": "1", "text": "hello world testing"},
            {"id": "2", "text": "foo bar production"},
            {"id": "3", "text": "hello foo code"},
        ]
        retriever.build_bm25_index(docs)

        mock_embedding = [[0.1, 0.2, 0.3]]
        embedding_service.get_embeddings = AsyncMock(return_value=mock_embedding)

        mock_vector_store.query_docs.return_value = {
            "ids": [["1", "2"]],
            "documents": [["hello world testing", "foo bar production"]],
            "metadatas": [[{"source": "test1"}, {"source": "test2"}]],
            "distances": [[0.1, 0.5]],
        }

        result = await retriever.hybrid_search_docs("hello world", top_k=3)

        assert len(result) <= 3
        assert hasattr(retriever, "bm25")

    @pytest.mark.asyncio
    async def test_get_relevant_commits_empty_query(self, retriever):
        result = await retriever.get_relevant_commits("", "owner", "repo", top_k=5)
        assert result == []

    @pytest.mark.asyncio
    async def test_get_relevant_commits_success(
        self, retriever, mock_vector_store, embedding_service
    ):
        mock_embedding = [[0.1, 0.2, 0.3]]
        embedding_service.get_embeddings = AsyncMock(return_value=mock_embedding)

        mock_vector_store.query.return_value = {
            "ids": [["owner/repo@abc123"]],
            "documents": [["Fix bug in auth"]],
            "metadatas": [
                [{"owner": "owner", "repo": "repo", "author": "test", "type": "commit"}]
            ],
            "distances": [[0.1]],
        }

        result = await retriever.get_relevant_commits(
            "fix auth bug", "owner", "repo", top_k=5
        )

        assert len(result) == 1
        assert result[0]["id"] == "owner/repo@abc123"
        assert result[0]["document"] == "Fix bug in auth"
        assert result[0]["distance"] == 0.1

    @pytest.mark.asyncio
    async def test_get_relevant_commits_no_results(
        self, retriever, mock_vector_store, embedding_service
    ):
        mock_embedding = [[0.1, 0.2, 0.3]]
        embedding_service.get_embeddings = AsyncMock(return_value=mock_embedding)

        mock_vector_store.query.return_value = {
            "ids": [[]],
            "documents": [[]],
            "metadatas": [[]],
            "distances": [[]],
        }

        result = await retriever.get_relevant_commits("test query", "owner", "repo")
        assert result == []


class TestChromaVectorStore:
    @patch("app.rag.vector_store.chromadb.PersistentClient")
    @patch("app.rag.vector_store.os.makedirs")
    def test_init(self, mock_makedirs, mock_chroma_client):
        mock_client_instance = MagicMock()
        mock_chroma_client.return_value = mock_client_instance
        mock_client_instance.get_or_create_collection.return_value = MagicMock()

        store = ChromaVectorStore(persist_directory="/tmp/test")

        mock_makedirs.assert_called_once_with("/tmp/test", exist_ok=True)
        mock_chroma_client.assert_called_once()

    @patch("app.rag.vector_store.chromadb.PersistentClient")
    @patch("app.rag.vector_store.os.makedirs")
    def test_add_documents_empty_ids(self, mock_makedirs, mock_chroma_client):
        mock_client_instance = MagicMock()
        mock_chroma_client.return_value = mock_client_instance
        mock_collection = MagicMock()
        mock_client_instance.get_or_create_collection.return_value = mock_collection

        store = ChromaVectorStore()
        store.add_documents(ids=[], documents=[], embeddings=[])

        mock_collection.add.assert_not_called()

    @patch("app.rag.vector_store.chromadb.PersistentClient")
    @patch("app.rag.vector_store.os.makedirs")
    def test_add_documents_with_metadata(self, mock_makedirs, mock_chroma_client):
        mock_client_instance = MagicMock()
        mock_chroma_client.return_value = mock_client_instance
        mock_collection = MagicMock()
        mock_client_instance.get_or_create_collection.return_value = mock_collection
        mock_collection.get.return_value = {"ids": []}

        store = ChromaVectorStore()
        store.add_documents(
            ids=["id1", "id2"],
            documents=["doc1", "doc2"],
            embeddings=[[0.1, 0.2], [0.3, 0.4]],
            metadatas=[{"type": "test"}, {"type": "test2"}],
        )

        mock_collection.add.assert_called_once()

    @patch("app.rag.vector_store.chromadb.PersistentClient")
    @patch("app.rag.vector_store.os.makedirs")
    def test_add_knowledge_docs(self, mock_makedirs, mock_chroma_client):
        mock_client_instance = MagicMock()
        mock_chroma_client.return_value = mock_client_instance
        mock_docs_collection = MagicMock()
        mock_client_instance.get_or_create_collection.return_value = (
            mock_docs_collection
        )

        store = ChromaVectorStore()
        store.add_knowledge_docs(
            ids=["id1"],
            documents=["doc1"],
            embeddings=[[0.1, 0.2]],
            metadatas=[{"type": "knowledge"}],
        )

        mock_docs_collection.add.assert_called_once()

    @patch("app.rag.vector_store.chromadb.PersistentClient")
    @patch("app.rag.vector_store.os.makedirs")
    def test_query(self, mock_makedirs, mock_chroma_client):
        mock_client_instance = MagicMock()
        mock_chroma_client.return_value = mock_client_instance
        mock_collection = MagicMock()
        mock_client_instance.get_or_create_collection.return_value = mock_collection
        mock_collection.query.return_value = {
            "ids": [["id1"]],
            "documents": [["test doc"]],
            "metadatas": [[{"type": "commit"}]],
            "distances": [[0.1]],
        }

        store = ChromaVectorStore()
        result = store.query(query_embeddings=[[0.1, 0.2]], n_results=5)

        mock_collection.query.assert_called_once()
        assert result["ids"] == [["id1"]]

    @patch("app.rag.vector_store.chromadb.PersistentClient")
    @patch("app.rag.vector_store.os.makedirs")
    def test_query_docs(self, mock_makedirs, mock_chroma_client):
        mock_client_instance = MagicMock()
        mock_chroma_client.return_value = mock_client_instance
        mock_docs_collection = MagicMock()
        mock_client_instance.get_or_create_collection.return_value = (
            mock_docs_collection
        )
        mock_docs_collection.query.return_value = {
            "ids": [["doc1"]],
            "documents": [["knowledge doc"]],
            "metadatas": [[{"type": "doc"}]],
            "distances": [[0.05]],
        }

        store = ChromaVectorStore()
        result = store.query_docs(query_embeddings=[[0.1, 0.2]], n_results=5)

        mock_docs_collection.query.assert_called_once()
        assert result["ids"] == [["doc1"]]

    @patch("app.rag.vector_store.chromadb.PersistentClient")
    @patch("app.rag.vector_store.os.makedirs")
    def test_add_documents_skips_existing(self, mock_makedirs, mock_chroma_client):
        mock_client_instance = MagicMock()
        mock_chroma_client.return_value = mock_client_instance
        mock_collection = MagicMock()
        mock_client_instance.get_or_create_collection.return_value = mock_collection
        mock_collection.get.return_value = {"ids": ["id1"]}

        store = ChromaVectorStore()
        store.add_documents(
            ids=["id1", "id2"],
            documents=["doc1", "doc2"],
            embeddings=[[0.1, 0.2], [0.3, 0.4]],
        )

        call_args = mock_collection.add.call_args
        assert "id2" in call_args[1]["ids"]


class TestGitHubDataCollector:
    @pytest.mark.asyncio
    async def test_collect_and_store_commits_empty(self):
        from app.rag.data_collector import GitHubDataCollector

        mock_github = AsyncMock()
        mock_github.get_recent_commits = AsyncMock(return_value=[])

        mock_embedding_service = MagicMock(spec=EmbeddingService)
        mock_vector_store = MagicMock(spec=ChromaVectorStore)

        collector = GitHubDataCollector(
            mock_github, mock_embedding_service, mock_vector_store
        )
        result = await collector.collect_and_store_commits("owner", "repo")

        assert result == 0

    @pytest.mark.asyncio
    async def test_collect_and_store_commits_success(self):
        from app.rag.data_collector import GitHubDataCollector

        commits = [
            {"sha": "abc123", "message": "Fix bug", "author": "tester"},
            {"sha": "def456", "message": "Add feature", "author": "developer"},
        ]

        mock_github = AsyncMock()
        mock_github.get_recent_commits = AsyncMock(return_value=commits)

        mock_embedding_service = MagicMock(spec=EmbeddingService)
        mock_embedding_service.get_embeddings = AsyncMock(return_value=[[0.1], [0.2]])

        mock_vector_store = MagicMock(spec=ChromaVectorStore)

        collector = GitHubDataCollector(
            mock_github, mock_embedding_service, mock_vector_store
        )
        result = await collector.collect_and_store_commits("owner", "repo")

        assert result == 2
        mock_vector_store.add_documents.assert_called_once()

    @pytest.mark.asyncio
    async def test_collect_and_store_commits_error(self):
        from app.rag.data_collector import GitHubDataCollector

        mock_github = AsyncMock()
        mock_github.get_recent_commits = AsyncMock(side_effect=Exception("API Error"))

        mock_embedding_service = MagicMock(spec=EmbeddingService)
        mock_vector_store = MagicMock(spec=ChromaVectorStore)

        collector = GitHubDataCollector(
            mock_github, mock_embedding_service, mock_vector_store
        )
        result = await collector.collect_and_store_commits("owner", "repo")

        assert result == 0


class TestKnowledgeManager:
    @pytest.mark.asyncio
    async def test_ingest_document_no_chunks(self):
        from app.rag.knowledge_manager import KnowledgeManager

        mock_parser = MagicMock(spec=DocumentParser)
        mock_parser.parse_file.return_value = []

        mock_embedding_service = MagicMock(spec=EmbeddingService)
        mock_vector_store = MagicMock(spec=ChromaVectorStore)

        manager = KnowledgeManager(
            mock_vector_store, mock_embedding_service, mock_parser
        )
        await manager.ingest_document("/fake/path.txt")

        mock_vector_store.add_knowledge_docs.assert_not_called()

    @pytest.mark.asyncio
    async def test_ingest_document_success(self):
        from app.rag.knowledge_manager import KnowledgeManager

        chunks = [
            {"text": "chunk1", "metadata": {"source": "test.txt"}},
            {"text": "chunk2", "metadata": {"source": "test.txt"}},
        ]

        mock_parser = MagicMock(spec=DocumentParser)
        mock_parser.parse_file.return_value = chunks

        mock_embedding_service = MagicMock(spec=EmbeddingService)
        mock_embedding_service.get_embeddings = AsyncMock(return_value=[[0.1], [0.2]])

        mock_vector_store = MagicMock(spec=ChromaVectorStore)

        manager = KnowledgeManager(
            mock_vector_store, mock_embedding_service, mock_parser
        )
        await manager.ingest_document("/fake/path.txt")

        mock_vector_store.add_knowledge_docs.assert_called_once()
        call_kwargs = mock_vector_store.add_knowledge_docs.call_args[1]
        assert len(call_kwargs["ids"]) == 2
        assert len(call_kwargs["documents"]) == 2

    def test_load_all_docs_for_bm25(self):
        from app.rag.knowledge_manager import KnowledgeManager

        mock_vector_store = MagicMock()
        mock_docs_collection = MagicMock()
        mock_docs_collection.get.return_value = {
            "ids": ["id1", "id2"],
            "documents": ["doc1", "doc2"],
            "metadatas": [{"type": "t1"}, {"type": "t2"}],
        }
        mock_vector_store.docs_collection = mock_docs_collection

        mock_embedding_service = MagicMock(spec=EmbeddingService)
        mock_parser = MagicMock(spec=DocumentParser)

        manager = KnowledgeManager(
            mock_vector_store, mock_embedding_service, mock_parser
        )
        docs = manager.load_all_docs_for_bm25()

        assert len(docs) == 2
        assert docs[0]["id"] == "id1"
        assert docs[0]["text"] == "doc1"

    def test_load_all_docs_for_bm25_error(self):
        from app.rag.knowledge_manager import KnowledgeManager

        mock_vector_store = MagicMock()
        mock_docs_collection = MagicMock()
        mock_docs_collection.get.side_effect = Exception("DB Error")
        mock_vector_store.docs_collection = mock_docs_collection

        mock_embedding_service = MagicMock(spec=EmbeddingService)
        mock_parser = MagicMock(spec=DocumentParser)

        manager = KnowledgeManager(
            mock_vector_store, mock_embedding_service, mock_parser
        )
        docs = manager.load_all_docs_for_bm25()

        assert docs == []
