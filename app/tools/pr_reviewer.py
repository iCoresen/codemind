import logging
import yaml
import asyncio
from pathlib import Path
# 将 PR 的具体数据（如标题、分支、描述、代码差异）动态注入到从 TOML 文件中读取的 Prompt 模板中
from jinja2 import Template

from app.config import Settings
from app.git_providers.github_provider import GitHubProvider
from app.ai_handlers.litellm_ai_handler import LiteLLMAIHandler 
from app.algo.pr_processing import process_pr_files
from app.exceptions import GitHubAPIError, AIProviderError

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

        try:
            # 1. Get PR Info
            pr_info = await self.github.get_pr_info(owner, repo, pr_number)
            title = pr_info.get("title", "")
            description = pr_info.get("body", "") or ""
            head_ref = pr_info.get("head", {}).get("ref", "") # 原分支
            head_sha = pr_info.get("head", {}).get("sha", "") # 原分支sha
            base_ref = pr_info.get("base", {}).get("ref", "") # 目标分支
            branch = f"{base_ref} -> {head_ref}" # 分支合并方向

            # 2. Get Diff iteratively and format it semantically
            pr_files = await self.github.list_pr_files(owner, repo, pr_number)
            diff = process_pr_files(pr_files)
        except GitHubAPIError as e:
            logger.error(f"Failed to fetch PR info/diff from GitHub: {e}")
            raise

        # 3. Load & Render Prompts
        prompts_dir = Path(__file__).parent.parent / "prompts"
        agent_names = ["security", "performance", "style"]
        
        async def run_agent(name: str, max_retries: int = 2) -> str:
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
            
            for attempt in range(max_retries):
                try:
                    response_text, _ = await self.ai.async_chat_completion(system_prompt, user_prompt)
                    return response_text
                except Exception as e:
                    logger.warning(f"Task {name} attempt {attempt + 1} failed: {e}")
                    if attempt == max_retries - 1:
                        logger.error(f"Task {name} failed after {max_retries} attempts.")
                        return f"Error during {name} analysis: {str(e)}"
                    await asyncio.sleep(1)
            return ""

        # 4. Run Concurrent Reviews
        logger.info("Executing concurrent reviews: Security, Performance, Style")
        tasks = [run_agent(name) for name in agent_names]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 内存状态保存 (Memory State)
        agent_results = {
            "security": results[0] if not isinstance(results[0], Exception) else f"Error: {str(results[0])}",
            "performance": results[1] if not isinstance(results[1], Exception) else f"Error: {str(results[1])}",
            "style": results[2] if not isinstance(results[2], Exception) else f"Error: {str(results[2])}",
        }

        # 5. Reducer Phase
        logger.info("Summarizing results with Reducer Agent")
        reducer_path = prompts_dir / "reducer_prompt.toml"
        with open(reducer_path, "rb") as f:
            reducer_prompts = tomllib.load(f)["pr_review_prompt"]
        
        r_system = reducer_prompts["system"]
        r_user_template = Template(reducer_prompts["user"])
        r_user = r_user_template.render(
            security_report=agent_results["security"],
            performance_report=agent_results["performance"],
            style_report=agent_results["style"]
        )

        max_retries = 3
        formatted_comment = ""
        
        for attempt in range(max_retries):
            try:
                response_text, finish_reason = await self.ai.async_chat_completion(r_system, r_user)
                logger.info(f"Reducer response received (Attempt {attempt + 1}). Finish reason: {finish_reason}")
                
                formatted_comment = self._format_review_comment(response_text, owner, repo, head_sha, raise_on_fail=True)
                break
            except Exception as e:
                logger.warning(f"Attempt {attempt + 1} reducer failed: {e}")
                if attempt == max_retries - 1:
                    logger.error("Max retries reached. Triggering ultimate fallback.")
                    # Ultimate Fallback: return sub-agent content directly 
                    fallback_content = (
                        "## ⚠️ CodeMind PR Review (Fallback Mode)\n\n"
                        "*Note: Reducer failed to format the final summary. Showing raw output from individual review layers.*\n\n"
                        "### 🔒 Security Analysis\n"
                        f"{agent_results['security']}\n\n"
                        "### ⚡ Performance Analysis\n"
                        f"{agent_results['performance']}\n\n"
                        "### 🎨 Style Analysis\n"
                        f"{agent_results['style']}\n"
                    )
                    formatted_comment = fallback_content
                else:
                    logger.info("Retrying Reducer completion...")

        # 6. Publish Comment
        try:
            await self.github.publish_pr_comment(owner, repo, pr_number, formatted_comment)
            logger.info(f"Review comment published for {owner}/{repo}#{pr_number}")
        except GitHubAPIError as e:
            logger.error(f"Failed to publish PR review comment for {owner}/{repo}#{pr_number}: {e}")
            raise


    def _format_issue_item(self, issue: dict, owner: str, repo: str, head_sha: str) -> str:
        title = issue.get('title') or issue.get('description', '')[:20]
        desc = issue.get('description', '')
        file_path = issue.get('file', '')
        line = issue.get('line', '')
        
        link = ""
        if file_path and line and head_sha:
            link = f"https://github.com/{owner}/{repo}/blob/{head_sha}/{file_path}#L{line}"
            header = f"**<a href='{link}'>{title}</a>**"
        elif file_path and head_sha:
            link = f"https://github.com/{owner}/{repo}/blob/{head_sha}/{file_path}"
            header = f"**<a href='{link}'>{title}</a>**"
        else:
            header = f"**{title}**"
            
        md_part = f"{header}\n"
        md_part += f"> {desc}\n>\n"
        
        action = issue.get('immediate_action') or issue.get('recommended_action') or issue.get('improvement_suggestion')
        if action:
            md_part += f"> 💡 **建议修复**: {action}\n"
            
        return md_part + "\n"

    def _format_review_comment(self, ai_response: str, owner: str, repo: str, head_sha: str, raise_on_fail: bool = False) -> str:
        try:
            text_to_parse = ai_response.strip()
            if text_to_parse.startswith("```yaml"):
                text_to_parse = text_to_parse[7:]
            if text_to_parse.startswith("```"):
                text_to_parse = text_to_parse[3:]
            if text_to_parse.endswith("```"):
                text_to_parse = text_to_parse[:-3]
                
            parsed = yaml.safe_load(text_to_parse)
            
            # 检查是否是新的final_review格式
            if "final_review" in parsed:
                review = parsed["final_review"]
                pr_summary = review.get("pr_summary", {})
                prioritized_issues = review.get("prioritized_issues", {})
                metrics = review.get("metrics", {})
                action_plan = review.get("action_plan", {})
                executive_summary = review.get("executive_summary", "")
                
                md = f"## 🎯 CodeMind PR 综合审查报告\n\n"
                
                # PR摘要
                md += f"### 📋 PR摘要\n"
                md += f"- **标题**: {pr_summary.get('title', 'N/A')}\n"
                md += f"- **分支**: {pr_summary.get('branch', 'N/A')}\n"
                md += f"- **总体风险等级**: {pr_summary.get('overall_risk_level', 'N/A')}\n"
                md += f"- **合并建议**: **{pr_summary.get('merge_recommendation', 'N/A')}**\n\n"
                
                # 执行摘要
                if executive_summary:
                    md += f"### 📊 执行摘要\n{executive_summary}\n\n"
                
                # 指标
                md += f"### 📈 审查指标\n"
                md += f"- **安全评分**: {metrics.get('security_score', 'N/A')}/10\n"
                md += f"- **性能评分**: {metrics.get('performance_score', 'N/A')}/10\n"
                md += f"- **代码质量评分**: {metrics.get('code_quality_score', 'N/A')}/10\n"
                md += f"- **综合评分**: {metrics.get('overall_score', 'N/A')}/10\n"
                md += f"- **审查工作量估计**: {metrics.get('estimated_review_effort', 'N/A')}/5\n\n"
                
                # 阻断性问题
                blocker_issues = prioritized_issues.get("blocker_issues", [])
                if blocker_issues:
                    md += f"### 🚨 阻断性问题（必须立即修复）\n<br>\n\n"
                    for issue in blocker_issues:
                        md += self._format_issue_item(issue, owner, repo, head_sha)
                
                # 高优先级问题
                high_priority_issues = prioritized_issues.get("high_priority_issues", [])
                if high_priority_issues:
                    md += f"### ⚠️ 高优先级问题\n<br>\n\n"
                    for issue in high_priority_issues:
                        md += self._format_issue_item(issue, owner, repo, head_sha)
                
                # 中优先级问题
                medium_priority_issues = prioritized_issues.get("medium_priority_issues", [])
                if medium_priority_issues:
                    md += f"### 📝 中优先级问题\n<br>\n\n"
                    for issue in medium_priority_issues:
                        md += self._format_issue_item(issue, owner, repo, head_sha)
                
                # 建议与低优先级
                low_priority_suggestions = prioritized_issues.get("low_priority_suggestions", [])
                if low_priority_suggestions:
                    md += f"### 💡 低优先级建议\n<br>\n\n"
                    for issue in low_priority_suggestions:
                        md += self._format_issue_item(issue, owner, repo, head_sha)
                
                # 行动计划
                md += f"### 🎯 行动计划\n"
                immediate_actions = action_plan.get("immediate_actions", [])
                if immediate_actions:
                    md += f"**立即执行**:\n"
                    for action in immediate_actions:
                        md += f"- {action}\n"
                
                short_term_improvements = action_plan.get("short_term_improvements", [])
                if short_term_improvements:
                    md += f"\n**短期改进**:\n"
                    for improvement in short_term_improvements:
                        md += f"- {improvement}\n"
                
                long_term_considerations = action_plan.get("long_term_considerations", [])
                if long_term_considerations:
                    md += f"\n**长期考虑**:\n"
                    for consideration in long_term_considerations:
                        md += f"- {consideration}\n"
                
                return md
            else:
                # 向后兼容：处理旧的格式
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
                raise e 
            return f"## CodeMind PR Review\n\n```yaml\n{ai_response}\n```"
