import os
import json
import re
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from data import Config, PRData, AsanaProject
from dotenv import load_dotenv

import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)


def load_config() -> Config:
    load_dotenv(dotenv_path=".env.test")

    token = os.getenv('ASANA_TOKEN')
    workspace_gid = os.getenv('ASANA_WORKSPACE_GID')
    pr_number = os.getenv('PR_NUMBER')
    pr_title = os.getenv('PR_TITLE')
    pr_body = os.getenv('PR_BODY')
    pr_reviewers_raw = os.getenv('REVIEWERS')
    platform = os.getenv('PLATFORM')

    missing = []
    if not token: missing.append('ASANA_TOKEN')
    if not workspace_gid: missing.append('ASANA_WORKSPACE_GID')
    if not pr_number: missing.append('PR_NUMBER')
    if not pr_title: missing.append('PR_TITLE')
    if not pr_body: missing.append('PR_BODY')
    if not pr_reviewers_raw: missing.append('REVIEWERS')
    if not platform: missing.append('PLATFORM')

    if missing:
        logger.error(f"Missing required environment variables: {', '.join(missing)}")
        raise EnvironmentError("Missing required environment variables")

    pr_reviewers = pr_reviewers_raw.split(',')


    return Config(
        token=token,
        workspace_gid=workspace_gid,
        pr=PRData(number=pr_number, title=pr_title, body=pr_body, platform=platform, reviewers=pr_reviewers)
    )


def load_reviewer_mapping() -> Dict:
    raw = os.getenv("REVIEWERS_GIDS")
    if not raw:
        logger.warning("REVIEWERS_GIDS environment variable is not set.")
        return {}

    try:
        return json.loads(raw)
    except Exception as e:
        logger.error(f"Error parsing REVIEWERS_GIDS from environment: {e}")
        raise


def get_pr_url() -> str:
    url = os.getenv("PR_URL")
    if url:
        return url
    return ""


def extract_asana_task_urls(pr_description: str) -> List[str]:
    pattern = re.compile(r"https://app\.asana\.com/\d+/\d+/project/\d+/task/\d+")
    matches = pattern.findall(pr_description)
    logger.debug(f"Extracted {len(matches)} Asana task URL(s).")
    return matches


def extract_project_gid(url: str) -> str:
    match = re.search(r"/project/(\d+)/task/\d+", url)
    if match:
        return match.group(1)
    return ""


def parse_sprint_info(name: str) -> Optional[Tuple[int, datetime, datetime]]:
    pattern = r"Sprint\s+(\d+)\s+\((\d{2}\.\d{2})-(\d{2}\.\d{2})\)"
    match = re.search(pattern, name)

    if not match:
        return None

    sprint_number = int(match.group(1))
    start_str = match.group(2)
    end_str = match.group(3)

    current_year = datetime.now().year
    start_date = datetime.strptime(f"{start_str}.{current_year}", "%d.%m.%Y")
    end_date = datetime.strptime(f"{end_str}.{current_year}", "%d.%m.%Y")

    # Adjust year if end date is before start (spanning December–January)
    if end_date < start_date:
        end_date = end_date.replace(year=end_date.year + 1)

    return sprint_number, start_date, end_date


def get_latest_sprint_project(projects: List[AsanaProject]) -> Optional[Tuple[int, datetime, datetime, AsanaProject]]:
    parsed_projects = []

    for project in projects:
        parsed = parse_sprint_info(project.name)
        if parsed:
            sprint_number, start, end = parsed
            parsed_projects.append((sprint_number, start, end, project))

    if not parsed_projects:
        return None

    return max(parsed_projects, key=lambda x: x[0])


def parse_task_title(title: str) -> (bool, Optional[int]):
    pattern = r'^pr(\d+): .+$'
    match = re.match(pattern, title)
    if match:
        pr_number = match.group(1)
        return True, pr_number
    return False, None
