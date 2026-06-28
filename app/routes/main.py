from datetime import date, datetime, time
from flask import Blueprint, render_template, redirect, url_for, request
from flask_login import login_required, current_user
from app import db
from app.models import ClientApplication, LapsedPolicy, RecoveryCallLog, PolicyProduct, User, TelesalesScriptSession, ClientFicaDocument, ComplianceReview

main_bp = Blueprint("main", __name__)

@main_bp.route("/")
@login_required
def dashboard():
    today = date.today()
    open_statuses = ["New", "Imported", "Called", "No Answer", "Callback", "Interested", "Application Started", "Signature Sent", "FICA Outstanding", "QA Review"]
    stats = {
        "applications": ClientApplication.query.count(),
        "products": PolicyProduct.query.count(),
        "lapsed": LapsedPolicy.query.count(),
        "calls": RecoveryCallLog.query.count(),
        "calls_today": RecoveryCallLog.query.filter(RecoveryCallLog.agent_id == current_user.id, RecoveryCallLog.created_at >= today).count(),
        "callbacks_today": LapsedPolicy.query.filter(LapsedPolicy.recovery_status == "Callback", LapsedPolicy.next_action_date == today).count(),
        "callbacks_overdue": LapsedPolicy.query.filter(LapsedPolicy.recovery_status == "Callback", LapsedPolicy.next_action_date < today).count(),
        "due_now": LapsedPolicy.query.filter(LapsedPolicy.recovery_status.in_(open_statuses), LapsedPolicy.next_action_date <= today).count(),
        "interested": LapsedPolicy.query.filter(LapsedPolicy.recovery_status == "Interested").count(),
        "applications_started": LapsedPolicy.query.filter(LapsedPolicy.recovery_status == "Application Started").count(),
    }
    todays_calls = RecoveryCallLog.query.filter(RecoveryCallLog.agent_id == current_user.id, RecoveryCallLog.created_at >= today).order_by(RecoveryCallLog.created_at.desc()).limit(10).all()
    return render_template("dashboard/index.html", stats=stats, todays_calls=todays_calls)


@main_bp.route("/login")
def login_alias():
    return redirect(url_for("auth.login"))


def _is_manager_user():
    role_name = (current_user.role.name if current_user.is_authenticated and current_user.role else "").lower().replace("_", " ")
    return role_name in {"admin", "manager", "branch manager"}


def _today_bounds():
    today = date.today()
    return datetime.combine(today, time.min), datetime.combine(today, time.max)


def _manager_scope(query):
    if not _is_manager_user():
        return query.filter(RecoveryCallLog.agent_id == current_user.id)
    return query


@main_bp.route("/manager")
@login_required
def manager_dashboard():
    """Phase 3 manager dashboard built from existing tables only. No schema changes required."""
    if not _is_manager_user():
        return redirect(url_for("main.dashboard"))

    start, end = _today_bounds()
    branch = request.args.get("branch") or ""

    lead_query = LapsedPolicy.query
    app_query = ClientApplication.query
    call_query = RecoveryCallLog.query
    script_query = TelesalesScriptSession.query
    fica_query = ClientFicaDocument.query.join(ClientApplication, ClientFicaDocument.application_id == ClientApplication.id)

    if branch:
        lead_query = lead_query.filter(LapsedPolicy.branch == branch)
        app_query = app_query.filter(ClientApplication.branch == branch)
        script_query = script_query.filter(TelesalesScriptSession.branch == branch)
        fica_query = fica_query.filter(ClientApplication.branch == branch)

    open_statuses = ["New", "Imported", "Called", "No Answer", "Callback", "Interested", "Application Started", "Signature Sent", "FICA Outstanding", "QA Review"]
    pending_signature_statuses = ["Draft", "Pending Signature", "Signature Sent"]
    pending_qa_statuses = ["QA Review", "Application Started"]

    stats = {
        "total_leads": lead_query.count(),
        "open_leads": lead_query.filter(LapsedPolicy.recovery_status.in_(open_statuses)).count(),
        "calls_today": call_query.filter(RecoveryCallLog.created_at >= start, RecoveryCallLog.created_at <= end).count(),
        "callbacks_today": lead_query.filter(LapsedPolicy.recovery_status == "Callback", LapsedPolicy.next_action_date == date.today()).count(),
        "callbacks_overdue": lead_query.filter(LapsedPolicy.recovery_status == "Callback", LapsedPolicy.next_action_date < date.today()).count(),
        "interested": lead_query.filter(LapsedPolicy.recovery_status == "Interested").count(),
        "applications_started": lead_query.filter(LapsedPolicy.recovery_status == "Application Started").count(),
        "signature_pending": app_query.filter(ClientApplication.status.in_(pending_signature_statuses), ClientApplication.signed_at.is_(None)).count(),
        "qa_pending": lead_query.filter(LapsedPolicy.recovery_status.in_(pending_qa_statuses)).count() + script_query.filter(TelesalesScriptSession.status == "Completed", TelesalesScriptSession.qa_result.is_(None)).count(),
        "compliance_reviews": ComplianceReview.query.count(),
        "fica_received": fica_query.filter(ClientFicaDocument.status == "Received").count(),
        "approved": lead_query.filter(LapsedPolicy.recovery_status.in_(["Approved", "Reinstated"])).count(),
        "rejected": lead_query.filter(LapsedPolicy.recovery_status == "Rejected").count(),
    }
    stats["conversion_rate"] = round((stats["approved"] / stats["total_leads"] * 100), 1) if stats["total_leads"] else 0

    agent_rows = db.session.query(
        User.id, User.name, User.branch,
        db.func.count(RecoveryCallLog.id).label("calls"),
        db.func.sum(db.case((RecoveryCallLog.outcome.in_(["Wants Reinstatement", "Wants New Policy", "Application Started", "Signature Sent"]), 1), else_=0)).label("sales_actions"),
        db.func.sum(db.case((RecoveryCallLog.outcome.in_(["No Answer", "Voicemail"]), 1), else_=0)).label("no_answers"),
    ).outerjoin(RecoveryCallLog, db.and_(RecoveryCallLog.agent_id == User.id, RecoveryCallLog.created_at >= start, RecoveryCallLog.created_at <= end))
    if branch:
        agent_rows = agent_rows.filter(User.branch == branch)
    agent_rows = agent_rows.group_by(User.id, User.name, User.branch).order_by(db.desc("calls"), User.name.asc()).all()

    agents = []
    for row in agent_rows:
        conversion = round((int(row.sales_actions or 0) / int(row.calls or 0) * 100), 1) if row.calls else 0
        agents.append({"id": row.id, "name": row.name, "branch": row.branch, "calls": int(row.calls or 0), "sales_actions": int(row.sales_actions or 0), "no_answers": int(row.no_answers or 0), "conversion": conversion})

    status_counts = db.session.query(LapsedPolicy.recovery_status, db.func.count(LapsedPolicy.id)).group_by(LapsedPolicy.recovery_status).order_by(db.func.count(LapsedPolicy.id).desc()).all()
    if branch:
        status_counts = db.session.query(LapsedPolicy.recovery_status, db.func.count(LapsedPolicy.id)).filter(LapsedPolicy.branch == branch).group_by(LapsedPolicy.recovery_status).order_by(db.func.count(LapsedPolicy.id).desc()).all()

    pending_work = {
        "overdue_callbacks": lead_query.filter(LapsedPolicy.recovery_status == "Callback", LapsedPolicy.next_action_date < date.today()).order_by(LapsedPolicy.next_action_date.asc()).limit(10).all(),
        "today_callbacks": lead_query.filter(LapsedPolicy.recovery_status == "Callback", LapsedPolicy.next_action_date == date.today()).order_by(LapsedPolicy.imported_at.asc()).limit(10).all(),
        "signature_pending": app_query.filter(ClientApplication.signed_at.is_(None)).order_by(ClientApplication.created_at.asc()).limit(10).all(),
        "fica_received": fica_query.filter(ClientFicaDocument.status == "Received").order_by(ClientFicaDocument.uploaded_at.asc()).limit(10).all(),
        "qa_pending": lead_query.filter(LapsedPolicy.recovery_status == "QA Review").order_by(LapsedPolicy.imported_at.asc()).limit(10).all(),
        "recent_reviews": ComplianceReview.query.order_by(ComplianceReview.created_at.desc()).limit(5).all(),
    }

    branches = [r[0] for r in db.session.query(LapsedPolicy.branch).filter(LapsedPolicy.branch.isnot(None)).distinct().order_by(LapsedPolicy.branch.asc()).all() if r[0]]

    return render_template("dashboard/manager.html", stats=stats, agents=agents, status_counts=status_counts, pending_work=pending_work, branches=branches, active_branch=branch)
