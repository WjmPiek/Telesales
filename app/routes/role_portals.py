
from datetime import date, datetime, time
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from app import db
from app.models import User, LapsedPolicy, RecoveryCallLog, ClientApplication, ClientFicaDocument, TelesalesScriptSession, AuditLog
from app.security import is_admin_user, is_branch_manager_user, is_agent_user, role_home_endpoint, require_admin, require_manager_or_admin
from app.services.branch_access import scope_by_branch, selected_branch_arg, branch_choices_from_model, user_branch

role_portals_bp = Blueprint("role_portals", __name__)

def _today_bounds():
    today = date.today()
    return datetime.combine(today, time.min), datetime.combine(today, time.max)

def _base_stats(branch=None, agent_id=None):
    start, end = _today_bounds()
    leads = LapsedPolicy.query
    apps = ClientApplication.query
    calls = RecoveryCallLog.query
    scripts = TelesalesScriptSession.query
    docs = ClientFicaDocument.query.join(ClientApplication, ClientFicaDocument.application_id == ClientApplication.id)
    if branch:
        leads = leads.filter(LapsedPolicy.branch == branch)
        apps = apps.filter(ClientApplication.branch == branch)
        scripts = scripts.filter(TelesalesScriptSession.branch == branch)
        docs = docs.filter(ClientApplication.branch == branch)
    if agent_id:
        leads = leads.filter(LapsedPolicy.assigned_agent_id == agent_id)
        apps = apps.filter(ClientApplication.agent_id == agent_id)
        calls = calls.filter(RecoveryCallLog.agent_id == agent_id)
        scripts = scripts.filter(TelesalesScriptSession.agent_id == agent_id)
        docs = docs.filter(ClientApplication.agent_id == agent_id)
    return {
        "leads": leads.count(),
        "calls_today": calls.filter(RecoveryCallLog.created_at >= start, RecoveryCallLog.created_at <= end).count(),
        "sales_today": apps.filter(ClientApplication.created_at >= start, ClientApplication.created_at <= end).count(),
        "callbacks_today": leads.filter(LapsedPolicy.recovery_status == "Callback", LapsedPolicy.next_action_date == date.today()).count(),
        "callbacks_overdue": leads.filter(LapsedPolicy.recovery_status == "Callback", LapsedPolicy.next_action_date < date.today()).count(),
        "pending_signatures": apps.filter(ClientApplication.signed_at.is_(None)).count(),
        "fica_outstanding": docs.filter(ClientFicaDocument.status.in_(["Received", "Rejected"])).count(),
        "qa_pending": scripts.filter(TelesalesScriptSession.status == "Completed", TelesalesScriptSession.qa_result.is_(None)).count(),
    }

@role_portals_bp.route("/home")
@login_required
def home():
    return redirect(url_for(role_home_endpoint()))

@role_portals_bp.route("/admin")
@login_required
def admin_home():
    blocked = require_admin()
    if blocked: return blocked
    branch = selected_branch_arg()
    stats = _base_stats(branch=branch)
    branches = branch_choices_from_model(db, LapsedPolicy)
    agents = User.query.order_by(User.branch.asc(), User.name.asc()).all()
    if branch:
        agents = [a for a in agents if a.branch == branch]
    recent_audit = AuditLog.query.order_by(AuditLog.created_at.desc()).limit(10).all()
    return render_template("role_portals/admin.html", stats=stats, branches=branches, active_branch=branch, agents=agents, recent_audit=recent_audit)

@role_portals_bp.route("/branch-manager")
@login_required
def branch_manager_home():
    blocked = require_manager_or_admin()
    if blocked: return blocked
    branch = selected_branch_arg() if is_admin_user() else user_branch()
    if not branch:
        branch = user_branch()
    stats = _base_stats(branch=branch)
    start, end = _today_bounds()
    agents = User.query.filter(User.branch == branch).order_by(User.name.asc()).all() if branch else []
    agent_rows = []
    for a in agents:
        calls = RecoveryCallLog.query.filter(RecoveryCallLog.agent_id == a.id, RecoveryCallLog.created_at >= start, RecoveryCallLog.created_at <= end).count()
        apps = ClientApplication.query.filter(ClientApplication.agent_id == a.id, ClientApplication.created_at >= start, ClientApplication.created_at <= end).count()
        agent_rows.append({"agent": a, "calls": calls, "sales": apps, "conversion": round(apps / calls * 100, 1) if calls else 0})
    pending_callbacks = LapsedPolicy.query.filter(LapsedPolicy.branch == branch, LapsedPolicy.recovery_status == "Callback").order_by(LapsedPolicy.next_action_date.asc()).limit(10).all() if branch else []
    return render_template("role_portals/branch_manager.html", stats=stats, branch=branch, agent_rows=agent_rows, pending_callbacks=pending_callbacks)

@role_portals_bp.route("/agent")
@login_required
def agent_home():
    if not (is_agent_user() or is_admin_user() or is_branch_manager_user()):
        flash("Agent access required.", "danger")
        return redirect(url_for("main.dashboard"))
    agent_id = current_user.id if is_agent_user() else request.args.get("agent_id", type=int)
    if not agent_id:
        agent_id = current_user.id
    stats = _base_stats(agent_id=agent_id)
    callbacks = LapsedPolicy.query.filter(LapsedPolicy.assigned_agent_id == agent_id, LapsedPolicy.recovery_status == "Callback").order_by(LapsedPolicy.next_action_date.asc()).limit(10).all()
    my_apps = ClientApplication.query.filter(ClientApplication.agent_id == agent_id).order_by(ClientApplication.created_at.desc()).limit(10).all()
    return render_template("role_portals/agent.html", stats=stats, callbacks=callbacks, my_apps=my_apps)
