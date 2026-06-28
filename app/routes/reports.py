from datetime import date, datetime, time, timedelta
from io import StringIO
import csv
from flask import Blueprint, render_template, request, Response, redirect, url_for
from flask_login import login_required, current_user
from app import db
from app.models import ClientApplication, LapsedPolicy, RecoveryCallLog, User, ClientFicaDocument, DocumentSignature

reports_bp = Blueprint('reports', __name__, url_prefix='/reports')

def is_manager():
    role = (current_user.role.name if current_user.is_authenticated and current_user.role else '').lower().replace('_',' ')
    return role in {'admin','manager','branch manager'}

def parse_dates():
    today=date.today(); start=request.args.get('start') or today.replace(day=1).isoformat(); end=request.args.get('end') or today.isoformat()
    try: sd=datetime.strptime(start,'%Y-%m-%d').date()
    except Exception: sd=today.replace(day=1)
    try: ed=datetime.strptime(end,'%Y-%m-%d').date()
    except Exception: ed=today
    return sd,ed

def date_bounds(sd,ed): return datetime.combine(sd,time.min), datetime.combine(ed,time.max)

@reports_bp.route('/')
@login_required
def index():
    if not is_manager(): return redirect(url_for('main.dashboard'))
    sd,ed=parse_dates(); start,end=date_bounds(sd,ed); branch=request.args.get('branch') or ''
    leads=LapsedPolicy.query; apps=ClientApplication.query; calls=RecoveryCallLog.query; docs=ClientFicaDocument.query.join(ClientApplication)
    if branch:
        leads=leads.filter(LapsedPolicy.branch==branch); apps=apps.filter(ClientApplication.branch==branch); docs=docs.filter(ClientApplication.branch==branch)
    stats={
      'calls': calls.filter(RecoveryCallLog.created_at>=start, RecoveryCallLog.created_at<=end).count(),
      'applications': apps.filter(ClientApplication.created_at>=start, ClientApplication.created_at<=end).count(),
      'signed': apps.filter(ClientApplication.signed_at>=start, ClientApplication.signed_at<=end).count(),
      'open_leads': leads.filter(LapsedPolicy.recovery_status.in_(['Imported','New','Called','No Answer','Callback','Interested','Application Started','Signature Sent','FICA Outstanding','QA Review'])).count(),
      'approved': leads.filter(LapsedPolicy.recovery_status.in_(['Approved','Reinstated'])).count(),
      'rejected': leads.filter(LapsedPolicy.recovery_status=='Rejected').count(),
      'outstanding_fica': docs.filter(ClientFicaDocument.status.in_(['Received','Rejected'])).count(),
      'pending_signatures': apps.filter(ClientApplication.signed_at.is_(None)).count(),
    }
    stats['conversion_rate']=round((stats['signed']/stats['calls']*100),1) if stats['calls'] else 0
    agent_rows=db.session.query(User.name, User.branch, db.func.count(RecoveryCallLog.id).label('calls'), db.func.sum(db.case((RecoveryCallLog.outcome.in_(['Wants Reinstatement','Wants New Policy','Application Started','Signature Sent']),1), else_=0)).label('positive')).outerjoin(RecoveryCallLog, db.and_(RecoveryCallLog.agent_id==User.id, RecoveryCallLog.created_at>=start, RecoveryCallLog.created_at<=end)).group_by(User.id,User.name,User.branch).order_by(db.desc('calls')).all()
    branch_rows=db.session.query(LapsedPolicy.branch, db.func.count(LapsedPolicy.id)).group_by(LapsedPolicy.branch).order_by(db.func.count(LapsedPolicy.id).desc()).limit(30).all()
    status_rows=db.session.query(LapsedPolicy.recovery_status, db.func.count(LapsedPolicy.id)).group_by(LapsedPolicy.recovery_status).order_by(db.func.count(LapsedPolicy.id).desc()).all()
    return render_template('reports/index.html', stats=stats, agents=agent_rows, branches=branch_rows, statuses=status_rows, start_date=sd, end_date=ed, selected_branch=branch)

@reports_bp.route('/export.csv')
@login_required
def export_csv():
    if not is_manager(): return redirect(url_for('main.dashboard'))
    sd,ed=parse_dates(); start,end=date_bounds(sd,ed)
    output=StringIO(); w=csv.writer(output)
    w.writerow(['Agent','Branch','Calls','Positive Outcomes'])
    rows=db.session.query(User.name, User.branch, db.func.count(RecoveryCallLog.id), db.func.sum(db.case((RecoveryCallLog.outcome.in_(['Wants Reinstatement','Wants New Policy','Application Started','Signature Sent']),1), else_=0))).outerjoin(RecoveryCallLog, db.and_(RecoveryCallLog.agent_id==User.id, RecoveryCallLog.created_at>=start, RecoveryCallLog.created_at<=end)).group_by(User.id,User.name,User.branch).all()
    for r in rows: w.writerow([r[0],r[1] or '', int(r[2] or 0), int(r[3] or 0)])
    return Response(output.getvalue(), mimetype='text/csv', headers={'Content-Disposition':'attachment; filename=telesales_report.csv'})
