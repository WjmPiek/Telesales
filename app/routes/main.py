from flask import Blueprint, render_template, redirect, url_for
from flask_login import login_required
from app.models import ClientApplication, LapsedPolicy, RecoveryCallLog, PolicyProduct

main_bp = Blueprint("main", __name__)

@main_bp.route("/")
@login_required
def dashboard():
    stats = {
        "applications": ClientApplication.query.count(),
        "products": PolicyProduct.query.count(),
        "lapsed": LapsedPolicy.query.count(),
        "calls": RecoveryCallLog.query.count(),
    }
    return render_template("dashboard/index.html", stats=stats)


@main_bp.route("/login")
def login_alias():
    return redirect(url_for("auth.login"))
