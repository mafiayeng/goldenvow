import os, uuid, random, string, io, secrets
from datetime import datetime, timedelta
from flask import Flask, render_template_string, request, redirect, url_for, session, flash, jsonify, send_file
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import desc, func, inspect
from jinja2 import BaseLoader, TemplateNotFound
import bcrypt
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from apscheduler.schedulers.background import BackgroundScheduler

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'pL3x9QmW8vN2kR5yTzH7bJ4dF6sA1cX0')
database_url = os.environ.get('DATABASE_URL')
app.config['SQLALCHEMY_DATABASE_URI'] = database_url if database_url else 'sqlite:///database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.permanent_session_lifetime = timedelta(days=30)
db = SQLAlchemy(app)

# ---------- CONFIG ----------
SERVICE_FEE_PERCENTAGE = float(os.environ.get('SERVICE_FEE_PERCENTAGE', 2.0))
SUPPORT_WHATSAPP = os.environ.get('SUPPORT_WHATSAPP', '0737349468')
SUPPORT_EMAIL = os.environ.get('SUPPORT_EMAIL', 'goldenvowsupport@gmail.com')
SUPER_ADMIN_SECRET = os.environ.get('SUPER_ADMIN_SECRET', 'super.mfy')
MINIMUM_WITHDRAWAL_FEE = float(os.environ.get('MINIMUM_WITHDRAWAL_FEE', 50.0))

# ---------- MODELS ----------
class Admin(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    email = db.Column(db.String(100))
    phone = db.Column(db.String(20))
    is_super_admin = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    referral_code = db.Column(db.String(20), unique=True, nullable=False, default='')
    referred_by = db.Column(db.String(20), db.ForeignKey('admin.referral_code'), nullable=True)
    referral_count = db.Column(db.Integer, default=0)
    bonus_earned = db.Column(db.Float, default=0.0)
    last_login = db.Column(db.DateTime, nullable=True)

class Event(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    token = db.Column(db.String(100), unique=True, nullable=False)
    admin_id = db.Column(db.Integer, db.ForeignKey('admin.id'))
    event_type = db.Column(db.String(50), nullable=False, default='dowry')
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    target_amount = db.Column(db.Float, nullable=False)
    deadline = db.Column(db.DateTime, nullable=False)
    event_date = db.Column(db.DateTime, nullable=False)
    picture_url = db.Column(db.String(500))
    background_image_url = db.Column(db.String(500), nullable=True)
    account_name = db.Column(db.String(150), nullable=True)
    paybill = db.Column(db.String(50))
    mpesa_number = db.Column(db.String(20))
    till_number = db.Column(db.String(50))
    bank_name = db.Column(db.String(100))
    bank_account_name = db.Column(db.String(100))
    bank_account_number = db.Column(db.String(50))
    payment_instructions = db.Column(db.Text)
    whatsapp_contact = db.Column(db.String(20))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)
    first_contribution_date = db.Column(db.DateTime, nullable=True)
    fee_paid = db.Column(db.Boolean, default=False)
    fee_paid_date = db.Column(db.DateTime, nullable=True)
    grace_period = db.Column(db.Integer, default=0)
    has_grace_period = db.Column(db.Boolean, default=False)
    ended_at = db.Column(db.DateTime, nullable=True)
    thank_you_message = db.Column(db.Text, nullable=True)
    super_admin_message = db.Column(db.Text, nullable=True)
    disabled = db.Column(db.Boolean, default=False)
    disabled_reason = db.Column(db.Text, nullable=True)

class Contributor(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=True)
    password_hash = db.Column(db.String(200), nullable=True)
    last_login = db.Column(db.DateTime, nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    event_id = db.Column(db.Integer, db.ForeignKey('event.id'))
    token = db.Column(db.String(100), unique=True, nullable=False)
    pin = db.Column(db.String(4), nullable=False, default='0000')
    name = db.Column(db.String(150), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    pledge_amount = db.Column(db.Float, nullable=False)
    fee_amount = db.Column(db.Float, default=0.0)
    net_contribution = db.Column(db.Float, default=0.0)
    paid_amount = db.Column(db.Float, default=0.0)
    status = db.Column(db.String(20), default='pending')
    decline_reason = db.Column(db.Text, nullable=True)
    sender_name = db.Column(db.String(150), nullable=True)
    auto_verified = db.Column(db.Boolean, default=False)
    payment_proof_screenshot = db.Column(db.String(500))
    payment_proof_text = db.Column(db.Text)
    completed_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class Payment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    contributor_id = db.Column(db.Integer, db.ForeignKey('contributor.id'))
    amount = db.Column(db.Float, nullable=False)
    date_paid = db.Column(db.DateTime, default=datetime.utcnow)
    note = db.Column(db.String(200))

class ChatMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey('event.id'))
    sender_name = db.Column(db.String(150), nullable=False)
    sender_type = db.Column(db.String(20), default='contributor')
    message = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

class PrivateMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(db.Integer, db.ForeignKey('conversation.id'))
    sender_type = db.Column(db.String(20), nullable=False)
    sender_id = db.Column(db.Integer, nullable=False)
    message = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    is_read = db.Column(db.Boolean, default=False)

class Conversation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey('event.id'))
    admin_id = db.Column(db.Integer, db.ForeignKey('admin.id'))
    contributor_id = db.Column(db.Integer, db.ForeignKey('contributor.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    admin_id = db.Column(db.Integer, db.ForeignKey('admin.id'))
    event_id = db.Column(db.Integer, db.ForeignKey('event.id'), nullable=True)
    contributor_id = db.Column(db.Integer, db.ForeignKey('contributor.id'), nullable=True)
    message = db.Column(db.Text, nullable=False)
    type = db.Column(db.String(50), default='info')
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Testimonial(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey('event.id'))
    contributor_id = db.Column(db.Integer, db.ForeignKey('contributor.id'))
    rating = db.Column(db.Integer, default=0)
    message = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Withdrawal(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    admin_id = db.Column(db.Integer, db.ForeignKey('admin.id'))
    amount = db.Column(db.Float, nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    method = db.Column(db.String(20), default='mpesa')
    status = db.Column(db.String(20), default='pending')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    paid_at = db.Column(db.DateTime, nullable=True)

class ContactMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    email = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20), nullable=True)
    subject = db.Column(db.String(200), nullable=False)
    message = db.Column(db.Text, nullable=False)
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class PasswordReset(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    admin_id = db.Column(db.Integer, db.ForeignKey('admin.id'))
    token = db.Column(db.String(100), unique=True, nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    used = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Setting(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(100), unique=True, nullable=False)
    value = db.Column(db.Text, nullable=False)

class FeatureRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey('event.id'), nullable=True)
    contributor_id = db.Column(db.Integer, db.ForeignKey('contributor.id'), nullable=True)
    contributor_name = db.Column(db.String(150), nullable=False)
    contributor_email = db.Column(db.String(100), nullable=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), default='pending')
    admin_response = db.Column(db.Text, nullable=True)
    votes = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

# ---------- CREATE TABLES ----------
with app.app_context():
    db.create_all()

# ---------- HELPERS ----------
def is_admin_logged_in():
    return session.get('admin_id') is not None

def is_contributor_logged_in():
    return session.get('contributor_id') is not None

def get_admin():
    if not is_admin_logged_in():
        return None
    return Admin.query.get(session['admin_id'])

def get_contributor():
    if not is_contributor_logged_in():
        return None
    return Contributor.query.get(session['contributor_id'])

def is_super_admin():
    admin = get_admin()
    return admin and admin.is_super_admin

def generate_unique_token():
    return str(uuid.uuid4())[:12]

def generate_pin():
    return f"{random.randint(1000, 9999)}"

def generate_referral_code():
    return f"GV-{''.join(random.choices(string.ascii_uppercase + string.digits, k=6))}"

def hash_password(plain):
    return bcrypt.hashpw(plain.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def check_password(plain, hashed):
    return bcrypt.checkpw(plain.encode('utf-8'), hashed.encode('utf-8'))

def create_notification(admin_id, message, type='info', event_id=None, contributor_id=None):
    n = Notification(admin_id=admin_id, event_id=event_id, contributor_id=contributor_id, message=message, type=type)
    db.session.add(n)
    db.session.commit()

def get_unread_notifications(admin_id):
    return Notification.query.filter_by(admin_id=admin_id, is_read=False).count()

def get_fee_percentage(admin_id):
    admin = Admin.query.get(admin_id)
    if not admin:
        return SERVICE_FEE_PERCENTAGE
    count = admin.referral_count
    if count >= 9:
        return 1.54
    elif count >= 4:
        return 1.61
    elif count >= 2:
        return 1.72
    elif count >= 1:
        return 1.80
    else:
        return 2.0

def calculate_fee(amount, admin_id=None):
    fee_pct = get_fee_percentage(admin_id) if admin_id else SERVICE_FEE_PERCENTAGE
    fee = round(amount * (fee_pct / 100), 2)
    return max(fee, 0.0)

def get_event_total_contributions(event_id):
    return db.session.query(func.sum(Contributor.paid_amount)).filter_by(event_id=event_id, status='approved').scalar() or 0

def get_event_total_fee(event_id):
    return db.session.query(func.sum(Contributor.fee_amount)).filter_by(event_id=event_id, status='approved').scalar() or 0

def get_global_total_fees():
    return db.session.query(func.sum(Contributor.fee_amount)).filter_by(status='approved').scalar() or 0

def get_admin_total_fees(admin_id):
    events = Event.query.filter_by(admin_id=admin_id).all()
    total = 0
    for e in events:
        total += get_event_total_fee(e.id)
    return total

def is_fee_overdue(event):
    if not event.first_contribution_date:
        return False
    if event.fee_paid:
        return False
    total_fee = get_event_total_fee(event.id)
    if total_fee < 50.0:
        return False
    due_date = event.first_contribution_date + timedelta(days=3)
    if datetime.utcnow() > due_date:
        grace_end = due_date + timedelta(hours=1)
        if datetime.utcnow() > grace_end:
            return True
    return False

def get_page_lock_status(event, contributor_token=None):
    if event.disabled:
        return True
    if contributor_token:
        return False
    if not event.first_contribution_date:
        return False
    if event.fee_paid:
        return False
    if is_fee_overdue(event):
        return True
    return False

def get_daily_note(event_type, day):
    notes = {
        'dowry': ["🐂 Love unites two families...", "Every step brings them closer..."],
        'burial': ["🕊️ In loving memory...", "Together we heal..."],
        'medical': ["❤️ Hope and healing...", "Your support saves lives..."],
        'education': ["🎓 Building futures...", "Knowledge is power..."],
        'harambee': ["🤝 Community strength...", "Together we achieve more..."],
        'other': ["✨ Great things happen...", "Your kindness matters..."]
    }
    list = notes.get(event_type, notes['other'])
    return list[(day - 1) % len(list)]

def generate_event_logo(event, size=120):
    colors = {
        'dowry': {'bg1': '#1A2A3A', 'bg2': '#D4AF37', 'symbol': '🐂', 'ring': '#D4AF37'},
        'burial': {'bg1': '#2C2C2C', 'bg2': '#C0C0C0', 'symbol': '🕊️', 'ring': '#C0C0C0'},
        'medical': {'bg1': '#C62828', 'bg2': '#FFFFFF', 'symbol': '❤️', 'ring': '#C62828'},
        'education': {'bg1': '#1565C0', 'bg2': '#D4AF37', 'symbol': '🎓', 'ring': '#1565C0'},
        'harambee': {'bg1': '#2E7D32', 'bg2': '#D4AF37', 'symbol': '🤝', 'ring': '#2E7D32'},
        'other': {'bg1': '#6A1B9A', 'bg2': '#D4AF37', 'symbol': '✦', 'ring': '#6A1B9A'}
    }
    c = colors.get(event.event_type, colors['other'])
    initials = ''.join([w[0].upper() for w in event.title.split()][:2]) or event.title[:2].upper()
    svg = f'''<svg width="{size}" height="{size}" viewBox="0 0 {size} {size}" xmlns="http://www.w3.org/2000/svg">
        <circle cx="{size/2}" cy="{size/2}" r="{size/2 - 5}" fill="{c['bg1']}" />
        <circle cx="{size/2}" cy="{size/2}" r="{size/2 - 15}" stroke="{c['ring']}" stroke-width="3" fill="none" opacity="0.8"/>
        <text x="{size/2}" y="{size/2 - 10}" text-anchor="middle" fill="{c['ring']}" font-size="{size/3}">{c['symbol']}</text>
        <text x="{size/2}" y="{size/2 + 25}" text-anchor="middle" fill="#FFFFFF" font-size="{size/5}" font-weight="bold">{initials}</text>
        <text x="{size/4}" y="{size/4}" fill="{c['ring']}" font-size="{size/8}">✦</text>
        <text x="{size*0.75}" y="{size/4}" fill="{c['ring']}" font-size="{size/8}">✦</text>
    </svg>'''
    return svg

def get_app_logo(size=40):
    return f'''<svg width="{size}" height="{size}" viewBox="0 0 {size} {size}">
        <circle cx="{size/2}" cy="{size/2}" r="{size/2-3}" fill="#1A2A3A"/>
        <circle cx="{size/2}" cy="{size/2}" r="{size/2-8}" stroke="#D4AF37" stroke-width="2" fill="none"/>
        <text x="{size/2}" y="{size/2+5}" text-anchor="middle" fill="#D4AF37" font-size="{size/3}" font-weight="bold">GV</text>
        <text x="{size/4}" y="{size/4}" fill="#D4AF37" font-size="{size/8}">✦</text>
        <text x="{size*0.75}" y="{size/4}" fill="#D4AF37" font-size="{size/8}">✦</text>
    </svg>'''

# ---------- BASE HTML ----------
BASE_HTML = """<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>GoldenVow – {% block title %}Fundraising{% endblock %}</title>
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.10.0/font/bootstrap-icons.css">
<style>
:root { --gold: #D4AF37; --gold-light: #f5d06b; --dark-bg: #0b1120; --text-light: #e2e8f0; --text-muted: #94a3b8; }
* { scroll-behavior: smooth; }
body { background: linear-gradient(135deg, #0b1120 0%, #1a2332 100%); color: var(--text-light); font-family: 'Inter', Arial, sans-serif; min-height: 100vh; }
.glass-card { background: rgba(255,255,255,0.04); backdrop-filter: blur(12px); border: 1px solid rgba(255,255,255,0.06); border-radius: 24px; box-shadow: 0 20px 40px rgba(0,0,0,0.4); transition: transform 0.2s, box-shadow 0.2s; }
.glass-card:hover { transform: translateY(-4px); box-shadow: 0 30px 50px rgba(0,0,0,0.5); }
.golden-text { color: var(--gold); }
.text-muted-light { color: var(--text-muted); }
.btn-gold { background: linear-gradient(135deg, var(--gold), var(--gold-light)); border: none; color: #0b1120; font-weight: 600; border-radius: 50px; padding: 10px 24px; transition: 0.3s; }
.btn-gold:hover { transform: scale(1.03); box-shadow: 0 8px 25px rgba(212,175,55,0.4); color: #0b1120; }
.btn-outline-gold { border: 2px solid var(--gold); color: var(--gold); border-radius: 50px; background: transparent; }
.btn-outline-gold:hover { background: var(--gold); color: #0b1120; }
.progress-bar-gold { background: linear-gradient(90deg, var(--gold), var(--gold-light)); }
.navbar { background: rgba(15, 26, 43, 0.8); backdrop-filter: blur(10px); border-bottom: 1px solid rgba(255,255,255,0.05); }
.navbar-brand { font-weight: 700; letter-spacing: 1px; font-size: 1.4rem; }
.footer { background: rgba(15, 26, 43, 0.9); backdrop-filter: blur(10px); border-top: 1px solid rgba(255,255,255,0.05); }
.alert { background: var(--dark-bg); border: 1px solid rgba(255,255,255,0.06); }
@keyframes fadeUp { from { opacity: 0; transform: translateY(20px); } to { opacity: 1; transform: translateY(0); } }
.animate-fade-up { animation: fadeUp 0.6s ease-out forwards; }
::-webkit-scrollbar { width: 8px; }
::-webkit-scrollbar-track { background: #1a2332; }
::-webkit-scrollbar-thumb { background: var(--gold); border-radius: 10px; }
</style>
</head>
<body>
<nav class="navbar navbar-expand-lg sticky-top"><div class="container">
<a class="navbar-brand" href="{{ url_for('dashboard') if is_admin_logged_in() else url_for('login') }}"><span class="golden-text">✦ GoldenVow</span></a>
<button class="navbar-toggler border-0" type="button" data-bs-toggle="collapse" data-bs-target="#navbarNav"><span class="navbar-toggler-icon" style="filter: invert(1);"></span></button>
<div class="collapse navbar-collapse" id="navbarNav">
<ul class="navbar-nav ms-auto align-items-lg-center">
{% if is_admin_logged_in() %}
<li class="nav-item"><a class="nav-link" href="{{ url_for('dashboard') }}">Dashboard</a></li>
<li class="nav-item"><a class="nav-link" href="{{ url_for('create_event') }}"><i class="bi bi-plus-circle"></i> New</a></li>
<li class="nav-item"><a class="nav-link" href="{{ url_for('help_page') }}"><i class="bi bi-question-circle"></i> Help</a></li>
<li class="nav-item"><a class="nav-link" href="{{ url_for('contact') }}"><i class="bi bi-envelope"></i> Contact</a></li>
{% if get_admin() and get_admin().is_super_admin %}
<li class="nav-item"><a class="nav-link" href="{{ url_for('super_dashboard') }}">Super</a></li>
<li class="nav-item"><a class="nav-link" href="{{ url_for('withdrawals') }}">Withdrawals</a></li>
<li class="nav-item"><a class="nav-link" href="{{ url_for('settings') }}">Settings</a></li>
{% endif %}
<li class="nav-item"><a class="nav-link position-relative" href="{{ url_for('notifications') }}"><i class="bi bi-bell fs-5"></i>{% if get_unread_notifications(get_admin().id) > 0 %}<span class="position-absolute top-0 start-100 translate-middle badge rounded-pill bg-danger">{{ get_unread_notifications(get_admin().id) }}</span>{% endif %}</a></li>
<li class="nav-item"><a class="nav-link" href="{{ url_for('profile') }}"><i class="bi bi-person"></i></a></li>
<li class="nav-item"><a class="nav-link" href="{{ url_for('logout') }}"><i class="bi bi-box-arrow-right"></i></a></li>
{% else %}
<li class="nav-item"><a class="nav-link" href="{{ url_for('login') }}">Admin Login</a></li>
<li class="nav-item"><a class="nav-link" href="{{ url_for('contributor_login') }}">Contributor Login</a></li>
<li class="nav-item"><a class="nav-link" href="{{ url_for('contact') }}">Contact</a></li>
{% endif %}
</ul>
</div></div></nav>
<div class="container mt-3">{% with messages = get_flashed_messages(with_categories=true) %}{% if messages %}{% for category, message in messages %}<div class="alert alert-{{ 'danger' if category == 'error' else 'success' if category == 'success' else 'info' }} alert-dismissible fade show glass-card">{{ message }}<button type="button" class="btn-close" data-bs-dismiss="alert"></button></div>{% endfor %}{% endif %}{% endwith %}</div>
<main class="container py-4 animate-fade-up">{% block content %}{% endblock %}</main>
<footer class="footer mt-5 py-3"><div class="container text-center"><p class="mb-1 golden-text">✦ GoldenVow – Bringing Communities Together</p><small class="text-muted-light">WhatsApp: {{ support_whatsapp }} &nbsp;|&nbsp; Email: {{ support_email }}</small></div></footer>
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
{% block scripts %}{% endblock %}
</body>
</html>"""

# ---------- CUSTOM LOADER ----------
class StringLoader(BaseLoader):
    def __init__(self, base_html):
        self.base_html = base_html
    def get_source(self, environment, template):
        if template == 'base.html':
            return self.base_html, None, lambda: True
        raise TemplateNotFound(template)

app.jinja_env.loader = StringLoader(BASE_HTML)

# ---------- HTML TEMPLATES ----------
LOGIN_HTML = """{% extends "base.html" %}
{% block content %}
<div class="row justify-content-center"><div class="col-md-5 col-lg-4"><div class="glass-card p-4"><h3 class="text-center golden-text">✦ Admin Login</h3><hr><form method="POST"><div class="mb-3"><label class="form-label">Username</label><input type="text" name="username" class="form-control bg-dark text-light" required></div><div class="mb-3"><label class="form-label">Password</label><input type="password" name="password" class="form-control bg-dark text-light" required></div><button type="submit" class="btn btn-gold w-100">Login</button></form><div class="mt-3 text-center"><a href="{{ url_for('forgot_password') }}" class="text-muted-light">Forgot password?</a><br><small class="text-muted-light">Don't have an account? <a href="{{ url_for('register') }}" class="golden-text">Register</a></small><hr><small class="text-muted-light">Contributor? <a href="{{ url_for('contributor_login') }}" class="golden-text">Login here</a></small></div></div></div></div>
{% endblock %}"""

REGISTER_HTML = """{% extends "base.html" %}
{% block content %}
<div class="row justify-content-center"><div class="col-md-6 col-lg-5"><div class="glass-card p-4"><h3 class="text-center golden-text">✦ Create Admin Account</h3><hr><form method="POST"><div class="mb-2"><label class="form-label">Username <span class="text-danger">*</span></label><input type="text" name="username" class="form-control bg-dark text-light" required></div><div class="mb-2"><label class="form-label">Email <span class="text-danger">*</span></label><input type="email" name="email" class="form-control bg-dark text-light" required></div><div class="mb-2"><label class="form-label">Phone</label><input type="tel" name="phone" class="form-control bg-dark text-light"></div><div class="mb-2"><label class="form-label">Password <span class="text-danger">*</span></label><input type="password" name="password" class="form-control bg-dark text-light" required></div><div class="mb-2"><label class="form-label">Referral Code (optional)</label><input type="text" name="referral_code" class="form-control bg-dark text-light" placeholder="Enter code if you have one"></div><div class="mb-3"><label class="form-label">Super Admin Secret (if applicable)</label><input type="password" name="super_secret" class="form-control bg-dark text-light" placeholder="Only if you're the developer"></div><button type="submit" class="btn btn-gold w-100">Register</button></form><div class="mt-3 text-center"><small class="text-muted-light">Already have an account? <a href="{{ url_for('login') }}" class="golden-text">Login</a></small></div></div></div></div>
{% endblock %}"""

# ---------- ROUTES ----------
@app.route('/')
def index():
    if is_admin_logged_in():
        admin = get_admin()
        if admin.is_super_admin:
            return redirect(url_for('super_dashboard'))
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        admin = Admin.query.filter_by(username=username, is_active=True).first()
        if admin and check_password(password, admin.password_hash):
            session.permanent = True
            session['admin_id'] = admin.id
            admin.last_login = datetime.utcnow()
            db.session.commit()
            flash('Logged in.', 'success')
            if admin.is_super_admin:
                return redirect(url_for('super_dashboard'))
            return redirect(url_for('dashboard'))
        flash('Invalid credentials.', 'error')
    return render_template_string(LOGIN_HTML)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        email = request.form.get('email', '').strip()
        phone = request.form.get('phone', '').strip()
        super_secret = request.form.get('super_secret', '').strip()
        ref_code = request.form.get('referral_code', '').strip()
        if not username or not password:
            flash('Username and password required.', 'error')
            return render_template_string(REGISTER_HTML)
        if Admin.query.filter_by(username=username).first():
            flash('Username taken.', 'error')
            return render_template_string(REGISTER_HTML)
        if Admin.query.filter_by(email=email).first():
            flash('Email already registered.', 'error')
            return render_template_string(REGISTER_HTML)
        referral_code = generate_referral_code()
        while Admin.query.filter_by(referral_code=referral_code).first():
            referral_code = generate_referral_code()
        admin = Admin(username=username, password_hash=hash_password(password), email=email, phone=phone,
                      referral_code=referral_code, is_super_admin=False)
        if super_secret == SUPER_ADMIN_SECRET or Admin.query.count() == 0:
            admin.is_super_admin = True
            flash('You are now the Super Admin!', 'success')
        db.session.add(admin)
        db.session.commit()
        if ref_code:
            referrer = Admin.query.filter_by(referral_code=ref_code).first()
            if referrer:
                referrer.referral_count += 1
                db.session.commit()
                flash('Referral code accepted! You now have lower fees.', 'success')
        flash('Registration successful! Login.', 'success')
        return redirect(url_for('login'))
    return render_template_string(REGISTER_HTML)

@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out.', 'info')
    return redirect(url_for('login'))

# ---------- DASHBOARD (MINIMAL WORKING VERSION) ----------
@app.route('/dashboard')
def dashboard():
    if not is_admin_logged_in():
        return redirect(url_for('login'))
    admin = get_admin()
    if admin.is_super_admin:
        return redirect(url_for('super_dashboard'))
    events = Event.query.filter_by(admin_id=admin.id).all()
    return f"<h1>Welcome {admin.username}!</h1><p>You have {len(events)} events.</p><a href='/logout'>Logout</a>"

@app.route('/super-dashboard')
def super_dashboard():
    if not is_admin_logged_in():
        return redirect(url_for('login'))
    admin = get_admin()
    if not admin.is_super_admin:
        flash('Access denied.', 'error')
        return redirect(url_for('dashboard'))
    return f"<h1>👑 Super Admin: {admin.username}</h1><p>You control everything!</p><a href='/logout'>Logout</a>"

# ---------- CREATE EVENT ----------
@app.route('/events/create', methods=['GET', 'POST'])
def create_event():
    if not is_admin_logged_in():
        return redirect(url_for('login'))
    admin = get_admin()
    if admin.is_super_admin:
        flash('Super admins cannot create events.', 'error')
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        token = generate_unique_token()
        while Event.query.filter_by(token=token).first():
            token = generate_unique_token()
        event = Event(
            token=token, admin_id=admin.id,
            title=request.form.get('title'),
            description=request.form.get('description'),
            target_amount=float(request.form.get('target_amount', 0)),
            deadline=datetime.strptime(request.form.get('deadline'), '%Y-%m-%dT%H:%M'),
            event_date=datetime.strptime(request.form.get('event_date'), '%Y-%m-%dT%H:%M'),
            account_name=request.form.get('account_name')
        )
        db.session.add(event)
        db.session.commit()
        flash('Event created!', 'success')
        return redirect(url_for('dashboard'))
    return render_template_string("""
    <h1>Create Event</h1>
    <form method="POST">
    <input type="text" name="title" placeholder="Title" required><br>
    <textarea name="description" placeholder="Description"></textarea><br>
    <input type="number" name="target_amount" placeholder="Target" step="0.01" required><br>
    <input type="datetime-local" name="event_date" required><br>
    <input type="datetime-local" name="deadline" required><br>
    <input type="text" name="account_name" placeholder="Account Name" required><br>
    <button type="submit">Create</button>
    </form>
    <a href="/dashboard">Back</a>
    """)

@app.route('/events/<token>')
def event_landing(token):
    event = Event.query.filter_by(token=token).first_or_404()
    return f"<h1>{event.title}</h1><p>{event.description}</p><p>Account: {event.account_name}</p><a href='/dashboard'>Back</a>"

# ---------- CONTACT ----------
@app.route('/contact', methods=['GET', 'POST'])
def contact():
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        subject = request.form.get('subject')
        message = request.form.get('message')
        if not all([name, email, subject, message]):
            flash('All fields required.', 'error')
            return redirect(url_for('contact'))
        msg = ContactMessage(name=name, email=email, phone=request.form.get('phone'), subject=subject, message=message)
        db.session.add(msg)
        db.session.commit()
        flash('Message sent!', 'success')
        return redirect(url_for('contact'))
    return render_template_string("""
    <h1>📩 Contact Us</h1>
    <form method="POST">
    <input type="text" name="name" placeholder="Your Name" required><br>
    <input type="email" name="email" placeholder="Your Email" required><br>
    <input type="tel" name="phone" placeholder="Phone (optional)"><br>
    <input type="text" name="subject" placeholder="Subject" required><br>
    <textarea name="message" placeholder="Your Message" rows="4" required></textarea><br>
    <button type="submit">Send</button>
    </form>
    <p><strong>WhatsApp:</strong> {{ support_whatsapp }}</p>
    <p><strong>Email:</strong> {{ support_email }}</p>
    <a href="/">Back</a>
    """)

# ---------- SCHEDULER ----------
scheduler = BackgroundScheduler()
scheduler.add_job(lambda: None, 'interval', hours=3)  # Placeholder
scheduler.start()

# ---------- MAIN ----------
if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
