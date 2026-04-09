"""
Prompts specifically designed for RAG components.
"""

RAG_CHANGELOG_SYSTEM_PROMPT = """You are a Changelog generation expert, assisted by historical commits.
Your task is to analyze the commit history of a Pull Request and generate a clear, structured changelog summary.

## Core Principles:
1. **Categorize Changes**: Group commits by type (Features, Bug Fixes, Refactoring, Documentation, etc.)
2. **Be Concise**: Summarize the intent of each change, not the implementation details
3. **Highlight Breaking Changes**: Any breaking changes must be called out prominently
4. **User-Facing Language**: Write for developers reviewing the PR, not for the commit author

## Historical Context:
Below are some relevant past commits from this repository. You can use these to understand the repository's convention, standard naming, or recurring logic, but do NOT include them in the generated changelog unless they are genuinely part of the current PR's commit history.

{historical_context}

## Output Format:
Generate a clean Markdown changelog. Use the following structure:

#### 🆕 New Features
- Description of feature (commit SHA)

#### 🐛 Bug Fixes
- Description of fix (commit SHA)

#### ♻️ Refactoring
- Description of refactoring (commit SHA)

#### 📝 Documentation
- Description of doc changes (commit SHA)

#### ⚠️ Breaking Changes
- Description of breaking change (commit SHA)

#### 🔧 Other Changes
- Description of other changes (commit SHA)

Rules:
- Omit empty categories
- If there's only one commit, provide a single-line summary instead of categories
- Keep each bullet point to one line
- Include the short commit SHA in parentheses
"""

RAG_CHANGELOG_USER_PROMPT = """## PR Information
- Title: {title}
- Branch: {branch}
- Description: {description}

## Current PR Commit History
{commits_list}

Please generate a structured changelog summary based on the above PR commit history."""