import logging
import yaml
from pathlib import Path
# 将 PR 的具体数据（如标题、分支、描述、代码差异）动态注入到从 TOML 文件中读取的 Prompt 模板中
from jinja2 import Template

from app.config import Settings
from app.github_client import GitHubClient
from app.ai_handler import AIHandler 

try:
    import tomllib
except ImportError:
    pass

logger = logging.getLogger("codemind.reviewer")

class PRReviewer:
    def __init__(self, settings: Settings, event_payload: dict):
        self.settings = settings
        self.event_payload = event_payload # extract_pr_event 得到
        self.github = GitHubClient(settings.github_token) # 定义一个GithubClient实例
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
        head_ref = pr_info.get("head", {}).get("ref", "") # 原分支
        base_ref = pr_info.get("base", {}).get("ref", "") # 目标分支
        branch = f"{base_ref} -> {head_ref}" # 分支合并方向

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

        # 4 & 5. Get AI Review with Retry Mechanism
        max_retries = 3
        formatted_comment = ""
        
        for attempt in range(max_retries):
            response_text, finish_reason = self.ai.chat_completion(system_prompt, user_prompt)
            logger.info(f"AI response received (Attempt {attempt + 1}). Finish reason: {finish_reason}")
            
            try:
                formatted_comment = self._format_review_comment(response_text, raise_on_fail=True)
                break  # If successful, exit the retry loop
            except Exception as e:
                logger.warning(f"Attempt {attempt + 1} failed to parse YAML: {e}")
                if attempt == max_retries - 1:
                    logger.error("Max retries reached. Falling back to raw AI response.")
                    # Fallback to pure markdown raw response
                    formatted_comment = f"## CodeMind PR Review (Raw)\n\n```yaml\n{response_text}\n```"
                else:
                    logger.info("Retrying AI completion...")

        # 6. Publish Comment
        self.github.publish_pr_comment(owner, repo, pr_number, formatted_comment)
        logger.info(f"Review comment published for {owner}/{repo}#{pr_number}")


    def _format_review_comment(self, ai_response: str, raise_on_fail: bool = False) -> str:
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
            if raise_on_fail:
                # 中断当前函数的执行，直接把这个异常重新抛给上一层的 try...except 块
                raise e 
            return f"## CodeMind PR Review\n\n```yaml\n{ai_response}\n```"
