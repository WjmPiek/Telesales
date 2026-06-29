from functools import wraps
from flask import abort
from flask_login import current_user


def permission_required(code):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if not current_user.is_authenticated or not current_user.has_permission(code):
                abort(403)
            return fn(*args, **kwargs)
        return wrapper
    return decorator

# PHASE 10+ ROLE PORTAL HELPERS
def normalized_role_name(user=None):
    try:
        from flask_login import current_user
        user = user or current_user
        role = getattr(user, "role", None)
        return (role.name if role else "").lower().replace("_", " ").strip()
    except Exception:
        return ""

def is_super_admin_user(user=None):
    try:
        from flask_login import current_user
        user = user or current_user
        email = ((getattr(user, "email", "") or "").lower().strip())
    except Exception:
        email = ""
    return normalized_role_name(user) in {"super admin", "super_admin"} or email == "wjm@martinsdirect.com"

def is_admin_user(user=None):
    return normalized_role_name(user) in {"admin", "super admin", "super_admin"} or is_super_admin_user(user)

def is_branch_manager_user(user=None):
    return normalized_role_name(user) in {"branch manager", "branchmanager", "manager", "supervisor"}

def is_agent_user(user=None):
    return normalized_role_name(user) in {"agent", "user", "staff", "sales agent"}

def role_home_endpoint(user=None):
    role = normalized_role_name(user)
    if role in {"admin", "super admin", "super_admin", "branch manager", "branchmanager", "manager", "supervisor", "agent", "user", "staff", "sales agent"}:
        return "role_portals.workspace"
    return "main.dashboard"

def require_admin():
    from flask import flash, redirect, url_for
    if not is_admin_user():
        flash("Admin access required.", "danger")
        return redirect(url_for(role_home_endpoint()))
    return None

def require_manager_or_admin():
    from flask import flash, redirect, url_for
    if not (is_admin_user() or is_branch_manager_user()):
        flash("Manager access required.", "danger")
        return redirect(url_for(role_home_endpoint()))
    return None
