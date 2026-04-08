import logging
import asyncio
import httpx
from typing import Any

from app.git_providers.github_provider import GitHubProvider
from app.agents.result_aggregator import ResultAggregator

logger = logging.getLogger("codemind.ci_updater")

class CIUpdaterService:
    """
    负责查询 PR 的 CI (check_runs) 状态并以最佳格式追加到 CodeMind 评论中。
    解耦了后台任务调度与呈现逻辑。
    """
    def __init__(self, github_provider: GitHubProvider):
        self.provider = github_provider
        self.aggregator = ResultAggregator(self.provider)

    async def execute(self, owner: str, repo: str, head_sha: str) -> None:
        """
        核心执行逻辑：
        1. 通过 head_sha 查找关联的 PR。
        2. 获取这个 sha 的全部 check_runs。
        3. 如果还未全部完成，直接返回（等待下一个 check_run completed 事件）。
        4. 如果完成，获取 CodeMind 发布的最后一条评论，并通过 aggregator 追加展示 CI 信息。
        """
        logger.info("=== CIUpdaterService.execute() 开始 ===")
        logger.info(f"参数: owner={owner}, repo={repo}, head_sha={head_sha}")
        
        # 1. 查找关联 PR
        logger.info("步骤1: 查找与提交关联的PR...")
        prs = await self._get_prs_for_commit(owner, repo, head_sha)
        logger.info(f"找到 {len(prs)} 个关联的PR")
        for i, pr in enumerate(prs):
            logger.info(f"  PR #{i+1}: number={pr.get('number')}, title={pr.get('title', 'N/A')[:50]}...")
        
        if not prs:
            logger.warning("没有找到与提交 %s 关联的PR，退出处理", head_sha)
            return

        # 2. 获取并过滤 linter 相关 check_runs
        logger.info("步骤2: 获取check_runs...")
        check_runs = await self.provider.get_pr_check_runs(owner, repo, head_sha)
        logger.info(f"获取到 {len(check_runs)} 个check_runs")
        
        # 记录所有check_runs的详细信息
        for i, check in enumerate(check_runs):
            name = check.get("name", "unknown")
            status = check.get("status", "unknown")
            conclusion = check.get("conclusion", "N/A")
            logger.info(f"  Check #{i+1}: name='{name}', status='{status}', conclusion='{conclusion}'")
        
        # 放宽过滤条件，包含更多CI类型
        relevant_checks = []
        for check in check_runs:
            name = check.get("name", "").lower()
            # 更宽松的过滤条件
            if any(keyword in name for keyword in ["flake8", "eslint", "sonar", "lint", "style", "test", "ci", "build", "check", "verify"]):
                relevant_checks.append(check)
                logger.info(f"  -> 标记为相关检查: '{name}'")
        
        logger.info(f"过滤后得到 {len(relevant_checks)} 个相关检查")
        
        if not relevant_checks:
            logger.warning("没有找到相关的linter CI检查，退出处理")
            logger.info("所有检查名称: %s", [c.get("name", "unknown") for c in check_runs])
            return

        # 检查pending状态
        logger.info("步骤3: 检查检查状态...")
        pending_checks = []
        completed_checks = []
        
        for check in relevant_checks:
            name = check.get("name", "unknown")
            status = check.get("status", "unknown")
            conclusion = check.get("conclusion", "N/A")
            
            if status != "completed":
                pending_checks.append(name)
                logger.info(f"  '{name}' 状态为 '{status}' (未完成)")
            else:
                completed_checks.append((name, conclusion))
                logger.info(f"  '{name}' 状态为 '{status}', 结论为 '{conclusion}'")
        
        if pending_checks:
            logger.info(f"有 {len(pending_checks)} 个检查仍在进行中: {pending_checks}")
            logger.info("等待下一个webhook触发，退出处理")
            return
        
        logger.info("所有相关检查已完成")
        
        # 检查是否有失败的检查
        has_failures = any(
            check.get("conclusion") in ["failure", "timed_out", "action_required"]
            for check in relevant_checks
        )
        logger.info(f"检查结果: has_failures={has_failures}")
        
        # 3. 为所有找到的 PR 更新评论
        logger.info("步骤4: 更新PR评论...")
        for pr_data in prs:
            pr_number = pr_data.get("number")
            if not pr_number:
                logger.warning("PR数据中没有number字段，跳过")
                continue
            
            logger.info(f"处理 PR #{pr_number}")
            
            bot_comments = await self._get_bot_comments(owner, repo, pr_number)
            logger.info(f"找到 {len(bot_comments)} 个CodeMind评论")
            
            if not bot_comments:
                logger.warning(f"PR #{pr_number} 没有找到CodeMind评论，跳过")
                continue

            # 使用最新的一条评论追加
            latest_comment = bot_comments[-1]
            comment_id = latest_comment.get("id")
            current_body = latest_comment.get("body", "")
            
            logger.info(f"使用评论 #{comment_id} (长度: {len(current_body)} 字符)")
            
            # 检查是否已经追加过（使用 ResultAggregator 统一判断机制）
            if self.aggregator.has_ci_results(current_body):
                logger.info(f"PR #{pr_number} 评论 {comment_id} 已经包含CI结果，跳过")
                continue

            logger.info(f"准备追加CI结果到PR #{pr_number} 评论 {comment_id}")
            
            # 通过 Aggregator 追加内容
            updated_body = self.aggregator.append_ci_results(current_body, relevant_checks, has_failures)
            
            logger.info(f"更新前长度: {len(current_body)}, 更新后长度: {len(updated_body)}")
            
            # 发布更新
            try:
                await self.provider.update_pr_comment(owner, repo, comment_id, updated_body)
                logger.info(f"成功追加CI结果到PR #{pr_number} 评论 {comment_id}")
            except Exception as e:
                logger.error(f"更新PR #{pr_number} 评论失败: {e}")
        
        logger.info("=== CIUpdaterService.execute() 完成 ===")

    async def _get_prs_for_commit(self, owner: str, repo: str, head_sha: str) -> list[dict[str, Any]]:
        """获取与指定提交相关的 PR 列表"""
        url = f"https://api.github.com/repos/{owner}/{repo}/commits/{head_sha}/pulls"
        logger.info(f"查询关联PR: {url}")
        
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(url, headers=self.provider._headers(), timeout=20.0)
                logger.info(f"GitHub API响应状态: {resp.status_code}")
                
                if resp.status_code == 404:
                    logger.warning(f"提交 {head_sha} 未找到或不在PR中")
                    return []
                
                resp.raise_for_status()
                prs = resp.json()
                logger.info(f"API返回 {len(prs)} 个PR")
                return prs
        except httpx.HTTPStatusError as e:
            logger.error(f"GitHub API错误: {e.response.status_code} - {e.response.text[:200]}")
            return []
        except Exception as e:
            logger.error(f"获取提交 {head_sha} 的PR失败: {e}")
            return []

    async def _get_bot_comments(self, owner: str, repo: str, pr_number: int) -> list[dict[str, Any]]:
        """获取由 CodeMind Bot 发布的评论"""
        logger.info(f"获取PR #{pr_number} 的评论...")
        
        try:
            comments = await self.provider.get_pr_comments(owner, repo, pr_number)
            logger.info(f"获取到 {len(comments)} 条评论")
            
            bot_comments = []
            for i, comment in enumerate(comments):
                body = comment.get("body", "")
                user = comment.get("user", {}).get("login", "unknown")
                
                # 放宽匹配条件
                if "CodeMind" in body or "codemind" in body.lower():
                    bot_comments.append(comment)
                    logger.info(f"  评论 #{i+1}: 用户={user}, 长度={len(body)}, 匹配为CodeMind评论")
            
            logger.info(f"找到 {len(bot_comments)} 个CodeMind评论")
            return bot_comments
        except Exception as e:
            logger.error(f"获取PR #{pr_number} 评论失败: {e}")
            return []
