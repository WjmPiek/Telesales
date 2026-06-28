from datetime import datetime, timedelta
from flask import Blueprint, render_template, redirect, url_for, flash
from flask_login import login_required, current_user
from app import db
from app.models import LoginAttempt, AuditLog, User
security_center_bp=Blueprint('security_center',__name__,url_prefix='/security-center')
def is_admin(): return current_user.is_authenticated and current_user.role and current_user.role.name.lower()=='admin'
@security_center_bp.route('/')
@login_required
def index():
    if not is_admin(): return redirect(url_for('main.dashboard'))
    since=datetime.utcnow()-timedelta(days=7)
    attempts=LoginAttempt.query.filter(LoginAttempt.created_at>=since).order_by(LoginAttempt.created_at.desc()).limit(200).all()
    inactive_users=User.query.filter_by(active=False).order_by(User.name).all()
    checklist=[
      ('SECRET_KEY set in Render environment', True),('DATABASE_URL uses PostgreSQL', True),('AUTO_CREATE_TABLES disabled after migrations are stable', False),('Uploads moved to permanent cloud storage', False),('Default/admin passwords changed', False),('Regular database backups configured', False),('No .git folder in deployment ZIP', True)]
    return render_template('security_center/index.html', attempts=attempts, inactive_users=inactive_users, checklist=checklist)
