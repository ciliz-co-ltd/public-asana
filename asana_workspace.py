from data import Config, AsanaUser, AsanaTask, AsanaProject, AsanaCustomField
import asana
import logging
from typing import List, Optional, Dict

logger = logging.getLogger(__name__)

class AsanaWorkspace:
    def __init__(self, config: Config):
        self.platform = config.pr.platform
        self.workspace_gid = config.workspace_gid

        configuration = asana.Configuration()
        configuration.access_token = config.token
        api_client = asana.ApiClient(configuration)
        self.users_api = asana.UsersApi(api_client)
        self.tasks_api = asana.TasksApi(api_client)
        self.workspaces_api = asana.WorkspacesApi(api_client)
        self.sections_api = asana.SectionsApi(api_client)
        self.custom_fields_api = asana.CustomFieldsApi(api_client)
        self.projects_api = asana.ProjectsApi(api_client)
        self.stories_api = asana.StoriesApi(api_client)

    def list_users(self) -> List[AsanaUser]:
        try:
            workspace = self.workspaces_api.get_workspace(self.workspace_gid, {})
            users = self.users_api.get_users_for_workspace(workspace["gid"], {"opt_fields": "gid,name,email"})
            return [AsanaUser(gid=u["gid"], name=u.get("name"), email=u.get("email")) for u in users]
        except Exception as e:
            logger.error(f"Exception when listing users: {e}")
            return []

    def complete_task(self, task_gid: str) -> None:
        try:
            self.tasks_api.update_task({"data": {"completed": True}}, task_gid, {})
            logger.info(f"Task {task_gid} marked as completed.")
        except Exception as e:
            logger.error(f"Exception when completing task {task_gid}: {e}")

    def delete_task(self, task_gid: str) -> None:
        try:
            self.tasks_api.delete_task(task_gid)
            logger.info(f"Task {task_gid} deleted.")
        except Exception as e:
            logger.error(f"Exception when deleting task {task_gid}: {e}")

    def create_subtask(
        self,
        task: AsanaTask,
        name: str,
        assignee_gid: Optional[str] = None,
        project_gid: Optional[str] = None,
        custom_fields: Optional[Dict[str, str]] = None,
        description: Optional[str] = None,
        project_sections_mapping: Optional[Dict[str, str]] = None
    ) -> Optional[AsanaTask]:
        parent_task_gid = task.gid
        existing_subtasks = task.subtasks
        try:
            subtask = next(
                (sub for sub in existing_subtasks if sub.name == name and sub.assignee and sub.assignee.gid == assignee_gid),
                None
            )
            if subtask:
                return self.get_task_details(subtask.gid)
            else:
                subtask_data = {"data": {"name": name}}

                if assignee_gid:
                    subtask_data["data"]["assignee"] = assignee_gid
                if project_gid:
                    subtask_data["data"]["projects"] = project_gid
                if custom_fields:
                    subtask_data["data"]["custom_fields"] = custom_fields
                if description:
                    subtask_data["data"]["notes"] = description

                logger.info(f"Created subtask '{name}' under task {parent_task_gid}.")
                response = self.tasks_api.create_subtask_for_task(subtask_data, parent_task_gid, {})
                task = AsanaTask(
                    gid=response["gid"],
                    name=response["name"],
                    assignee=AsanaUser(gid=response["assignee"]["gid"]) if response.get("assignee") else None,
                    projects=[AsanaProject(gid=proj["gid"], name=proj["name"]) for proj in response.get("projects", [])],
                    custom_fields=[
                        AsanaCustomField(name=cf["name"], gid=cf["gid"], enum_value=cf.get("enum_value"))
                        for cf in response.get("custom_fields", [])
                    ]
                )
                self.move_task_to_section(task.gid, project_sections_mapping["Запланировано"])
                return task
        except Exception as e:
            logger.error(f"Exception when creating subtask: {e}")
            return None
    
    def search_task_by_name(self, name: str, assignee_gid: Optional[str] = None) -> List[AsanaTask]:
        search_params = {
            "text": name,
            "opt_fields": ",".join([
                "name",
                "gid",
                "assignee.gid",
                "projects.name",
                "projects.gid",
                "custom_fields.name",
                "custom_fields.enum_value.name",
                "custom_fields.gid"
            ])
        }
        if assignee_gid:
            search_params["assignee.any"] = assignee_gid

        try:
            results = list(self.tasks_api.search_tasks_for_workspace(self.workspace_gid, search_params))
            return [
                AsanaTask(
                    gid=task["gid"],
                    name=task["name"],
                    assignee=AsanaUser(gid=task["assignee"]["gid"]) if task.get("assignee") else None,
                    projects=[AsanaProject(gid=proj["gid"], name=proj["name"]) for proj in task.get("projects", [])],
                    custom_fields=[
                        AsanaCustomField(name=cf["name"], gid=cf["gid"], enum_value=cf.get("enum_value"))
                        for cf in task.get("custom_fields", [])
                    ]
                )
                for task in results
            ]
        except Exception as e:
            logger.error(f"Exception when searching for task by name '{name}': {e}")
            return []
    
    def get_task_details(self, task_gid: str) -> Optional[AsanaTask]:
        fields = [
            "name",
            "gid",
            "assignee.gid",
            "projects.name",
            "projects.gid",
            "custom_fields.name",
            "custom_fields.enum_value.name",
            "custom_fields.gid",
            "completed"
        ]
        try:
            raw = self.tasks_api.get_task(task_gid, {"opt_fields": ",".join(fields)})
            subtasks_raw = self.tasks_api.get_subtasks_for_task(task_gid, {"opt_fields": "name,gid,assignee.gid"})

            subtasks = [
                AsanaTask(
                    gid=st["gid"],
                    name=st["name"],
                    assignee=AsanaUser(gid=st["assignee"]["gid"]) if st.get("assignee") else None
                )
                for st in subtasks_raw
            ]

            return AsanaTask(
                gid=raw["gid"],
                name=raw["name"],
                assignee=AsanaUser(gid=raw["assignee"]["gid"]) if raw.get("assignee") else None,
                projects=[AsanaProject(gid=proj["gid"], name=proj["name"]) for proj in raw.get("projects", [])],
                custom_fields=[
                    AsanaCustomField(name=cf["name"], gid=cf["gid"] , enum_value=cf.get("enum_value"))
                    for cf in raw.get("custom_fields", [])
                ],
                subtasks=subtasks,
                completed=raw.get("completed", False)
            )
        except Exception as e:
            logger.error(f"Exception when retrieving task details for {task_gid}: {e}")
            return None
        
    def get_custom_field_enum_options(self, custom_field_gid: str) -> List[Dict[str, str]]:
        try:
            field = self.custom_fields_api.get_custom_field(
                custom_field_gid, {"opt_fields": "enum_options.name"}
            )
            return [{"gid": opt["gid"], "name": opt["name"]} for opt in field.get("enum_options", [])]
        except Exception as e:
            logger.error(f"Error fetching enum options for custom field {custom_field_gid}: {e}")
            return []
    
    def move_task_to_section(self, task_gid: str, section_gid: str) -> bool:
        try:
            opts = {
                'body': {
                    "data": {
                        "task": task_gid
                    }
                }
            }
            self.sections_api.add_task_for_section(section_gid, opts)
            logger.info(f"Moved task {task_gid} to section {section_gid}.")
            return True
        except Exception as e:
            logger.error(f"Failed to move task {task_gid} to section {section_gid}: {e}")
            return False

    def list_sections_of_project(self, project_gid: str) -> List[Dict[str, str]]:
        try:
            sections = self.sections_api.get_sections_for_project(project_gid, {})
            return [{"gid": section["gid"], "name": section["name"]} for section in sections]
        except Exception as e:
            logger.error(f"Error listing sections for project {project_gid}: {e}")
            return []

    def list_custom_fields_of_project(self, project_gid: str) -> List[Dict[str, str]]:
        try:
            project = self.projects_api.get_project(
                project_gid, {"opt_fields": "custom_field_settings.custom_field"}
            )
            settings = project.get("custom_field_settings", [])
            return [
                {
                    "gid": setting["custom_field"]["gid"],
                    "name": setting["custom_field"]["name"]
                }
                for setting in settings if "custom_field" in setting
            ]
        except Exception as e:
            logger.error(f"Error fetching custom fields for project {project_gid}: {e}")
            return []

    def add_comment_to_task(self, task_gid: str, comment: str) -> bool:
        try:
            body = {"data": {"text": comment}}
            opts = {}  # Optional parameters can be added here if needed
            self.stories_api.create_story_for_task(body, task_gid, opts)
            logger.info(f"Added comment to task {task_gid}: {comment}")
            return True
        except Exception as e:
            logger.error(f"Failed to add comment to task {task_gid}: {e}")
            return False