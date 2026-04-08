import argparse
import asyncio
import logging
import sys

from app.config import load_settings
from app.tools.pr_reviewer import PRReviewer

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("codemind.cli")

def parse_pr_url(url: str) -> dict:
    parts = url.rstrip("/").split("/")
    if len(parts) < 4 or parts[-2] != "pull":
        raise ValueError(f"Invalid PR URL: {url}")
    
    pr_number = int(parts[-1])
    repo = parts[-3]
    owner = parts[-4]
    
    return {
        "owner": owner,
        "repo": repo,
        "pr_number": pr_number,
        "action": "opened",
    }

async def main():
    parser = argparse.ArgumentParser(description="CodeMind CLI Tester")
    parser.add_argument("--pr_url", required=True, help="GitHub PR URL")
    parser.add_argument("command", choices=["review"], help="Command to run")
    parser.add_argument("--level", type=int, choices=[1, 2, 3], help="Optional override for review level (1=Changelog, 2=+Logic, 3=+UnitTest)")
    
    args = parser.parse_args()
    
    if args.command == "review":
        settings = load_settings()
        if not settings.github_token:
            logger.error("GITHUB_TOKEN is not set.")
            sys.exit(1)
            
        if not settings.ai_api_key:
            logger.error("AI_API_KEY is not set.")
            sys.exit(1)
            
        try:
            event_payload = parse_pr_url(args.pr_url)
            if args.level:
                event_payload["level"] = args.level
        except Exception as e:
            logger.error(str(e))
            sys.exit(1)
            
        reviewer = PRReviewer(settings, event_payload)
        await reviewer.run()
        logger.info("Local review execution finished.")

if __name__ == "__main__":
    asyncio.run(main())
