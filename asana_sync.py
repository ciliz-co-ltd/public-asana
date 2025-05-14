import os
import json
import logging
import argparse
import asana
import re
from pprint import pprint
import time
from datetime import datetime
import sys
import utils
import asana_workspace
from typing import List, Dict, Optional, Tuple
from asana.rest import ApiException
from data import Config, PRData, AsanaUser, AsanaProject, AsanaCustomField, AsanaTask

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def log(msg):
    print(f"[Asana] {msg}")

def handle_open(
        asana_ws: asana_workspace.AsanaWorkspace, 
        task: AsanaTask, 
        pr: PRData, 
        reviewers_gids: List[str], 
        latest_sprint_gid: Optional[str], 
        fields_config: Optional[Dict[str, str]], 
        pr_url: str,
        project_sections_mapping: Dict[str, str]):
    print(f"{pr.number}: {pr.title}")
    print(f"Reviewers: {reviewers_gids}")
    print(f"Latest Sprint GID: {latest_sprint_gid}")
    print(f"Fields Config: {fields_config}")
    print(f"PR URL: {pr_url}")
    for assignee in reviewers_gids:
        asana_ws.create_subtask(task, f"pr{pr.number}: {pr.title}", assignee, latest_sprint_gid, fields_config, pr_url, project_sections_mapping)
    log(f"Creating Asana subtasks for reviewers: {pr.reviewers}")
    log(f"PR #{pr.number}: {pr.title} on {pr.platform}")

def handle_closed(asana_ws: asana_workspace.AsanaWorkspace, existing_subtasks: List[AsanaTask], pr: PRData):
    log(f"Closing (discarded) Asana subtasks for reviewers: {pr.reviewers}")
    log(f"tasks: {existing_subtasks}")
    for subtask in existing_subtasks:
        if not subtask.completed:
            try:
                asana_ws.add_comment_to_task(subtask.gid, f"Pull request closed")
                asana_ws.complete_task(subtask.gid)
                log(f"Subtask {subtask.gid} closed with comment: 'pull request closed'")
            except Exception as e:
                log(f"Failed to close subtask {subtask.gid}: {e}")

def handle_updated(
        asana_ws: asana_workspace.AsanaWorkspace, 
        task: AsanaTask,
        to_open_user_gids: List[str], 
        to_close_tasks: List[AsanaTask],
        pr: PRData,
        latest_sprint_gid: Optional[str], 
        fields_config: Optional[Dict[str, str]], 
        pr_url: str,
        project_sections_mapping: Dict[str, str]):
    for assignee in to_open_user_gids:
        asana_ws.create_subtask(task, f"pr{pr.number}: {pr.title}", assignee, latest_sprint_gid, fields_config, pr_url, project_sections_mapping)
    for task in to_close_tasks:
        if not task.completed:
            try:
                asana_ws.add_comment_to_task(task.gid, f"Review request dissmissed")
                asana_ws.complete_task(task.gid)
                log(f"Subtask {task.gid} closed with comment: 'review request dissmissed'")
            except Exception as e:
                log(f"Failed to close subtask {task.gid}: {e}")

def handle_approved(asana_ws: asana_workspace.AsanaWorkspace, task: AsanaTask, pr: PRData):
    if not task.completed:
        try:
            asana_ws.add_comment_to_task(task.gid, f"Pull request approved")
            asana_ws.complete_task(task.gid)
            log(f"Subtask {task.gid} closed with comment: 'pull request closed'")
        except Exception as e:
            log(f"Failed to close subtask {task.gid}: {e}")

def handle_comment(asana_ws: asana_workspace.AsanaWorkspace, task: AsanaTask, pr: PRData):
     if not task.completed:
        try:
            asana_ws.add_comment_to_task(task.gid, f"Changes requested")
            log(f"Subtask {task.gid} closed with comment: 'changes requested'")
        except Exception as e:
            log(f"Failed to close subtask {task.gid}: {e}")

def load_pr_data() -> PRData:
    return PRData(
        number=os.getenv("PR_NUMBER", ""),
        title=os.getenv("PR_TITLE", ""),
        body=os.getenv("PR_BODY", ""),
        platform=os.getenv("PLATFORM", ""),
        reviewers=os.getenv("REVIEWERS", "").split(",") if os.getenv("REVIEWERS") else []
    )

def main():
    if len(sys.argv) < 2:
        print("Usage: asana.py <action>")
        sys.exit(1)

    action = sys.argv[1]
    
    config = utils.load_config()
    
    if not config.token or not config.workspace_gid:
        print("ASANA_TOKEN and ASANA_WORKSPACE_GID must be set.")
        sys.exit(1)

    log(f"Action: {action}")
    log(f"PR #{config.pr.number} Title: {config.pr.title}")
    asana_ws = asana_workspace.AsanaWorkspace(config)
    
    # for user in asana_ws.list_users():
    #     pprint(user)
    
    reviewer_mapping = utils.load_reviewer_mapping()    
    
    body_tasks_urls = utils.extract_asana_task_urls(config.pr.body)
    first_task_url = body_tasks_urls[0]
    task_gid = first_task_url.rstrip('/').split('/')[-1]
    task = asana_ws.get_task_details(task_gid)
    subtasks = [asana_ws.get_task_details(task.gid) for task in task.subtasks]
    log(f"Subtasks: {subtasks}")
    def extract_prs(x):
        st, pr_num = utils.parse_task_title(x.name)
        return (st, pr_num, x)
    parsed_sub_tasks = list(map(extract_prs, subtasks))

    pr_tasks = list(filter(lambda result: result[0], parsed_sub_tasks))
    existing_subtasks = list(map(lambda result: result[2], pr_tasks))

    priority_field = next((cf for cf in task.custom_fields if cf.name == "Priority"), None)
    fields_config = None
    if priority_field:
        if priority_field.enum_value:
            fields_config = { priority_field.gid: priority_field.enum_value["gid"] }
    
    latest_sprint = utils.get_latest_sprint_project(task.projects)
    latest_sprint_gid = None
    project_sections_mapping = None

    if latest_sprint:
        (num, month, day, project) = latest_sprint
        latest_sprint_gid = project.gid

        cf_of_project = asana_ws.list_custom_fields_of_project(project.gid)
        custom_fields_map = { custom_field['name']:custom_field['gid'] for custom_field in cf_of_project }
        # pprint(custom_fields_map)

        # priority_info = asana_ws.get_custom_field_enum_options(custom_fields_map["Priority"])
        # priority_mapping = {opt["name"]: opt["gid"] for opt in priority_info}
        # pprint(priority_mapping)

        project_sections = asana_ws.list_sections_of_project(project.gid)
        project_sections_mapping = { section['name']: section['gid'] for section in project_sections }
        # pprint(project_sections_mapping)

    reviewers_gids = [reviewer_mapping[reviewer] for reviewer in config.pr.reviewers if reviewer in reviewer_mapping]
    print(reviewers_gids)
    
    gid2task = {}   
    for subtask in existing_subtasks:
        if subtask.assignee:
            gid2task[subtask.assignee.gid] = subtask
    
    # Route the action
    if action == "opened":
        gids = []
        for reviewers_gid in reviewers_gids:
            subtask = gid2task.get(reviewers_gid)
            if not subtask:
                gids.append(reviewers_gid)
                
        handle_open(asana_ws, task, config.pr, gids, latest_sprint_gid, fields_config, utils.get_pr_url(), project_sections_mapping)
    elif action == "closed":
        handle_closed(asana_ws, existing_subtasks, config.pr)
    elif action == "updated":
        to_close_tasks = []
        for subtask in existing_subtasks:
            if subtask.assignee and subtask.assignee.gid not in reviewers_gids:
                to_close_tasks.append(subtask)
        to_open_user_gids = []                        
        for reviewers_gid in reviewers_gids:
            subtask = gid2task.get(reviewers_gid)
            if not subtask:
                to_open_user_gids.append(reviewers_gid)
        handle_updated(asana_ws, task, to_open_user_gids, to_close_tasks, config.pr, latest_sprint_gid, fields_config, utils.get_pr_url(), project_sections_mapping)
    elif action == "approved":
        handle_approved(asana_ws, gid2task.get(reviewers_gids[0]), config.pr)
    elif action == "comment":
        handle_comment(asana_ws, gid2task.get(reviewers_gids[0]), config.pr)
    else:
        print(f"Unknown action: {action}")
        sys.exit(1)

if __name__ == "__main__":
    main()