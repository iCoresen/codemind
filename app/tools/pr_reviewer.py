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
        
        def _get_result(res: any, name: str) -> str:
            if isinstance(res, Exception):
                logger.error(f"Task {name} failed: {res}")
                return f"Error during {name} analysis: {str(res)}"
            return res[0]

        security_res = _get_result(results[0], "security")
        performance_res = _get_result(results[1], "performance")
        style_res = _get_result(results[2], "style")

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
        try:
            await self.github.publish_pr_comment(owner, repo, pr_number, formatted_comment)
            logger.info(f"Review comment published for {owner}/{repo}#{pr_number}")
        except GitHubAPIError as e:
            logger.error(f"Failed to publish PR review comment for {owner}/{repo}#{pr_number}: {e}")
            raise


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
                md += f"- **安全评分**: {metrics.get('security_score', 'N/A')}/100\n"
                md += f"- **性能评分**: {metrics.get('performance_score', 'N/A')}/100\n"
                md += f"- **代码质量评分**: {metrics.get('code_quality_score', 'N/A')}/100\n"
                md += f"- **综合评分**: {metrics.get('overall_score', 'N/A')}/100\n"
                md += f"- **审查工作量估计**: {metrics.get('estimated_review_effort', 'N/A')}/5\n\n"
                
                # 阻断性问题
                blocker_issues = prioritized_issues.get("blocker_issues", [])
                if blocker_issues:
                    md += f"### 🚨 阻断性问题（必须立即修复）\n"
                    for i, issue in enumerate(blocker_issues, 1):
                        md += f"**{i}. {issue.get('category', '')} - {issue.get('description', '')}**\n"
                        md += f"   - 严重性: {issue.get('severity', '')}\n"
                        md += f"   - 影响文件: {', '.join(issue.get('files_affected', []))}\n"
                        md += f"   - 立即行动: {issue.get('immediate_action', '')}\n"
                        md += f"   - 预估修复时间: {issue.get('estimated_fix_time', '')}\n\n"
                
                # 高优先级问题
                high_priority_issues = prioritized_issues.get("high_priority_issues", [])
                if high_priority_issues:
                    md += f"### ⚠️ 高优先级问题\n"
                    for i, issue in enumerate(high_priority_issues, 1):
                        md += f"**{i}. {issue.get('category', '')} - {issue.get('description', '')}**\n"
                        md += f"   - 严重性: {issue.get('severity', '')}\n"
                        md += f"   - 影响文件: {', '.join(issue.get('files_affected', []))}\n"
                        md += f"   - 建议行动: {issue.get('recommended_action', '')}\n"
                        md += f"   - 业务影响: {issue.get('business_impact', '')}\n\n"
                
                # 中优先级问题
                medium_priority_issues = prioritized_issues.get("medium_priority_issues", [])
                if medium_priority_issues:
                    md += f"### 📝 中优先级问题\n"
                    for i, issue in enumerate(medium_priority_issues, 1):
                        md += f"{i}. {issue.get('category', '')} - {issue.get('description', '')}\n"
                        md += f"   - 改进建议: {issue.get('improvement_suggestion', '')}\n\n"
                
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
