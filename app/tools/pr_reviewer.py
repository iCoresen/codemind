import logging
import yaml
import asyncio
from pathlib import Path
# 将 PR 的具体数据（如标题、分支、描述、代码差异）动态注入到从 TOML 文件中读取的 Prompt 模板中
from jinja2 import Template

from app.config import Settings
from app.git_providers.github_provider import GitHubProvider
from app.ai_handlers.litellm_ai_handler import LiteLLMAIHandler 

try:
    import tomllib
except ImportError:
    pass

logger = logging.getLogger("codemind.reviewer")

class PRReviewer:
    def __init__(self, settings: Settings, event_payload: dict):
        self.settings = settings
        self.event_payload = event_payload # extract_pr_event 得到
        self.github = GitHubProvider(settings.github_token) # 定义一个GitProvider实例
        self.ai = LiteLLMAIHandler(settings)

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
        prompts_dir = Path(__file__).parent.parent / "prompts"
        agent_names = ["security", "performance", "style"]
        tasks = []
        
        for name in agent_names:
            path = prompts_dir / f"{name}_prompt.toml"
            with open(path, "rb") as f:
                prompts = tomllib.load(f)["pr_review_prompt"]
                
            system_prompt = prompts["system"]
            user_prompt_template = Template(prompts["user"])
            user_prompt = user_prompt_template.render(
                title=title,
                branch=branch,
                description=description,
                language="auto",
                diff=diff[:max(0, 30000)]
            )
            tasks.append(self.ai.async_chat_completion(system_prompt, user_prompt))

        # 4. Run Concurrent Reviews
        logger.info("Executing concurrent reviews: Security, Performance, Style")
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        security_res = results[0][0] if not isinstance(results[0], Exception) else str(results[0])
        performance_res = results[1][0] if not isinstance(results[1], Exception) else str(results[1])
        style_res = results[2][0] if not isinstance(results[2], Exception) else str(results[2])

        # 5. Reducer Phase
        logger.info("Summarizing results with Reducer Agent")
        reducer_path = prompts_dir / "reducer_prompt.toml"
        with open(reducer_path, "rb") as f:
            reducer_prompts = tomllib.load(f)["pr_review_prompt"]
        
        r_system = reducer_prompts["system"]
        r_user_template = Template(reducer_prompts["user"])
        r_user = r_user_template.render(
            security_report=security_res,
            performance_report=performance_res,
            style_report=style_res
        )

        max_retries = 3
        formatted_comment = ""
        
        for attempt in range(max_retries):
            # Using synchronous chat_completion for reducer or keep it async since we can await 
            try:
                response_text, finish_reason = await self.ai.async_chat_completion(r_system, r_user)
                logger.info(f"Reducer response received (Attempt {attempt + 1}). Finish reason: {finish_reason}")
                
                formatted_comment = self._format_review_comment(response_text, raise_on_fail=True)
                break
            except Exception as e:
                logger.warning(f"Attempt {attempt + 1} reducer failed: {e}")
                if attempt == max_retries - 1:
                    logger.error("Max retries reached. Falling back to raw Reducer response.")
                    raw_text = response_text if 'response_text' in locals() else str(e)
                    formatted_comment = f"## CodeMind PR Review (Raw)\n\n```yaml\n{raw_text}\n```"
                else:
                    logger.info("Retrying Reducer completion...")

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
            security = parsed.get("security_concerns", "无")
            performance = parsed.get("performance_concerns", "无")
            style = parsed.get("style_concerns", "无")
            summary = parsed.get("summary", "")
            
            md = f"## CodeMind PR Review\n\n"
            if summary:
                md += f"{summary}\n\n"
            md += f"**得分 (Estimated Effort):** {effort}/5\n\n"
            
            if issues:
                md += "### 主要问题 (Key Issues)\n"
                for issue in issues:
                    md += f"- {issue}\n"
            
            md += f"\n### 安全隐患 (Security Concerns)\n{security}\n"
            md += f"\n### 性能问题 (Performance Concerns)\n{performance}\n"
            md += f"\n### 代码规范 (Style Concerns)\n{style}\n"
            return md
            
        except Exception as e:
            logger.error(f"Failed to parse YAML response: {e}")
            if raise_on_fail:
                # 中断当前函数的执行，直接把这个异常重新抛给上一层的 try...except 块
                raise e 
            return f"## CodeMind PR Review\n\n```yaml\n{ai_response}\n```"
