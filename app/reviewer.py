import logging
import yaml
from pathlib import Path
from jinja2 import Template

from app.config import Settings
from app.github_client import GitHubClient
from app.ai_handler import AIHandler

try:
    import tomllib
except ImportError:
    pass # we will assume python 3.11+ natively handles this

logger = logging.getLogger("codemind.reviewer")

class PRReviewer:
    def __init__(self, settings: Settings, event_payload: dict):
        self.settings = settings
        self.event_payload = event_payload
        self.github = GitHubClient(settings.github_token)
        self.ai = AIHandler(settings)

    async def run(self):
        owner = self.event_payload["owner"]
        repo = self.event_payload["repo"]
        pr_number = self.event_payload["pr_number"]

        logger.info(f"Starting review for {owner}/{repo}#{pr_number}")

        # 1. Get PR Info
        pr_info = self.github.get_pr_info(owner, repo, pr_number)
        title = pr_info.get("title", "")
        description = pr_info.get("body", "") or ""
        head_ref = pr_info.get("head", {}).get("ref", "")
        base_ref = pr_info.get("base", {}).get("ref", "")
        branch = f"{base_ref} -> {head_ref}"

        # 2. Get Diff
        diff = self.github.get_pr_diff(owner, repo, pr_number)

        # 3. Load & Render Prompts
        prompt_path = Path(__file__).parent / "prompts" / "review_prompt.toml"
        
        with open(prompt_path, "rb") as f:
            prompts = tomllib.load(f)["pr_review_prompt"]

        system_prompt = prompts["system"]
        user_prompt_template = Template(prompts["user"])
        user_prompt = user_prompt_template.render(
            title=title,
            branch=branch,
            description=description,
            language="auto",
            diff=diff[:max(0, 30000)] # avoid overly long diff exceeding context limit
        )

        # 4. Get AI Review
        response_text, finish_reason = self.ai.chat_completion(system_prompt, user_prompt)
        
        logger.info(f"AI response received. Finish reason: {finish_reason}")
        
        # 5. Format output
        formatted_comment = self._format_review_comment(response_text)

        # 6. Publish Comment
        self.github.publish_pr_comment(owner, repo, pr_number, formatted_comment)
        logger.info(f"Review comment published for {owner}/{repo}#{pr_number}")


    def _format_review_comment(self, ai_response: str) -> str:
        try:
            text_to_parse = ai_response.strip()
            if text_to_parse.startswith("```yaml"):
                text_to_parse = text_to_parse[7:]
            if text_to_parse.startswith("```"):
                text_to_parse = text_to_parse[3:]
            if text_to_parse.endswith("```"):
                text_to_parse = text_to_parse[:-3]
                
            parsed = yaml.safe_load(text_to_parse)
            
            effort = 0
            for k, v in parsed.items():
                if k.startswith("estimated_effort"):
                    effort = v
                    break
            
            issues = parsed.get("key_issues_to_review", [])
            security = parsed.get("security_concerns", "None")
            
            md = f"## CodeMind PR Review\n\n"
            md += f"**Estimated Effort:** {effort}/5\n\n"
            
            if issues:
                md += "### Key Issues\n"
                for issue in issues:
                    md += f"- {issue}\n"
            
            md += f"\n### Security Concerns\n{security}\n"
            return md
            
        except Exception as e:
            logger.error(f"Failed to parse YAML response: {e}")
            return f"## CodeMind PR Review\n\n```yaml\n{ai_response}\n```"
