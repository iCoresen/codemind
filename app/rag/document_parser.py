import re
import logging
from typing import List, Dict, Any
from pathlib import Path

logger = logging.getLogger("codemind.rag.parser")

class DocumentParser:
    def __init__(self, chunk_size: int = 1000, chunk_overlap: int = 200):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def parse_file(self, file_path: str) -> List[Dict[str, Any]]:
        path = Path(file_path)
        if not path.exists():
            logger.error(f"File not found: {file_path}")
            return []

        if path.suffix.lower() == '.md':
            return self._parse_markdown(path.read_text(encoding='utf-8'), file_path)
        elif path.suffix.lower() == '.pdf':
            return self._parse_pdf(file_path)
        else:
            # Fallback to plain text
            return self._chunk_text(path.read_text(encoding='utf-8'), file_path)

    def _parse_markdown(self, content: str, source: str) -> List[Dict[str, Any]]:
        # A simple markdown splitting strategy by headers
        chunks = []
        sections = re.split(r'(^#{1,3}\s+.*$)', content, flags=re.MULTILINE)
        
        current_section = "Intro"
        current_content = ""
        
        for part in sections:
            if re.match(r'^#{1,3}\s+', part):
                if current_content.strip():
                    pieces = self._chunk_text(current_content, source, section=current_section)
                    chunks.extend(pieces)
                current_section = part.strip()
                current_content = ""
            else:
                current_content += part

        if current_content.strip():
            pieces = self._chunk_text(current_content, source, section=current_section)
            chunks.extend(pieces)
            
        return chunks

    def _parse_pdf(self, file_path: str) -> List[Dict[str, Any]]:
        try:
            import fitz  # PyMuPDF
            doc = fitz.open(file_path)
            text = ""
            for page in doc:
                text += page.get_text()
            return self._chunk_text(text, file_path)
        except ImportError:
            logger.error("pymupdf not installed, cannot parse PDF")
            return []

    def _chunk_text(self, text: str, source: str, section: str = "") -> List[Dict[str, Any]]:
        words = text.split()
        chunks = []
        
        # very simple word-based chunker
        for i in range(0, len(words), self.chunk_size - self.chunk_overlap):
            chunk_words = words[i:i + self.chunk_size]
            chunk_text = " ".join(chunk_words)
            if chunk_text.strip():
                chunks.append({
                    "text": chunk_text,
                    "metadata": {
                        "source": source,
                        "section": section,
                        "type": "document"
                    }
                })
        return chunks