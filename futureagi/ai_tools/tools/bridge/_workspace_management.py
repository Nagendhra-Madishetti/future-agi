"""Bridge registration for accounts APIViews.

WorkspaceListAPIView and UserListAPIView are plain APIViews. Names and
descriptions are derived automatically:
  - WorkspaceListAPIView → entity 'workspace' → tool 'list_workspaces'
    (description from WorkspaceListRequestSerializer.__doc__)
  - UserListAPIView      → entity 'user'      → tool 'list_users'
    (description from UserListRequestSerializer.__doc__)
"""

from accounts.views.workspace_management import (
    UserListAPIView,
    WorkspaceListAPIView,
)
from ai_tools.drf_bridge import expose_to_mcp

expose_to_mcp(category="users", tools=["get"])(WorkspaceListAPIView)
expose_to_mcp(category="users", tools=["get"])(UserListAPIView)
