import logging
import sys
import utils
from asana_workspace import AsanaWorkspace
from typing import List, Dict, Optional
from data import PRData, AsanaTask

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)


def handle_open(
        asana_ws: AsanaWorkspace,
        task: AsanaTask,
        pr: PRData,
        reviewers_gids: List[str],
        latest_sprint_gid: Optional[str],
        fields_config: Optional[Dict[str, str]],
        pr_url: str,
        project_sections_mapping: Dict[str, str]):
    for assignee in reviewers_gids:
        asana_ws.create_subtask(task, f"pr{pr.number}: {pr.title}", assignee, latest_sprint_gid, fields_config, pr_url,
                                project_sections_mapping)
    logger.info(
        f"[OPEN] PR #{pr.number} '{pr.title}' – Created subtasks for reviewers: {reviewers_gids}, Sprint: {latest_sprint_gid}, Fields: {fields_config}, URL: {pr_url}")


def handle_closed(asana_ws: AsanaWorkspace, existing_subtasks: List[AsanaTask], pr: PRData):
    closed = []
    for subtask in existing_subtasks:
        if not subtask.completed:
            asana_ws.add_comment_to_task(subtask.gid, "Pull request closed")
            asana_ws.complete_task(subtask.gid)
            closed.append(subtask.gid)
    logger.info(f"[CLOSED] PR #{pr.number} – Closed subtasks: {closed}")


def handle_updated(
        asana_ws: AsanaWorkspace,
        task: AsanaTask,
        to_open_user_gids: List[str],
        to_close_tasks: List[AsanaTask],
        pr: PRData,
        latest_sprint_gid: Optional[str],
        fields_config: Optional[Dict[str, str]],
        pr_url: str,
        project_sections_mapping: Dict[str, str]):
    opened = []
    closed = []

    for assignee in to_open_user_gids:
        asana_ws.create_subtask(
            task,
            f"pr{pr.number}: {pr.title}",
            assignee,
            latest_sprint_gid,
            fields_config,
            pr_url,
            project_sections_mapping
        )
        opened.append(assignee)

    for subtask in to_close_tasks:
        if not subtask.completed:
            asana_ws.add_comment_to_task(subtask.gid, "Review request dismissed")
            asana_ws.complete_task(subtask.gid)
            closed.append(subtask.gid)

    logger.info(
        f"[UPDATED] PR #{pr.number} – Title: '{pr.title}'\n"
        f"Opened reviewer GIDs: {opened}\n"
        f"Closed subtask GIDs: {closed}\n"
        f"PR URL: {pr_url}\n"
        f"Fields Config: {fields_config}\n"
        f"Latest Sprint GID: {latest_sprint_gid}\n"
        f"Project Sections Mapping: {project_sections_mapping}"
    )


def handle_approved(asana_ws: AsanaWorkspace, task: AsanaTask, pr: PRData):
    result = "skipped"
    if not task.completed:
        asana_ws.add_comment_to_task(task.gid, "Pull request approved")
        asana_ws.complete_task(task.gid)
        result = "completed"
    logger.info(f"[APPROVED] PR #{pr.number} – Task {task.gid} {result}")


def handle_comment(asana_ws: AsanaWorkspace, task: AsanaTask, pr: PRData):
    result = "skipped"
    if not task.completed:
        asana_ws.add_comment_to_task(task.gid, "Changes requested")
        result = "commented"
    logger.info(f"[COMMENT] PR #{pr.number} – Task {task.gid if task else 'N/A'} {result}")


def get_cli_action() -> str:
    if len(sys.argv) < 2:
        logger.error("Usage: asana.py <action>")
        sys.exit(1)
    return sys.argv[1]


def validate_and_load_config():
    config = utils.load_config()
    if not config.token or not config.workspace_gid:
        logger.error("ASANA_TOKEN and ASANA_WORKSPACE_GID must be set.")
        sys.exit(1)
    return config


def resolve_root_task(asana_ws: AsanaWorkspace, config) -> AsanaTask | None:
    task_urls = utils.extract_asana_task_urls(config.pr.body)
    if not task_urls:
        logger.error("No Asana task URL found in PR body.")
        return None
    task_gid = task_urls[0].rstrip('/').split('/')[-1]
    return asana_ws.get_task_details(task_gid)


def extract_existing_subtasks(subtasks: List[AsanaTask], pr_number: str) -> List[AsanaTask]:
    def extract_prs(st):
        matched, pr_num = utils.parse_task_title(st.name)
        return (matched, pr_num, st)

    parsed = map(extract_prs, subtasks)
    return [st for matched, pr_num, st in parsed if matched and pr_num == pr_number]


def resolve_field_config(asana_ws: AsanaWorkspace, task: AsanaTask):
    priority_field = next((cf for cf in task.custom_fields if cf.name == "Priority"), None)
    fields_config = {
        priority_field.gid: priority_field.enum_value["gid"]} if priority_field and priority_field.enum_value else None

    latest_sprint_data = utils.get_latest_sprint_project(task.projects)
    if not latest_sprint_data:
        return fields_config, None, None

    _, _, _, project = latest_sprint_data
    custom_fields = {cf['name']: cf['gid'] for cf in asana_ws.list_custom_fields_of_project(project.gid)}
    section_map = {s['name']: s['gid'] for s in asana_ws.list_sections_of_project(project.gid)}
    return fields_config, project.gid, section_map


def resolve_reviewers(config) -> List[str]:
    reviewer_mapping = utils.load_reviewer_mapping()
    return [reviewer_mapping[r] for r in config.pr.reviewers if r in reviewer_mapping]


def dispatch_action(action: str, context: Dict):
    if action == "opened":
        gids_to_open = [gid for gid in context['reviewers_gids'] if gid not in context['gid2task']]
        handle_open(context['asana_ws'], context['root_task'], context['config'].pr, gids_to_open,
                    context['latest_sprint_gid'], context['field_config'], utils.get_pr_url(), context['section_map'])
    elif action == "closed":
        handle_closed(context['asana_ws'], context['existing_subtasks'], context['config'].pr)
    elif action == "updated":
        to_close = [st for st in context['existing_subtasks'] if
                    st.assignee and st.assignee.gid not in context['reviewers_gids']]
        to_open = [gid for gid in context['reviewers_gids'] if gid not in context['gid2task']]
        handle_updated(context['asana_ws'], context['root_task'], to_open, to_close, context['config'].pr,
                       context['latest_sprint_gid'], context['field_config'], utils.get_pr_url(),
                       context['section_map'])
    elif action == "approved":
        first_gid = context['reviewers_gids'][0] if context['reviewers_gids'] else None
        handle_approved(context['asana_ws'], context['gid2task'].get(first_gid), context['config'].pr)
    elif action == "comment":
        first_gid = context['reviewers_gids'][0] if context['reviewers_gids'] else None
        handle_comment(context['asana_ws'], context['gid2task'].get(first_gid), context['config'].pr)
    else:
        logger.error(f"Unknown action: {action}")
        sys.exit(1)


def main():
    action = get_cli_action()
    config = validate_and_load_config()
    logger.info(f"Action: {action}\nPR #{config.pr.number} Title: {config.pr.title}")

    asana_ws = AsanaWorkspace(config)
    root_task = resolve_root_task(asana_ws, config)
    if root_task is None:
        logger.info("No tasks found in body")
        return
    subtasks = [asana_ws.get_task_details(st.gid) for st in root_task.subtasks]
    existing_subtasks = extract_existing_subtasks(subtasks, config.pr.number)

    field_config, latest_sprint_gid, section_map = resolve_field_config(asana_ws, root_task)
    reviewers_gids = resolve_reviewers(config)
    gid2task = {st.assignee.gid: st for st in existing_subtasks if st.assignee}

    dispatch_action(action, {
        "asana_ws": asana_ws,
        "root_task": root_task,
        "existing_subtasks": existing_subtasks,
        "reviewers_gids": reviewers_gids,
        "gid2task": gid2task,
        "config": config,
        "field_config": field_config,
        "latest_sprint_gid": latest_sprint_gid,
        "section_map": section_map,
    })


if __name__ == "__main__":
    main()
