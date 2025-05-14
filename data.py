from dataclasses import dataclass, field
from pydantic import BaseModel
from typing import List, Dict, Optional, Tuple

@dataclass
class PRData:
    number: str
    title: str
    body: str
    platform: str
    reviewers: list[str]


class Config(BaseModel):
    token: str
    workspace_gid: str
    pr: PRData
    
@dataclass
class AsanaUser:
    gid: str
    name: Optional[str] = None
    email: Optional[str] = None


@dataclass
class AsanaProject:
    gid: str
    name: str


@dataclass
class AsanaCustomField:
    name: str
    gid: Optional[str]
    enum_value: Optional[dict] 

@dataclass
class AsanaTask:
    gid: str
    name: Optional[str]
    assignee: Optional[AsanaUser]
    projects: Optional[List[AsanaProject]] = field(default_factory=list)
    custom_fields: Optional[List[AsanaCustomField]] = field(default_factory=list)
    subtasks: Optional[List["AsanaTask"]] = field(default_factory=list)
    completed: Optional[bool] = None