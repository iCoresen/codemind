import logging
import time
from typing import List, Dict, Any

from app.rag.embedding_service import EmbeddingService
from app.rag.vector_store import ChromaVectorStore

logger = logging.getLogger("codemind.rag.collector")

class GitHubDataCollector:
    def __init__(
        self,
        github_provider,
        embedding_service: EmbeddingService,
        vector_store: ChromaVectorStore
    ):
        self.github_provider = github_provider
        self.embedding_service = embedding_service
        self.vector_store = vector_store

    async def collect_and_store_commits(self, owner: str, repo: str, since=None) -> int:
        """
        Collect commits from GitHub and store them in the vector database.
        Returns the number of commits processed.
        """
        # Note: Github provider should have a method to get recent commits
        try:
            commits = await self.github_provider.get_recent_commits(owner, repo, since)
            if not commits:
                return 0
                
            processed_count = await self._process_commits(owner, repo, commits)
            return processed_count
        except Exception as e:
            logger.error(f"Failed to collect and store commits for {owner}/{repo}: {e}")
            return 0

    async def _process_commits(self, owner: str, repo: str, commits: List[Dict[str, Any]]) -> int:
        docs = []
        ids = []
        metas = []
        
        for commit in commits:
            sha = commit.get("sha")
            message = commit.get("message", "")
            author = commit.get("author", "Unknown")
            
            if not sha or not message:
                continue
                
            doc_id = f"{owner}/{repo}@{sha}"
            docs.append(message)
            ids.append(doc_id)
            metas.append({
                "owner": owner,
                "repo": repo,
                "sha": sha,
                "author": author,
                "type": "commit"
            })
            
        if not docs:
            return 0
            
        embeddings = await self.embedding_service.get_embeddings(docs)
        self.vector_store.add_documents(
            ids=ids,
            documents=docs,
            embeddings=embeddings,
            metadatas=metas
        )
        return len(docs)