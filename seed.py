from app import create_app, db
from app.models import Role, Permission, User, PolicyProduct

app = create_app()

PERMS = {
    "applications.view": "View applications",
    "applications.create": "Create applications",
    "applications.send_signing": "Send client signing links",
    "policies.view": "View policy products",
    "policies.edit": "Create and edit policy products",
    "recovery.view": "View lapsed recovery queue",
    "recovery.import": "Import lapsed policy reports",
    "recovery.call": "Log recovery calls",
    "reports.view": "View reports",
    "users.manage": "Manage users and roles",
}

ROLE_MAP = {
    "Admin": list(PERMS.keys()),
    "Branch Manager": ["applications.view", "applications.create", "applications.send_signing", "policies.view", "recovery.view", "recovery.import", "recovery.call", "reports.view"],
    "Agent": ["applications.view", "applications.create", "applications.send_signing", "policies.view", "recovery.view", "recovery.call"],
    "Compliance": ["applications.view", "policies.view", "reports.view"],
    "Claims": ["applications.view", "policies.view"],
}

with app.app_context():
    db.create_all()
    perm_objs = {}
    for code, desc in PERMS.items():
        p = Permission.query.filter_by(code=code).first() or Permission(code=code, description=desc)
        db.session.add(p); perm_objs[code] = p
    db.session.commit()

    for role_name, codes in ROLE_MAP.items():
        r = Role.query.filter_by(name=role_name).first() or Role(name=role_name, description=role_name)
        r.permissions = [perm_objs[c] for c in codes]
        db.session.add(r)
    db.session.commit()

    admin_role = Role.query.filter_by(name="Admin").first()
    if not User.query.filter_by(email="wjm@martinsdirect.com").first():
        u = User(name="Default Admin", email="wjm@martinsdirect.com", role=admin_role, branch="Head Office")
        u.set_password("Renette7")
        db.session.add(u)

    if not PolicyProduct.query.first():
        db.session.add(PolicyProduct(product_name="Funeral Cover", plan_name="Starter Plan", cover_amount=10000, monthly_premium=100, waiting_period_months=6, min_age=18, max_age=100))
    db.session.commit()
    print("Seed complete. Login: wjm@martinsdirect.com / Renette7")
