# Changelog

All notable changes to CodeMind will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-04-17

### Added
- **Multi-level Code Review**: Three-tier review system (Level 1-3)
  - Level 1: Changelog/Documentation review
  - Level 2: Logic and security review
  - Level 3: Deep review with unit test suggestions
- **Intelligent PR Routing**: Automatic review level selection based on PR characteristics
- **RAG Knowledge Base**: Hybrid search (BM25 + Vector) for context-aware review
- **GitHub Webhook Integration**: Real-time PR review on push events
- **CLI Tool**: Manual PR review trigger with level selection
- **Docker Support**: Full containerized deployment with docker-compose
- **Multi-language AST Analysis**: Support for Python, JavaScript, TypeScript, Go, Java

### Features
- GitHub API integration with retry and rate limiting
- Redis-based distributed lock for webhook deduplication
- ARQ async task queue for background processing
- ChromaDB vector storage for semantic search
- LiteLLM integration for unified AI model interface
- Tree-sitter based code structure analysis
- Timeout control with graceful degradation
- CI status update integration

### Tests
- 66 unit and integration tests covering all core modules
- RAG system integration tests
- AI handler mock tests
- Webhook event handling tests
- PR routing logic tests

## [0.1.0] - 2026-03-30

### Added
- MVP project foundation with environment configuration (.env.example)
- CLI interface and configuration management
- GitHub API client with webhook support
- Redis-based queue and distributed lock system
- Multi-agent code review framework
- Makefile for common development commands (install, api, cli)
