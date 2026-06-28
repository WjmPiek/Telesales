import json
from datetime import date
from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_required, current_user
from app import db
from app.models import ClientApplication, ClientFicaDocument, ComplianceReview, LapsedPolicy, TelesalesScriptSession, AuditLog

qa_bp = Blueprint('qa', __name__, url_prefix='/qa')

QA_CHECKLIST = [
    ('popia_confirmed', 'POPIA confirmed'),
    ('product_explained', 'Product and benefits explained'),
    ('premium_confirmed', 'Premium, joining fee and debit day confirmed'),
    ('waiting_periods', 'Waiting periods and exclusions explained'),
    ('debit_order', 'Debit order authority confirmed'),
    ('beneficiary', 'Beneficiary captured/confirmed'),
    ('signature_complete', 'Client signed required documents'),
    ('fica_complete', 'Required FICA documents received'),
    ('contact_details', 'Client contact details verified'),
    ('no_red_flags', 'No unresolved red flags or complaints'),
]

def _role_name():
    return str(getattr(getattr(current_user, 'role', None), 'name', '') or '').lower().replace('_', ' ')

def _is_qa_user():
    return _role_name() in {'admin', 'manager', 'branch manager', 'compliance', 'qa'}

def _branch_scope(query, model):
    branch = request.args.get('branch') or ''
    if branch and hasattr(model, 'branch'):
        query = query.filter(model.branch == branch)
    return query, branch

def _app_client_name(app):
    return ' '.join([x for x in [app.first_names, app.surname] if x]) or app.application_ref

def _latest_script(app):
    q = TelesalesScriptSession.query
    if app.id:
        q = q.filter(TelesalesScriptSession.application_id == app.id)
    if app.lapsed_policy_id:
        q = q.union(TelesalesScriptSession.query.filter(TelesalesScriptSession.lapsed_policy_id == app.lapsed_policy_id))
    try:
        return q.order_by(TelesalesScriptSession.completed_at.desc().nullslast(), TelesalesScriptSession.created_at.desc()).first()
    except Exception:
        return TelesalesScriptSession.query.filter_by(application_id=app.id).order_by(TelesalesScriptSession.created_at.desc()).first()

def _fica_summary(app):
    docs = ClientFicaDocument.query.filter_by(application_id=app.id).order_by(ClientFicaDocument.uploaded_at.desc()).all()
    received = [d for d in docs if d.status != 'Rejected']
    return docs, len(received)

@qa_bp.route('/')
@login_required
def qa_dashboard():
    if not _is_qa_user():
        flash('Only managers/compliance users can access QA.', 'danger')
        return redirect(url_for('main.dashboard'))

    branch = request.args.get('branch') or ''
    app_q = ClientApplication.query
    lead_q = LapsedPolicy.query
    if branch:
        app_q = app_q.filter(ClientApplication.branch == branch)
        lead_q = lead_q.filter(LapsedPolicy.branch == branch)

    qa_statuses = ['Signed', 'QA Review', 'QA Pending', 'Application Started', 'Signing Link Sent', 'Signing Link Prepared']
    qa_apps = app_q.filter(ClientApplication.status.in_(qa_statuses)).order_by(ClientApplication.updated_at.desc()).limit(50).all()
    signed_apps = app_q.filter(ClientApplication.signed_at.isnot(None), ClientApplication.status.notin_(['Compliance Approved', 'Compliance Rejected', 'QA Rejected'])).order_by(ClientApplication.signed_at.asc()).limit(50).all()
    fica_docs = ClientFicaDocument.query.join(ClientApplication, ClientFicaDocument.application_id == ClientApplication.id).filter(ClientFicaDocument.status == 'Received')
    if branch:
        fica_docs = fica_docs.filter(ClientApplication.branch == branch)
    fica_docs = fica_docs.order_by(ClientFicaDocument.uploaded_at.asc()).limit(50).all()
    recent_reviews = ComplianceReview.query.order_by(ComplianceReview.created_at.desc()).limit(20).all()

    stats = {
        'qa_pending': len(qa_apps),
        'signed_pending': len(signed_apps),
        'fica_to_review': len(fica_docs),
        'approved_today': ComplianceReview.query.filter(ComplianceReview.decision.in_(['QA Approved', 'Compliance Approved']), db.func.date(ComplianceReview.created_at) == date.today()).count(),
        'rejected_today': ComplianceReview.query.filter(ComplianceReview.decision.in_(['QA Rejected', 'Compliance Rejected']), db.func.date(ComplianceReview.created_at) == date.today()).count(),
    }
    branches = [r[0] for r in db.session.query(ClientApplication.branch).filter(ClientApplication.branch.isnot(None)).distinct().order_by(ClientApplication.branch.asc()).all() if r[0]]
    return render_template('qa/dashboard.html', qa_apps=qa_apps, signed_apps=signed_apps, fica_docs=fica_docs, recent_reviews=recent_reviews, stats=stats, branches=branches, active_branch=branch)

@qa_bp.route('/application/<int:app_id>', methods=['GET', 'POST'])
@login_required
def review_application(app_id):
    if not _is_qa_user():
        flash('Only managers/compliance users can access QA.', 'danger')
        return redirect(url_for('main.dashboard'))
    app = ClientApplication.query.get_or_404(app_id)
    script = _latest_script(app)
    docs, received_count = _fica_summary(app)
    reviews = ComplianceReview.query.filter_by(application_id=app.id).order_by(ComplianceReview.created_at.desc()).all()

    if request.method == 'POST':
        decision = request.form.get('decision') or 'QA Approved'
        checked = {key: (request.form.get(key) == 'on') for key, _ in QA_CHECKLIST}
        score = round(sum(1 for ok in checked.values() if ok) / len(QA_CHECKLIST) * 100)
        notes = request.form.get('notes') or ''
        if decision in {'QA Approved', 'Compliance Approved'} and score < 100:
            flash('Approval blocked: all QA checklist items must be ticked before approving.', 'danger')
            return redirect(url_for('qa.review_application', app_id=app.id))

        review = ComplianceReview(
            application_id=app.id,
            lapsed_policy_id=app.lapsed_policy_id,
            reviewer_id=current_user.id,
            decision=decision,
            checklist_json=json.dumps(checked),
            score=score,
            notes=notes,
        )
        db.session.add(review)
        app.status = decision
        if app.lapsed_policy:
            app.lapsed_policy.recovery_status = 'Approved' if decision in {'QA Approved', 'Compliance Approved'} else 'Rejected'
        db.session.add(AuditLog(user_id=current_user.id, action=decision, entity_type='ClientApplication', entity_id=str(app.id), details=f'QA score {score}%. {notes}'))
        db.session.commit()
        flash(f'{decision} saved with QA score {score}%.', 'success')
        return redirect(url_for('qa.qa_dashboard'))

    checklist_defaults = {key: False for key, _ in QA_CHECKLIST}
    if app.signed_at:
        checklist_defaults['signature_complete'] = True
    if received_count > 0:
        checklist_defaults['fica_complete'] = True
    if script and script.status == 'Completed':
        for key in ['popia_confirmed', 'product_explained', 'premium_confirmed', 'waiting_periods', 'debit_order', 'contact_details']:
            checklist_defaults[key] = True
    return render_template('qa/review_application.html', app=app, script=script, docs=docs, reviews=reviews, checklist=QA_CHECKLIST, checklist_defaults=checklist_defaults)

@qa_bp.route('/fica/<int:doc_id>/<decision>', methods=['POST'])
@login_required
def review_fica(doc_id, decision):
    if not _is_qa_user():
        flash('Only managers/compliance users can access FICA review.', 'danger')
        return redirect(url_for('main.dashboard'))
    doc = ClientFicaDocument.query.get_or_404(doc_id)
    doc.status = 'Reviewed' if decision == 'approve' else 'Rejected'
    db.session.add(AuditLog(user_id=current_user.id, action=f'FICA {doc.status}', entity_type='ClientFicaDocument', entity_id=str(doc.id), details=doc.original_filename or doc.document_type))
    db.session.commit()
    flash(f'FICA document marked {doc.status}.', 'success')
    return redirect(request.referrer or url_for('qa.qa_dashboard'))
