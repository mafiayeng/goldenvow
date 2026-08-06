# =============================================================================
# GOLDENVOW – COMPLETE APPLICATION (Single File)
# =============================================================================
import os, uuid, random, string, io, secrets, smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
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
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///database.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.permanent_session_lifetime = timedelta(days=30)
db = SQLAlchemy(app)

# ---------- CONFIG ----------
SERVICE_FEE_PERCENTAGE = float(os.environ.get('SERVICE_FEE_PERCENTAGE', 2.0))
SUPPORT_WHATSAPP = os.environ.get('SUPPORT_WHATSAPP', '0737349468')
SUPPORT_EMAIL = os.environ.get('SUPPORT_EMAIL', 'goldenvowsupport@gmail.com')
SUPER_ADMIN_SECRET = os.environ.get('SUPER_ADMIN_SECRET', 'super.mfy')
MINIMUM_WITHDRAWAL_FEE = float(os.environ.get('MINIMUM_WITHDRAWAL_FEE', 50.0))

EMAIL_HOST = os.environ.get('EMAIL_HOST', 'smtp.gmail.com')
EMAIL_PORT = int(os.environ.get('EMAIL_PORT', 587))
EMAIL_USER = os.environ.get('EMAIL_USER', 'goldenvowsupport@gmail.com')
EMAIL_PASS = os.environ.get('EMAIL_PASS', '')

def send_email(to, subject, body):
    if not EMAIL_PASS:
        print(f"[EMAIL] To: {to}\nSubject: {subject}\n{body}\n")
        return
    try:
        msg = MIMEMultipart()
        msg['From'] = EMAIL_USER
        msg['To'] = to
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))
        server = smtplib.SMTP(EMAIL_HOST, EMAIL_PORT)
        server.starttls()
        server.login(EMAIL_USER, EMAIL_PASS)
        server.send_message(msg)
        server.quit()
        print(f"Email sent to {to}")
    except Exception as e:
        print(f"Email error: {e}")

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
    event_id = db.Column(db.Integer, db.ForeignKey('event.id'), nullable=True)
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

# ---------- CREATE TABLES & MIGRATIONS ----------
with app.app_context():
    db.create_all()
    for key, default in [('maintenance_mode', 'False'), ('maintenance_message', ''), ('maintenance_eta', '')]:
        if not Setting.query.filter_by(key=key).first():
            db.session.add(Setting(key=key, value=default))
    db.session.commit()
    try:
        inspector = inspect(db.engine)
        cols = [c['name'] for c in inspector.get_columns('contributor')]
        if 'decline_reason' not in cols:
            db.engine.execute('ALTER TABLE contributor ADD COLUMN decline_reason TEXT')
        if 'sender_name' not in cols:
            db.engine.execute('ALTER TABLE contributor ADD COLUMN sender_name VARCHAR(150)')
        if 'auto_verified' not in cols:
            db.engine.execute('ALTER TABLE contributor ADD COLUMN auto_verified BOOLEAN DEFAULT 0')
        if 'username' not in cols:
            db.engine.execute('ALTER TABLE contributor ADD COLUMN username VARCHAR(100)')
        if 'password_hash' not in cols:
            db.engine.execute('ALTER TABLE contributor ADD COLUMN password_hash VARCHAR(200)')
        if 'last_login' not in cols:
            db.engine.execute('ALTER TABLE contributor ADD COLUMN last_login TIMESTAMP')
        if 'is_active' not in cols:
            db.engine.execute('ALTER TABLE contributor ADD COLUMN is_active BOOLEAN DEFAULT 1')
        cols = [c['name'] for c in inspector.get_columns('event')]
        if 'account_name' not in cols:
            db.engine.execute('ALTER TABLE event ADD COLUMN account_name VARCHAR(150)')
        if 'whatsapp_contact' not in cols:
            db.engine.execute('ALTER TABLE event ADD COLUMN whatsapp_contact VARCHAR(20)')
        if 'payment_instructions' not in cols:
            db.engine.execute('ALTER TABLE event ADD COLUMN payment_instructions TEXT')
        if 'first_contribution_date' not in cols:
            db.engine.execute('ALTER TABLE event ADD COLUMN first_contribution_date TIMESTAMP')
        if 'fee_paid' not in cols:
            db.engine.execute('ALTER TABLE event ADD COLUMN fee_paid BOOLEAN DEFAULT 0')
        if 'fee_paid_date' not in cols:
            db.engine.execute('ALTER TABLE event ADD COLUMN fee_paid_date TIMESTAMP')
        if 'grace_period' not in cols:
            db.engine.execute('ALTER TABLE event ADD COLUMN grace_period INTEGER DEFAULT 0')
        if 'has_grace_period' not in cols:
            db.engine.execute('ALTER TABLE event ADD COLUMN has_grace_period BOOLEAN DEFAULT 0')
        if 'disabled' not in cols:
            db.engine.execute('ALTER TABLE event ADD COLUMN disabled BOOLEAN DEFAULT 0')
        if 'disabled_reason' not in cols:
            db.engine.execute('ALTER TABLE event ADD COLUMN disabled_reason TEXT')
        cols = [c['name'] for c in inspector.get_columns('admin')]
        if 'is_active' not in cols:
            db.engine.execute('ALTER TABLE admin ADD COLUMN is_active BOOLEAN DEFAULT 1')
    except Exception as e:
        print(f"Migration warning: {e}")

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
    return db.session.query(func.sum(Contributor.paid_amount)).filter_by(
        event_id=event_id, status='approved'
    ).scalar() or 0

def get_event_total_fee(event_id):
    return db.session.query(func.sum(Contributor.fee_amount)).filter_by(
        event_id=event_id, status='approved'
    ).scalar() or 0

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

# ---------- CONTEXT PROCESSOR ----------
@app.context_processor
def utility_processor():
    return dict(
        is_admin_logged_in=is_admin_logged_in,
        is_contributor_logged_in=is_contributor_logged_in,
        get_admin=get_admin,
        get_contributor=get_contributor,
        get_unread_notifications=get_unread_notifications,
        get_event_total_contributions=get_event_total_contributions,
        get_event_total_fee=get_event_total_fee,
        get_page_lock_status=get_page_lock_status,
        generate_event_logo=generate_event_logo,
        support_whatsapp=SUPPORT_WHATSAPP,
        support_email=SUPPORT_EMAIL,
        fee_percentage=SERVICE_FEE_PERCENTAGE,
        minimum_withdrawal_fee=MINIMUM_WITHDRAWAL_FEE,
        now=datetime.utcnow,
        request=request
    )

# ---------- BASE HTML – DARK GLASS THEME WITH IMPROVED CONTRAST ----------
BASE_HTML = """
<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>GoldenVow – {% block title %}Fundraising{% endblock %}</title>
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.10.0/font/bootstrap-icons.css">
<style>
:root { --gold: #D4AF37; --gold-light: #f5d06b; --dark-bg: #0b1120; --text-light: #e2e8f0; --text-muted: #c0d0e0; }
* { scroll-behavior: smooth; }
body { background: linear-gradient(135deg, #0b1120 0%, #1a2332 100%); color: var(--text-light); font-family: 'Inter', Arial, sans-serif; min-height: 100vh; }
.glass-card { background: rgba(255,255,255,0.08); backdrop-filter: blur(12px); border: 1px solid rgba(255,255,255,0.12); border-radius: 24px; box-shadow: 0 20px 40px rgba(0,0,0,0.4); transition: transform 0.2s, box-shadow 0.2s; }
.glass-card:hover { transform: translateY(-4px); box-shadow: 0 30px 50px rgba(0,0,0,0.5); }
.golden-text { color: var(--gold); }
.text-muted-light { color: var(--text-muted); }
.btn-gold { background: linear-gradient(135deg, var(--gold), var(--gold-light)); border: none; color: #0b1120; font-weight: 600; border-radius: 50px; padding: 10px 24px; transition: 0.3s; }
.btn-gold:hover { transform: scale(1.03); box-shadow: 0 8px 25px rgba(212,175,55,0.4); color: #0b1120; }
.btn-outline-gold { border: 2px solid var(--gold); color: var(--gold); border-radius: 50px; background: transparent; }
.btn-outline-gold:hover { background: var(--gold); color: #0b1120; }
.progress-bar-gold { background: linear-gradient(90deg, var(--gold), var(--gold-light)); }
.navbar { background: rgba(15, 26, 43, 0.85); backdrop-filter: blur(10px); border-bottom: 1px solid rgba(255,255,255,0.05); }
.navbar-brand { font-weight: 700; letter-spacing: 1px; font-size: 1.4rem; }
.navbar-brand svg { margin-right: 10px; vertical-align: middle; }
.footer { background: rgba(15, 26, 43, 0.9); backdrop-filter: blur(10px); border-top: 1px solid rgba(255,255,255,0.05); }
.alert { background: var(--dark-bg); border: 1px solid rgba(255,255,255,0.06); }
.alert-success { background: #1a3a2a; color: #8fdfaf; border-left: 4px solid #2ecc71; }
.alert-error { background: #3a1a1a; color: #ff8a8a; border-left: 4px solid #e74c3c; }
.alert-info { background: #1a2a3a; color: #8ab8ff; border-left: 4px solid #3498db; }
input, textarea, select {
    background: #1a2332 !important;
    color: #ffffff !important;
    border: 1px solid rgba(255,255,255,0.2) !important;
    border-radius: 12px !important;
    padding: 12px 16px !important;
    font-size: 1rem !important;
    transition: border-color 0.2s;
}
input:focus, textarea:focus, select:focus {
    border-color: var(--gold) !important;
    outline: none !important;
    box-shadow: 0 0 0 3px rgba(212, 175, 55, 0.3);
}
::placeholder { color: #a0b0c0 !important; opacity: 1; }
label { font-weight: 500; color: #d0e0f0; }
.hero { min-height: 70vh; display: flex; align-items: center; justify-content: center; text-align: center; }
.hero h1 { font-size: 3.5rem; font-weight: 800; }
.hero p { font-size: 1.2rem; max-width: 600px; margin: 0 auto; }
.hero .btn-group { gap: 15px; }
@keyframes fadeUp { from { opacity: 0; transform: translateY(20px); } to { opacity: 1; transform: translateY(0); } }
.animate-fade-up { animation: fadeUp 0.6s ease-out forwards; }
::-webkit-scrollbar { width: 8px; }
::-webkit-scrollbar-track { background: #1a2332; }
::-webkit-scrollbar-thumb { background: var(--gold); border-radius: 10px; }
.whatsapp-float {
    position: fixed;
    bottom: 30px;
    right: 30px;
    z-index: 1000;
    background: #25D366;
    color: white;
    width: 60px;
    height: 60px;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 30px;
    box-shadow: 0 4px 15px rgba(37, 211, 102, 0.4);
    transition: transform 0.3s;
    text-decoration: none;
}
.whatsapp-float:hover { transform: scale(1.1); color: white; }
.intro-overlay {
    position: fixed;
    top: 0; left: 0; width: 100%; height: 100%;
    background: rgba(0,0,0,0.85);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 9999;
    flex-direction: column;
    text-align: center;
}
.intro-overlay .btn {
    margin-top: 30px;
}
</style>
</head>
<body>
<nav class="navbar navbar-expand-lg sticky-top"><div class="container">
<a class="navbar-brand" href="{{ url_for('index') }}">
    <svg width="40" height="40" viewBox="0 0 40 40" fill="none" xmlns="http://www.w3.org/2000/svg">
        <circle cx="20" cy="20" r="18" stroke="#D4AF37" stroke-width="2"/>
        <text x="20" y="27" text-anchor="middle" fill="#D4AF37" font-size="22" font-weight="bold" font-family="Georgia">GV</text>
        <circle cx="8" cy="8" r="2" fill="#D4AF37"/>
        <circle cx="32" cy="8" r="2" fill="#D4AF37"/>
    </svg>
    <span class="golden-text">GoldenVow</span>
</a>
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
<li class="nav-item"><a class="nav-link" href="{{ url_for('contact_messages') }}">Messages</a></li>
<li class="nav-item"><a class="nav-link" href="{{ url_for('manage_admins') }}">Manage Admins</a></li>
{% endif %}
<li class="nav-item"><a class="nav-link position-relative" href="{{ url_for('notifications') }}"><i class="bi bi-bell fs-5"></i>{% if get_unread_notifications(get_admin().id) > 0 %}<span class="position-absolute top-0 start-100 translate-middle badge rounded-pill bg-danger">{{ get_unread_notifications(get_admin().id) }}</span>{% endif %}</a></li>
<li class="nav-item"><a class="nav-link" href="{{ url_for('profile') }}"><i class="bi bi-person"></i></a></li>
<li class="nav-item"><a class="nav-link" href="{{ url_for('logout') }}"><i class="bi bi-box-arrow-right"></i></a></li>
{% else %}
    {% if request.endpoint != 'event_landing' %}
        <li class="nav-item"><a class="nav-link" href="{{ url_for('login') }}">Admin Login</a></li>
        <li class="nav-item"><a class="nav-link" href="{{ url_for('register') }}">Admin Register</a></li>
    {% endif %}
    <li class="nav-item"><a class="nav-link" href="{{ url_for('contributor_login') }}">Contributor Login</a></li>
    <li class="nav-item"><a class="nav-link" href="{{ url_for('contributor_register') }}">Contributor Register</a></li>
    <li class="nav-item"><a class="nav-link" href="{{ url_for('contact') }}">Contact</a></li>
    <li class="nav-item"><a class="nav-link" href="{{ url_for('help_page') }}"><i class="bi bi-question-circle"></i> Help</a></li>
{% endif %}
</ul>
</div></div></nav>

<a href="https://wa.me/{{ support_whatsapp }}" target="_blank" class="whatsapp-float" aria-label="Chat on WhatsApp">
    <i class="bi bi-whatsapp"></i>
</a>

<div class="container mt-3">{% with messages = get_flashed_messages(with_categories=true) %}{% if messages %}{% for category, message in messages %}<div class="alert alert-{{ 'error' if category == 'error' else 'success' if category == 'success' else 'info' }} alert-dismissible fade show glass-card">{{ message }}<button type="button" class="btn-close" data-bs-dismiss="alert"></button></div>{% endfor %}{% endif %}{% endwith %}</div>
<main class="container py-4 animate-fade-up">{% block content %}{% endblock %}</main>
<footer class="footer mt-5 py-3"><div class="container text-center"><p class="mb-1 golden-text">✦ GoldenVow – Bringing Communities Together</p><small class="text-muted-light">WhatsApp: {{ support_whatsapp }} &nbsp;|&nbsp; Email: {{ support_email }}</small></div></footer>
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
{% block scripts %}{% endblock %}
</body>
</html>
"""

# ---------- CUSTOM JINJA LOADER ----------
class StringLoader(BaseLoader):
    def __init__(self, base_html):
        self.base_html = base_html
    def get_source(self, environment, template):
        if template == 'base.html':
            return self.base_html, None, lambda: True
        raise TemplateNotFound(template)

app.jinja_env.loader = StringLoader(BASE_HTML)

# ---------- LANDING PAGE WITH VOICE WELCOME AND OVERLAY ----------
LANDING_HTML = """
{% extends "base.html" %}
{% block title %}Welcome to GoldenVow{% endblock %}
{% block content %}
<div class="intro-overlay" id="introOverlay">
    <div class="glass-card p-5" style="max-width: 600px;">
        <svg width="80" height="80" viewBox="0 0 40 40" fill="none" xmlns="http://www.w3.org/2000/svg">
            <circle cx="20" cy="20" r="18" stroke="#D4AF37" stroke-width="2"/>
            <text x="20" y="27" text-anchor="middle" fill="#D4AF37" font-size="22" font-weight="bold" font-family="Georgia">GV</text>
            <circle cx="8" cy="8" r="2" fill="#D4AF37"/>
            <circle cx="32" cy="8" r="2" fill="#D4AF37"/>
        </svg>
        <h1 class="golden-text display-4">GoldenVow</h1>
        <p class="lead text-light">Transforming communities through transparent fundraising.</p>
        <p class="text-muted-light">Your journey to meaningful contributions starts here.</p>
        <button class="btn btn-gold btn-lg" onclick="enterSite()">Enter GoldenVow</button>
    </div>
</div>

<section class="hero">
    <div class="glass-card p-5" style="max-width: 800px; margin: 0 auto;">
        <div class="text-center mb-4">
            <svg width="80" height="80" viewBox="0 0 40 40" fill="none" xmlns="http://www.w3.org/2000/svg">
                <circle cx="20" cy="20" r="18" stroke="#D4AF37" stroke-width="2"/>
                <text x="20" y="27" text-anchor="middle" fill="#D4AF37" font-size="22" font-weight="bold" font-family="Georgia">GV</text>
                <circle cx="8" cy="8" r="2" fill="#D4AF37"/>
                <circle cx="32" cy="8" r="2" fill="#D4AF37"/>
            </svg>
        </div>
        <h1 class="golden-text">✦ GoldenVow</h1>
        <p class="lead">Bringing communities together through <span class="golden-text">transparent fundraising</span>.</p>
        <p class="text-muted-light">Start a campaign, manage contributions, and earn fees – all in one platform.</p>
        <div class="btn-group mt-4 flex-wrap justify-content-center">
            <a href="{{ url_for('login') }}" class="btn btn-gold">Admin Login</a>
            <a href="{{ url_for('register') }}" class="btn btn-outline-gold">Register as Admin</a>
            <a href="{{ url_for('contributor_login') }}" class="btn btn-outline-gold">Contributor Login</a>
            <a href="{{ url_for('contact') }}" class="btn btn-outline-gold">Contact Us</a>
        </div>
        <hr class="border-gold opacity-25">
        <div class="row mt-4">
            <div class="col-md-4">
                <i class="bi bi-calendar-event fs-1 golden-text"></i>
                <h5>Create Events</h5>
                <p class="small text-muted-light">Set up fundraising events in minutes.</p>
            </div>
            <div class="col-md-4">
                <i class="bi bi-people fs-1 golden-text"></i>
                <h5>Manage Contributors</h5>
                <p class="small text-muted-light">Track pledges, uploads, and approvals.</p>
            </div>
            <div class="col-md-4">
                <i class="bi bi-graph-up fs-1 golden-text"></i>
                <h5>Earn Fees</h5>
                <p class="small text-muted-light">2% platform fee on every contribution.</p>
            </div>
        </div>
    </div>
</section>

<script>
    // Auto-play voice greeting (male voice) when page loads
    window.addEventListener('load', function() {
        const msg = "Welcome to GoldenVow, transforming communities through transparent fundraising.";
        const utterance = new SpeechSynthesisUtterance(msg);
        utterance.rate = 0.9;
        utterance.pitch = 0.9;
        utterance.voice = speechSynthesis.getVoices().find(v => v.lang === 'en-US' && v.name.toLowerCase().includes('male')) || null;
        speechSynthesis.speak(utterance);
    });

    // Enter site – hide overlay and show content
    function enterSite() {
        document.getElementById('introOverlay').style.display = 'none';
    }
</script>
{% endblock %}
"""

# ---------- HTML TEMPLATES FOR ALL PAGES ----------
LOGIN_HTML = """
{% extends "base.html" %}
{% block content %}
<div class="row justify-content-center"><div class="col-md-5 col-lg-4"><div class="glass-card p-4"><h3 class="text-center golden-text">✦ Admin Login</h3><hr><form method="POST"><div class="mb-3"><label class="form-label">Username</label><input type="text" name="username" class="form-control" placeholder="Enter username" required></div><div class="mb-3"><label class="form-label">Password</label><input type="password" name="password" class="form-control" placeholder="Enter password" required></div><button type="submit" class="btn btn-gold w-100">Login</button></form><div class="mt-3 text-center"><a href="{{ url_for('forgot_password') }}" class="text-muted-light">Forgot password?</a><br><small class="text-muted-light">Don't have an account? <a href="{{ url_for('register') }}" class="golden-text">Register</a></small><hr><small class="text-muted-light">Contributor? <a href="{{ url_for('contributor_login') }}" class="golden-text">Login here</a></small></div></div></div></div>
{% endblock %}
"""

REGISTER_HTML = """
{% extends "base.html" %}
{% block content %}
<div class="row justify-content-center"><div class="col-md-6 col-lg-5"><div class="glass-card p-4"><h3 class="text-center golden-text">✦ Create Admin Account</h3><hr><form method="POST"><div class="mb-2"><label class="form-label">Username <span class="text-danger">*</span></label><input type="text" name="username" class="form-control" placeholder="Choose a username" required></div><div class="mb-2"><label class="form-label">Email <span class="text-danger">*</span></label><input type="email" name="email" class="form-control" placeholder="you@example.com" required></div><div class="mb-2"><label class="form-label">Phone</label><input type="tel" name="phone" class="form-control" placeholder="Phone number"></div><div class="mb-2"><label class="form-label">Password <span class="text-danger">*</span></label><input type="password" name="password" class="form-control" placeholder="Create a password" required></div><div class="mb-2"><label class="form-label">Referral Code (optional)</label><input type="text" name="referral_code" class="form-control" placeholder="Enter referral code"></div><div class="mb-3"><label class="form-label">Super Admin Secret (if applicable)</label><input type="password" name="super_secret" class="form-control" placeholder="Only if you're the developer"></div><button type="submit" class="btn btn-gold w-100">Register</button></form><div class="mt-3 text-center"><small class="text-muted-light">Already have an account? <a href="{{ url_for('login') }}" class="golden-text">Login</a></small></div></div></div></div>
{% endblock %}
"""

DASHBOARD_HTML = """
{% extends "base.html" %}
{% block content %}
<div class="d-flex justify-content-between align-items-center mb-4 flex-wrap"><h2 class="golden-text">👋 Welcome, {{ admin.username }}</h2><div class="d-flex gap-2"><a href="{{ url_for('contact_super') }}" class="btn btn-outline-gold"><i class="bi bi-envelope"></i> Contact Super Admin</a><a href="{{ url_for('create_event') }}" class="btn btn-gold"><i class="bi bi-plus-circle"></i> New Event</a></div></div>
<div class="glass-card p-3 mb-4"><h5 class="golden-text"><i class="bi bi-lightbulb"></i> Quick Tips</h5><ul class="text-muted-light"><li>🔑 <strong>Account Name:</strong> Always set the exact name contributors will see when sending money. The system will use this for verification.</li><li>📸 <strong>Payment Proof:</strong> Contributors upload screenshots. You review and click <strong>Approve</strong>.</li><li>📖 <strong>Full Guide:</strong> Click <a href="{{ url_for('help_page') }}" class="golden-text">Help</a> for detailed instructions.</li><li>⚠️ <strong>Event Locking:</strong> If fees reach KES 50+, your event will lock after 3 days if not paid.</li></ul></div>
<div class="row g-3 mb-4"><div class="col-md-3 col-6"><div class="glass-card p-3 text-center"><h3 class="golden-text">{{ events.total }}</h3><small class="text-muted-light">Events</small></div></div><div class="col-md-3 col-6"><div class="glass-card p-3 text-center"><h3 class="golden-text">KES {{ total_raised|round(2)|int }}</h3><small class="text-muted-light">Total Raised</small></div></div><div class="col-md-3 col-6"><div class="glass-card p-3 text-center"><h3 class="golden-text">{{ pending_contributions }}</h3><small class="text-muted-light">Pending Approvals</small></div></div><div class="col-md-3 col-6"><div class="glass-card p-3 text-center"><h3 class="golden-text">{{ admin.referral_count }}</h3><small class="text-muted-light">Referrals</small></div></div></div>
<h4 class="golden-text">📋 Your Events</h4><div class="row">{% for event in events.items %}<div class="col-md-6 col-lg-4 mb-3"><div class="glass-card h-100 p-3"><div class="d-flex justify-content-between align-items-center"><h5>{{ event.title }}</h5><span class="badge bg-secondary">{{ event.event_type|title }}</span></div><p class="mt-2">Raised: <strong>KES {{ get_event_total_contributions(event.id)|round(2) }}</strong> / {{ event.target_amount|round(2) }}</p><div class="progress" style="height:6px;"><div class="progress-bar progress-bar-gold" style="width:{{ (get_event_total_contributions(event.id)/event.target_amount*100)|round(0) if event.target_amount>0 else 0 }}%;"></div></div><small class="text-muted-light">Status: {{ 'Active' if event.is_active and not event.disabled else 'Inactive/Locked' }}</small>{% if event.account_name %}<small class="d-block text-muted-light">Account: {{ event.account_name }}</small>{% endif %}<div class="mt-2 d-flex flex-wrap gap-1"><a href="{{ url_for('event_landing', token=event.token) }}" class="btn btn-sm btn-outline-gold">View</a><a href="{{ url_for('edit_event', token=event.token) }}" class="btn btn-sm btn-outline-secondary">Edit</a><a href="{{ url_for('manage_contributors', token=event.token) }}" class="btn btn-sm btn-outline-info">Contributors</a><form method="POST" action="{{ url_for('toggle_event_active', token=event.token) }}" style="display:inline;"><button type="submit" class="btn btn-sm btn-{{ 'danger' if event.is_active else 'success' }}">{{ 'Disable' if event.is_active else 'Enable' }}</button></form></div></div></div>{% else %}<p class="text-muted-light">No events yet. <a href="{{ url_for('create_event') }}" class="golden-text">Create one now</a>.</p>{% endfor %}</div>
{% if events.pages > 1 %}<nav><ul class="pagination justify-content-center">{% if events.has_prev %}<li class="page-item"><a class="page-link bg-dark text-light border-0" href="?page={{ events.prev_num }}">Previous</a></li>{% endif %}<li class="page-item active"><span class="page-link bg-gold text-dark border-0">{{ events.page }}</span></li>{% if events.has_next %}<li class="page-item"><a class="page-link bg-dark text-light border-0" href="?page={{ events.next_num }}">Next</a></li>{% endif %}</ul></nav>{% endif %}
<div class="mt-3 text-center"><a href="{{ url_for('help_page') }}" class="text-muted-light"><i class="bi bi-question-circle"></i> Need help? Read the Admin Guide</a></div>
{% endblock %}
"""

SUPER_DASHBOARD_HTML = """
{% extends "base.html" %}
{% block content %}
<div class="d-flex justify-content-between align-items-center mb-4"><h2 class="golden-text">👑 Super Admin Dashboard</h2><span class="badge bg-gold text-dark">You are the Super Admin</span></div>
<div class="row g-3 mb-4"><div class="col-md-3 col-6"><div class="glass-card p-3 text-center"><h3 class="golden-text">{{ total_events }}</h3><small>Total Events (All Admins)</small></div></div><div class="col-md-3 col-6"><div class="glass-card p-3 text-center"><h3 class="golden-text">KES {{ total_contributions|round(2)|int }}</h3><small>Total Raised (Global)</small></div></div><div class="col-md-3 col-6"><div class="glass-card p-3 text-center"><h3 class="golden-text">KES {{ total_fees|round(2) }}</h3><small>Your Fees Collected (2%)</small>{% if total_fees < minimum_withdrawal_fee %}<div class="text-warning small mt-1">🔒 Need KES {{ minimum_withdrawal_fee|round(0) }} to withdraw</div>{% else %}<div class="text-success small mt-1">✅ Ready to withdraw!</div>{% endif %}</div></div><div class="col-md-3 col-6"><div class="glass-card p-3 text-center"><h3 class="golden-text">{{ pending_withdrawals }}</h3><small>Pending Withdrawals</small></div></div></div>
<div class="glass-card p-3 mb-4"><div class="d-flex justify-content-between align-items-center"><div><h5 class="golden-text">💰 Withdraw Your Fees</h5><p class="text-muted-light small mb-0">{% if total_fees >= minimum_withdrawal_fee %}✅ You have KES {{ total_fees|round(2) }} available. Min: KES {{ minimum_withdrawal_fee|round(0) }}{% else %}⚠️ Need at least KES {{ minimum_withdrawal_fee|round(0) }}. Current: KES {{ total_fees|round(2) }}{% endif %}</p></div><button class="btn btn-gold" data-bs-toggle="modal" data-bs-target="#withdrawalModal" {% if total_fees < minimum_withdrawal_fee %}disabled{% endif %}><i class="bi bi-arrow-up-circle"></i> Request Withdrawal</button></div></div>
<div class="row g-3 mb-4"><div class="col-md-3"><a href="{{ url_for('manage_admins') }}" class="text-decoration-none"><div class="glass-card p-3 text-center"><i class="bi bi-people fs-2 golden-text"></i><p>Manage Admins</p></div></a></div><div class="col-md-3"><a href="{{ url_for('withdrawals') }}" class="text-decoration-none"><div class="glass-card p-3 text-center"><i class="bi bi-arrow-up-circle fs-2 golden-text"></i><p>Manage Withdrawals</p></div></a></div><div class="col-md-3"><a href="{{ url_for('settings') }}" class="text-decoration-none"><div class="glass-card p-3 text-center"><i class="bi bi-gear fs-2 golden-text"></i><p>System Settings</p></div></a></div><div class="col-md-3"><a href="{{ url_for('manage_feature_requests') }}" class="text-decoration-none"><div class="glass-card p-3 text-center"><i class="bi bi-lightbulb fs-2 golden-text"></i><p>Feature Requests</p></div></a></div></div>
<h4 class="golden-text">👥 All Admins</h4><div class="table-responsive"><table class="table table-dark table-hover"><thead><tr><th>Username</th><th>Email</th><th>Referrals</th><th>Status</th><th>Action</th></tr></thead><tbody>{% for a in admins %}<tr><td>{{ a.username }} {% if a.is_super_admin %}👑{% endif %}</td><td>{{ a.email }}</td><td>{{ a.referral_count }}</td><td>{% if a.is_active %}<span class="badge bg-success">Active</span>{% else %}<span class="badge bg-danger">Disabled</span>{% endif %}</td><td>{% if not a.is_super_admin %}<form method="POST" action="{{ url_for('toggle_admin', aid=a.id) }}" style="display:inline;"><button type="submit" class="btn btn-sm btn-outline-warning">{{ 'Disable' if a.is_active else 'Enable' }}</button></form><form method="POST" action="{{ url_for('delete_admin', aid=a.id) }}" style="display:inline;" onsubmit="return confirm('Delete this admin?');"><button type="submit" class="btn btn-sm btn-outline-danger">Delete</button></form>{% else %}<span class="text-muted-light">Protected</span>{% endif %}</td></tr>{% endfor %}</tbody></table></div>
{% if locked_events > 0 %}<div class="mt-4"><div class="glass-card p-3"><h5 class="golden-text">🔒 Locked Events ({{ locked_events }})</h5><p class="text-muted-light">These events are locked because fees (>= 50 bob) are overdue.</p><a href="{{ url_for('super_dashboard') }}" class="btn btn-sm btn-outline-gold">View All</a></div></div>{% endif %}
<div class="modal fade" id="withdrawalModal" tabindex="-1"><div class="modal-dialog"><div class="modal-content glass-card"><div class="modal-header border-0"><h5 class="modal-title golden-text">Request Withdrawal</h5><button type="button" class="btn-close" data-bs-dismiss="modal"></button></div><form method="POST" action="{{ url_for('request_withdrawal') }}"><div class="modal-body"><div class="mb-3"><label class="form-label">Amount (KES)</label><input type="number" name="amount" class="form-control" step="0.01" min="{{ minimum_withdrawal_fee }}" required><small class="text-muted-light">Minimum: KES {{ minimum_withdrawal_fee|round(0) }}. Available: KES {{ total_fees|round(2) }}</small></div><div class="mb-3"><label class="form-label">Phone Number</label><input type="tel" name="phone" class="form-control" required></div><div class="mb-3"><label class="form-label">Method</label><select name="method" class="form-select"><option value="mpesa">M-Pesa</option><option value="bank">Bank Transfer</option></select></div></div><div class="modal-footer border-0"><button type="submit" class="btn btn-gold">Submit Request</button></div></form></div></div></div>
{% endblock %}
"""

CREATE_EVENT_HTML = """
{% extends "base.html" %}
{% block content %}
<h2 class="golden-text">✨ Create New Event</h2>
<div class="glass-card p-4">
<form method="POST" class="row g-3">
<div class="col-md-6"><label class="form-label">Event Type</label><select name="event_type" class="form-select"><option value="dowry">🐂 Dowry</option><option value="burial">🕊️ Burial</option><option value="medical">❤️ Medical</option><option value="education">🎓 Education</option><option value="harambee">🤝 Harambee</option><option value="other">✦ Other</option></select></div>
<div class="col-md-6"><label class="form-label">Event Title <span class="text-danger">*</span></label><input type="text" name="title" class="form-control" placeholder="e.g. Wedding Fundraiser" required></div>
<div class="col-12"><label class="form-label">Description</label><textarea name="description" class="form-control" rows="3" placeholder="Describe your event"></textarea></div>
<div class="col-md-4"><label class="form-label">Target Amount (KES) <span class="text-danger">*</span></label><input type="number" name="target_amount" class="form-control" step="0.01" placeholder="e.g. 50000" required></div>
<div class="col-md-4"><label class="form-label">Event Date <span class="text-danger">*</span></label><input type="datetime-local" name="event_date" class="form-control" required></div>
<div class="col-md-4"><label class="form-label">Deadline <span class="text-danger">*</span></label><input type="datetime-local" name="deadline" class="form-control" required></div>
<div class="col-12"><label class="form-label">Picture URL (optional)</label><input type="url" name="picture_url" class="form-control" placeholder="https://example.com/image.jpg"></div>
<div class="col-12"><label class="form-label">Background Image URL (optional)</label><input type="url" name="background_image_url" class="form-control" placeholder="https://example.com/bg.jpg"></div>
<h5 class="golden-text mt-3">💳 Payment Details</h5>
<div class="col-md-12"><label class="form-label">Account Name (M-Pesa/Bank Account Holder) <span class="text-danger">*</span></label><input type="text" name="account_name" class="form-control" placeholder="e.g. Alex Kiprop" required><div class="text-muted-light small mt-1"><i class="bi bi-info-circle"></i> This is the name contributors will see when sending money.</div></div>
<div class="col-md-3"><label class="form-label">Paybill</label><input type="text" name="paybill" class="form-control" placeholder="Paybill number"></div>
<div class="col-md-3"><label class="form-label">M-Pesa Number</label><input type="text" name="mpesa_number" class="form-control" placeholder="M-Pesa number"></div>
<div class="col-md-3"><label class="form-label">Till Number</label><input type="text" name="till_number" class="form-control" placeholder="Till number"></div>
<div class="col-md-3"><label class="form-label">WhatsApp Contact</label><input type="text" name="whatsapp_contact" class="form-control" placeholder="WhatsApp number"></div>
<div class="col-md-4"><label class="form-label">Bank Name</label><input type="text" name="bank_name" class="form-control" placeholder="Bank name"></div>
<div class="col-md-4"><label class="form-label">Bank Account Name</label><input type="text" name="bank_account_name" class="form-control" placeholder="Account name on bank"></div>
<div class="col-md-4"><label class="form-label">Bank Account Number</label><input type="text" name="bank_account_number" class="form-control" placeholder="Bank account number"></div>
<div class="col-12"><label class="form-label">Payment Instructions</label><textarea name="payment_instructions" class="form-control" rows="2" placeholder="e.g. Send money to the above details and upload proof."></textarea></div>
<div class="col-md-6"><div class="form-check"><input class="form-check-input" type="checkbox" name="has_grace_period" value="1"><label class="form-check-label">Enable Grace Period</label></div></div>
<div class="col-md-6"><label class="form-label">Grace Period (days)</label><input type="number" name="grace_period" class="form-control" value="0"></div>
<div class="col-12"><button type="submit" class="btn btn-gold">🚀 Create Event</button><a href="{{ url_for('dashboard') }}" class="btn btn-outline-secondary">Cancel</a></div>
</form>
</div>
{% endblock %}
"""

EVENT_LANDING_HTML = """
{% extends "base.html" %}
{% block content %}
<div class="text-center mb-4"><div class="glass-card p-4"><div class="mb-3">{{ generate_event_logo(event, 100)|safe }}</div>
<h1 class="golden-text">{{ event.title }}</h1><p class="text-muted-light">{{ event.event_type|title }} • {{ event.event_date.strftime('%B %d, %Y') }}</p><p>{{ event.description }}</p>
<div class="progress" style="height:25px;"><div class="progress-bar progress-bar-gold" id="progressBar" style="width:{{ (total_raised/event.target_amount*100)|round(0) if event.target_amount>0 else 0 }}%;"><span id="progressText">{{ (total_raised/event.target_amount*100)|round(0) if event.target_amount>0 else 0 }}%</span></div></div>
<h3 id="totalRaised" class="mt-2 golden-text">KES {{ total_raised|round(2) }}</h3><p class="text-muted-light">Target: KES {{ event.target_amount|round(2) }} • Deadline: {{ event.deadline.strftime('%B %d, %Y at %H:%M') }}</p></div></div>
<div class="alert glass-card text-center">{{ daily_note }}</div>
<div class="glass-card p-3 mb-3">{% if contributor %}<div class="d-flex justify-content-between align-items-center"><div><i class="bi bi-check-circle-fill golden-text"></i> Logged in as: <strong>{{ contributor.name }}</strong></div><a href="{{ url_for('contributor_logout') }}" class="btn btn-sm btn-outline-gold">Logout</a></div>{% else %}<div class="text-center"><p class="text-muted-light">Have an account? Log in to contribute faster!</p><div class="d-flex justify-content-center gap-2"><a href="{{ url_for('contributor_login', event_token=event.token) }}" class="btn btn-outline-gold"><i class="bi bi-box-arrow-in-right"></i> Login</a><a href="{{ url_for('contributor_register', event_token=event.token) }}" class="btn btn-gold"><i class="bi bi-person-plus"></i> Register</a></div></div>{% endif %}</div>
<div class="glass-card p-3 mb-3"><h5 class="golden-text">💰 Payment Instructions</h5>{% if event.account_name %}<div class="alert alert-success bg-dark text-light" style="border-left:4px solid var(--gold);"><i class="bi bi-person-check golden-text"></i> <strong>Send money to:</strong> <span class="golden-text fs-5">{{ event.account_name }}</span><br><small class="text-muted-light">Please use this exact name when sending money.</small></div>{% endif %}{{ event.payment_instructions or 'Contact the organiser for payment details.' }}{% if event.paybill %}<p><strong>Paybill:</strong> {{ event.paybill }}</p>{% endif %}{% if event.mpesa_number %}<p><strong>M-Pesa:</strong> {{ event.mpesa_number }}</p>{% endif %}{% if event.till_number %}<p><strong>Till:</strong> {{ event.till_number }}</p>{% endif %}<p class="text-muted-light small">Fee: {{ fee_percentage }}% of contribution.</p></div>
<div class="glass-card p-3 mb-3"><h5 class="golden-text">📎 Submit Payment Proof</h5><form method="POST" action="{{ url_for('submit_payment_proof', token=event.token) }}" enctype="multipart/form-data"><div class="mb-2"><label class="form-label">Your Name (as registered)</label><input type="text" name="contributor_name" class="form-control" value="{{ contributor.name if contributor else '' }}" readonly></div><div class="mb-2"><label class="form-label">Payment Screenshot</label><input type="file" name="screenshot" class="form-control" accept="image/*"></div><div class="mb-2"><label class="form-label">Additional Info (transaction code, etc.)</label><textarea name="payment_proof_text" class="form-control" rows="2"></textarea></div><button type="submit" class="btn btn-gold">Submit Proof</button></form></div>
<div class="glass-card p-3 mb-3"><h5 class="golden-text">💬 Live Chat</h5><div id="chatMessages" style="max-height:200px; overflow-y:auto;">{% for msg in chat_messages %}<div><strong>{{ msg.sender_name }}</strong>: {{ msg.message }} <small class="text-muted-light">{{ msg.timestamp.strftime('%H:%M') }}</small></div>{% endfor %}</div><form id="chatForm" class="d-flex mt-2"><input type="text" id="chatName" class="form-control me-1" placeholder="Your name" style="max-width:150px;" value="{{ contributor.name if contributor else 'Anonymous' }}"><input type="text" id="chatMessage" class="form-control me-1" placeholder="Message..." required><button type="submit" class="btn btn-gold">Send</button></form></div>
<div class="glass-card p-3 mb-3"><h5 class="golden-text">⭐ Testimonials</h5>{% for t in testimonials %}<div><strong>{{ t.message[:50] }}</strong> ({{ t.rating }}★) <small class="text-muted-light">{{ t.created_at.strftime('%d/%m') }}</small></div>{% endfor %}<form method="POST" action="{{ url_for('add_testimonial', token=event.token) }}" class="mt-2"><input type="text" name="name" class="form-control mb-1" placeholder="Your name" required><input type="number" name="rating" min="1" max="5" class="form-control mb-1" placeholder="Rating 1-5" required><input type="text" name="message" class="form-control mb-1" placeholder="Your message" required><button type="submit" class="btn btn-sm btn-gold">Submit</button></form></div>
<div class="text-center mt-3"><a href="{{ url_for('submit_feature_request', event_token=event.token) }}" class="btn btn-outline-gold"><i class="bi bi-lightbulb"></i> Suggest a New Feature</a></div>
{% endblock %}
"""

CONTRIBUTORS_HTML = """
{% extends "base.html" %}
{% block content %}
<div class="d-flex justify-content-between align-items-center mb-3"><h2 class="golden-text">👥 Contributors</h2><span class="badge bg-gold text-dark">{{ event.title }}</span></div>
<p class="text-muted-light">Total Raised: <strong class="golden-text">KES {{ get_event_total_contributions(event.id)|round(2) }}</strong></p>
<div class="glass-card p-3 mb-4"><h5 class="golden-text">➕ Add New Contributor</h5><form method="POST" action="{{ url_for('add_contributor', token=event.token) }}" class="row g-2"><div class="col-md-3"><input type="text" name="name" class="form-control" placeholder="Full Name" required></div><div class="col-md-3"><input type="tel" name="phone" class="form-control" placeholder="Phone" required></div><div class="col-md-3"><input type="number" name="pledge_amount" class="form-control" placeholder="Amount (KES)" step="0.01" required></div><div class="col-md-3"><button type="submit" class="btn btn-gold w-100">Add</button></div></form></div>
<div class="table-responsive"><table class="table table-dark table-hover"><thead><tr><th>Name</th><th>Phone</th><th>Pledge</th><th>Paid</th><th>Fee</th><th>Status</th><th>Action</th></tr></thead><tbody>{% for c in contributors.items %}<tr><td>{{ c.name }}{% if c.username %}<span class="badge bg-info text-dark">👤 {{ c.username }}</span>{% endif %}</td><td>{{ c.phone }}</td><td>KES {{ c.pledge_amount|round(2) }}</td><td>KES {{ c.paid_amount|round(2) }}</td><td>KES {{ c.fee_amount|round(2) }}</td><td><span class="badge bg-{{ 'success' if c.status == 'approved' else 'warning' if c.status == 'pending' else 'danger' }}">{{ c.status|title }}</span>{% if c.auto_verified %}<span class="badge bg-success">🤖 System Verified</span>{% endif %}{% if c.status == 'pending' and c.sender_name %}{% if c.sender_name.lower().strip() == event.account_name.lower().strip() %}<span class="badge bg-success">✅ Name Match</span>{% else %}<span class="badge bg-danger">❌ Name Mismatch</span>{% endif %}{% endif %}</td><td>{% if c.payment_proof_screenshot %}<a href="{{ url_for('static', filename=c.payment_proof_screenshot.replace('static/', '')) }}" target="_blank" class="btn btn-sm btn-outline-info"><i class="bi bi-image"></i> View Proof</a>{% endif %}{% if c.status == 'pending' %}<form method="POST" action="{{ url_for('approve_contributor', token=c.token) }}" class="d-inline"><input type="number" name="received_amount" class="form-control form-control-sm d-inline" style="width:100px;" step="0.01" placeholder="Amount received" required><button type="submit" class="btn btn-sm btn-success">✅ Approve</button></form><form method="POST" action="{{ url_for('decline_contributor', token=c.token) }}" class="d-inline"><input type="text" name="reason" class="form-control form-control-sm d-inline" style="width:100px;" placeholder="Reason"><button type="submit" class="btn btn-sm btn-danger">❌ Decline</button></form>{% endif %}<a href="{{ url_for('contributor_view', token=c.token) }}" class="btn btn-sm btn-outline-info">View</a></td></tr>{% endfor %}</tbody></table></div>
{% if contributors.pages > 1 %}<nav><ul class="pagination justify-content-center">{% if contributors.has_prev %}<li class="page-item"><a class="page-link bg-dark text-light border-0" href="?page={{ contributors.prev_num }}">Previous</a></li>{% endif %}<li class="page-item active"><span class="page-link bg-gold text-dark border-0">{{ contributors.page }}</span></li>{% if contributors.has_next %}<li class="page-item"><a class="page-link bg-dark text-light border-0" href="?page={{ contributors.next_num }}">Next</a></li>{% endif %}</ul></nav>{% endif %}
<div class="mt-3 text-center"><a href="{{ url_for('dashboard') }}" class="text-muted-light">← Back to Dashboard</a></div>
{% endblock %}
"""

CONTRIBUTOR_VIEW_HTML = """
{% extends "base.html" %}
{% block content %}
<div class="glass-card p-4"><h2 class="golden-text">👤 {{ contrib.name }}</h2><p><strong>Phone:</strong> {{ contrib.phone }}</p><p><strong>Username:</strong> {{ contrib.username or 'Not registered' }}</p><p><strong>Pledge Amount:</strong> KES {{ contrib.pledge_amount|round(2) }}</p><p><strong>Amount Paid:</strong> KES {{ contrib.paid_amount|round(2) }}</p><p><strong>Fee (2%):</strong> KES {{ contrib.fee_amount|round(2) }}</p><p><strong>Net Contribution:</strong> KES {{ contrib.net_contribution|round(2) }}</p><p><strong>Sender Name (from proof):</strong> {{ contrib.sender_name or 'Not provided' }}</p><p><strong>Status:</strong> <span class="badge bg-{{ 'success' if contrib.status == 'approved' else 'warning' if contrib.status == 'pending' else 'danger' }}">{{ contrib.status|title }}</span>{% if contrib.auto_verified %}<span class="badge bg-success">🤖 System Verified</span>{% endif %}</p>{% if contrib.status == 'pending' %}<div class="alert alert-warning"><i class="bi bi-clock"></i> Your contribution is pending admin approval.{% if contrib.sender_name and contrib.sender_name.lower().strip() == event.account_name.lower().strip() %}<br>✅ The system has verified your name matches the account.{% elif contrib.sender_name %}<br>⚠️ Your sender name doesn't match the account name. Admin will review.{% endif %}</div>{% elif contrib.status == 'approved' and contrib.auto_verified %}<div class="alert alert-success"><i class="bi bi-check-circle-fill"></i> ✅ Your payment was system-verified and approved!</div>{% elif contrib.status == 'approved' %}<div class="alert alert-success"><i class="bi bi-check-circle"></i> ✅ Your contribution has been approved by the admin.</div>{% endif %}</div>
<div class="glass-card p-4 mt-3"><h5 class="golden-text">📎 Submit Payment Proof</h5><form method="POST" action="{{ url_for('submit_payment_proof', token=contrib.token) }}" enctype="multipart/form-data"><div class="mb-2"><label class="form-label">Payment Screenshot</label><input type="file" name="screenshot" class="form-control" accept="image/*"></div><div class="mb-2"><label class="form-label">Additional Info (transaction code, etc.)</label><textarea name="payment_proof_text" class="form-control" rows="2">{{ contrib.payment_proof_text or '' }}</textarea></div><button type="submit" class="btn btn-gold">Submit Proof</button></form></div>
{% if contrib.payment_proof_screenshot %}<div class="glass-card p-4 mt-3"><h5 class="golden-text">📸 Your Payment Screenshot</h5><a href="{{ url_for('static', filename=contrib.payment_proof_screenshot.replace('static/', '')) }}" target="_blank"><img src="{{ url_for('static', filename=contrib.payment_proof_screenshot.replace('static/', '')) }}" alt="Payment proof" style="max-width:100%; max-height:300px; border-radius:12px; border:2px solid var(--gold);"></a><p class="text-muted-light small mt-1"><i class="bi bi-eye"></i> Click to view full size</p></div>{% endif %}
<div class="glass-card p-4 mt-3"><h5 class="golden-text">💳 Payment History</h5>{% if show_payments and payments %}<ul class="list-group list-group-flush bg-transparent">{% for p in payments %}<li class="list-group-item bg-transparent text-light d-flex justify-content-between"><span>KES {{ p.amount|round(2) }}</span><span class="text-muted-light">{{ p.date_paid.strftime('%Y-%m-%d %H:%M') }}</span></li>{% endfor %}</ul>{% elif show_payments and not payments %}<p class="text-muted-light">No payments recorded yet.</p>{% else %}<p class="text-muted-light"><i class="bi bi-lock"></i> Payment history will be available after 7 days.<br><small>Contact the event admin if you need it earlier.</small></p>{% endif %}</div>
<div class="glass-card p-4 mt-3 text-center"><a href="{{ url_for('contributor_chat', token=contrib.token) }}" class="btn btn-outline-gold"><i class="bi bi-chat-dots"></i> Chat with Admin</a></div>
{% if contrib.status == 'approved' and contrib.completed_at %}{% if is_admin_user %}<div class="glass-card p-4 mt-3 text-center"><a href="{{ url_for('contributor_receipt', token=contrib.token) }}" class="btn btn-gold"><i class="bi bi-file-pdf"></i> Download Receipt (PDF) – Admin</a></div>{% elif is_contributor_owner and (now - contrib.completed_at).days >= 7 %}<div class="glass-card p-4 mt-3 text-center"><a href="{{ url_for('contributor_receipt', token=contrib.token) }}" class="btn btn-gold"><i class="bi bi-file-pdf"></i> Download Receipt (PDF)</a></div>{% elif is_contributor_owner %}<div class="glass-card p-4 mt-3 text-center text-muted-light"><i class="bi bi-clock"></i> Receipt will be available after 7 days.<br><small>Contact the event admin if you need it earlier.</small></div>{% endif %}{% endif %}
<div class="mt-3 text-center"><a href="{{ url_for('manage_contributors', token=event.token) if is_admin_user else url_for('contributor_dashboard') }}" class="text-muted-light">← Back to {{ 'Contributors' if is_admin_user else 'Dashboard' }}</a></div>
{% endblock %}
"""

HELP_HTML = """
{% extends "base.html" %}
{% block title %}Help & AI Assistant{% endblock %}
{% block content %}
<div class="row">
    <div class="col-md-8 mx-auto">
        <div class="glass-card p-4">
            <h2 class="golden-text text-center">🤖 AI Help Assistant</h2>
            <p class="text-muted-light text-center">Ask me anything about GoldenVow!</p>
            <div id="chatBox" style="height: 300px; overflow-y: auto; background: rgba(0,0,0,0.2); border-radius: 12px; padding: 15px; margin-bottom: 15px;">
                <div class="text-muted-light"><i class="bi bi-robot"></i> Hello! I'm your AI assistant. Ask me about events, contributions, fees, or anything else.</div>
            </div>
            <div class="input-group">
                <input type="text" id="userQuestion" class="form-control" placeholder="Type your question...">
                <button class="btn btn-gold" onclick="askAI()">Ask</button>
            </div>
            <hr>
            <h5 class="golden-text">📋 Quick FAQs</h5>
            <ul class="list-unstyled">
                <li><a href="#" onclick="askQuestion('How do I create an event?')">How do I create an event?</a></li>
                <li><a href="#" onclick="askQuestion('How are fees calculated?')">How are fees calculated?</a></li>
                <li><a href="#" onclick="askQuestion('What is the 50 bob rule?')">What is the 50 bob rule?</a></li>
                <li><a href="#" onclick="askQuestion('How do I withdraw my earnings?')">How do I withdraw my earnings?</a></li>
            </ul>
        </div>
    </div>
</div>
<script>
const answers = {
    "how do i create an event": "To create an event, log in as an admin, go to Dashboard, and click 'New Event'. Fill in the details like title, target amount, account name, and payment instructions. Then click 'Create'.",
    "how are fees calculated": "The platform fee is 2% of the actual amount received (not the pledge). For example, if a contributor sends KES 1,000, the fee is KES 20. Referral discounts can lower your fee percentage.",
    "what is the 50 bob rule": "Events lock automatically if the total unpaid fee reaches KES 50 or more and is not paid within 3 days of the first contribution. Pay the fee to the Super Admin to unlock.",
    "how do i withdraw my earnings": "Only Super Admin can withdraw fees. Go to Super Dashboard, click 'Request Withdrawal', enter the amount (minimum KES 50), and submit. The Super Admin will process it.",
    "default": "I'm sorry, I don't have an answer for that yet. Please contact support via WhatsApp or email."
};
function askQuestion(q) {
    document.getElementById('userQuestion').value = q;
    askAI();
}
function askAI() {
    const input = document.getElementById('userQuestion');
    const question = input.value.trim().toLowerCase();
    if (!question) return;
    const chat = document.getElementById('chatBox');
    chat.innerHTML += `<div class="text-end mt-2"><span class="badge bg-primary">You</span> ${question}</div>`;
    input.value = '';
    let answer = answers['default'];
    for (let key in answers) {
        if (question.includes(key)) {
            answer = answers[key];
            break;
        }
    }
    setTimeout(() => {
        chat.innerHTML += `<div class="mt-2"><span class="badge bg-gold text-dark">🤖 AI</span> ${answer}</div>`;
        chat.scrollTop = chat.scrollHeight;
    }, 400);
}
</script>
{% endblock %}
"""

CONTACT_HTML = """
{% extends "base.html" %}
{% block content %}
<div class="row justify-content-center"><div class="col-md-6"><div class="glass-card p-4"><h3 class="golden-text text-center">📩 Contact Us</h3><hr><form method="POST"><div class="mb-2"><input type="text" name="name" class="form-control" placeholder="Your Name" required></div><div class="mb-2"><input type="email" name="email" class="form-control" placeholder="Email" required></div><div class="mb-2"><input type="tel" name="phone" class="form-control" placeholder="Phone (optional)"></div><div class="mb-2"><input type="text" name="subject" class="form-control" placeholder="Subject" required></div><div class="mb-2"><textarea name="message" class="form-control" rows="4" placeholder="Message" required></textarea></div><button type="submit" class="btn btn-gold w-100">Send</button></form><div class="mt-3 text-center"><p><strong>WhatsApp:</strong> {{ support_whatsapp }}</p><p><strong>Email:</strong> {{ support_email }}</p></div></div></div></div>
{% endblock %}
"""

CONTACT_MESSAGES_HTML = """
{% extends "base.html" %}
{% block content %}
<h2 class="golden-text">📬 Contact Messages</h2>
{% if messages %}
<div class="table-responsive">
    <table class="table table-dark table-hover">
        <thead><tr><th>Name</th><th>Email</th><th>Subject</th><th>Message</th><th>Status</th><th>Action</th></tr></thead>
        <tbody>
        {% for msg in messages %}
        <tr>
            <td>{{ msg.name }}</td>
            <td>{{ msg.email }}</td>
            <td>{{ msg.subject }}</td>
            <td>{{ msg.message[:100] }}{% if msg.message|length > 100 %}...{% endif %}</td>
            <td><span class="badge bg-{{ 'success' if msg.is_read else 'warning' }}">{{ 'Read' if msg.is_read else 'Unread' }}</span></td>
            <td>
                {% if not msg.is_read %}
                <form method="POST" action="{{ url_for('mark_contact_read', mid=msg.id) }}">
                    <button type="submit" class="btn btn-sm btn-gold">Mark Read</button>
                </form>
                {% endif %}
            </td>
        </tr>
        {% endfor %}
        </tbody>
    </table>
</div>
{% else %}
<p class="text-muted-light">No messages yet.</p>
{% endif %}
<a href="{{ url_for('super_dashboard') }}" class="btn btn-outline-gold mt-3">← Back to Super Dashboard</a>
{% endblock %}
"""

PROFILE_HTML = """
{% extends "base.html" %}
{% block content %}
<div class="row justify-content-center"><div class="col-md-6"><div class="glass-card p-4"><h3 class="golden-text text-center">👤 My Profile</h3><form method="POST"><div class="mb-3"><label class="form-label">Username</label><input type="text" class="form-control" value="{{ admin.username }}" disabled></div><div class="mb-3"><label class="form-label">Email</label><input type="email" name="email" class="form-control" value="{{ admin.email }}"></div><div class="mb-3"><label class="form-label">Phone</label><input type="tel" name="phone" class="form-control" value="{{ admin.phone or '' }}"></div><div class="mb-3"><label class="form-label">Referral Code</label><input type="text" class="form-control" value="{{ admin.referral_code }}" disabled></div><hr><h5 class="golden-text">Change Password</h5><div class="mb-3"><label class="form-label">New Password</label><input type="password" name="new_password" class="form-control" placeholder="Leave blank to keep current"></div><button type="submit" class="btn btn-gold w-100">Update Profile</button></form></div></div></div>
{% endblock %}
"""

NOTIFICATIONS_HTML = """
{% extends "base.html" %}
{% block content %}
<h2 class="golden-text">🔔 Notifications</h2>
<ul class="list-group">
{% for n in notifications %}
<li class="list-group-item bg-dark text-light">{{ n.message }} <small class="text-muted-light">{{ n.created_at.strftime('%Y-%m-%d %H:%M') }}</small></li>
{% else %}
<li class="list-group-item bg-dark text-muted-light">No notifications</li>
{% endfor %}
</ul>
{% endblock %}
"""

WITHDRAWALS_HTML = """
{% extends "base.html" %}
{% block content %}
<h2 class="golden-text">💰 Withdrawals</h2>
<table class="table table-dark table-hover">
<thead><tr><th>Admin</th><th>Amount</th><th>Phone</th><th>Status</th><th>Date</th></tr></thead>
<tbody>
{% for w in withdrawals %}
<tr>
    <td>{{ w.admin_id }}</td>
    <td>KES {{ w.amount|round(2) }}</td>
    <td>{{ w.phone }}</td>
    <td><span class="badge bg-{{ 'success' if w.status=='paid' else 'warning' if w.status=='pending' else 'danger' }}">{{ w.status }}</span></td>
    <td>{{ w.created_at.strftime('%Y-%m-%d %H:%M') }}</td>
</tr>
{% endfor %}
</tbody>
</table>
{% endblock %}
"""

SETTINGS_HTML = """
{% extends "base.html" %}
{% block content %}
<h2 class="golden-text">⚙️ Settings</h2>
<div class="glass-card p-4">
<form method="POST">
    <div class="form-check mb-3">
        <input class="form-check-input" type="checkbox" name="maintenance_mode" id="maintenance" {% if maintenance_mode %}checked{% endif %}>
        <label class="form-check-label" for="maintenance">🔒 Enable Maintenance Mode</label>
    </div>
    <button type="submit" class="btn btn-gold">Save Settings</button>
</form>
</div>
<a href="{{ url_for('super_dashboard') }}" class="btn btn-outline-gold mt-3">← Back to Super Dashboard</a>
{% endblock %}
"""

MANAGE_ADMINS_HTML = """
{% extends "base.html" %}
{% block content %}
<h2 class="golden-text">👥 Manage Admins</h2>
<div class="glass-card p-4">
<table class="table table-dark table-hover">
<thead><tr><th>Username</th><th>Email</th><th>Role</th><th>Status</th><th>Action</th></tr></thead>
<tbody>
{% for a in admins %}
<tr>
    <td>{{ a.username }}</td>
    <td>{{ a.email }}</td>
    <td>{% if a.is_super_admin %}👑 Super{% else %}Admin{% endif %}</td>
    <td>{% if a.is_active %}<span class="badge bg-success">Active</span>{% else %}<span class="badge bg-danger">Disabled</span>{% endif %}</td>
    <td>
        {% if not a.is_super_admin %}
        <form method="POST" action="{{ url_for('toggle_admin', aid=a.id) }}" style="display:inline;">
            <button type="submit" class="btn btn-sm btn-{{ 'warning' if a.is_active else 'success' }}">{{ 'Disable' if a.is_active else 'Enable' }}</button>
        </form>
        <form method="POST" action="{{ url_for('delete_admin', aid=a.id) }}" style="display:inline;" onsubmit="return confirm('Delete this admin?');">
            <button type="submit" class="btn btn-sm btn-danger">Delete</button>
        </form>
        {% else %}
        <span class="text-muted-light">Protected</span>
        {% endif %}
    </td>
</tr>
{% endfor %}
</tbody>
</table>
</div>
<a href="{{ url_for('super_dashboard') }}" class="btn btn-outline-gold mt-3">← Back to Super Dashboard</a>
{% endblock %}
"""

# ---------- ROUTES ----------
@app.route('/')
def index():
    if is_admin_logged_in():
        admin = get_admin()
        if admin.is_super_admin:
            return redirect(url_for('super_dashboard'))
        return redirect(url_for('dashboard'))
    if is_contributor_logged_in():
        return redirect(url_for('contributor_dashboard'))
    return render_template_string(LANDING_HTML)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
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

@app.route('/dashboard')
def dashboard():
    if not is_admin_logged_in():
        return redirect(url_for('login'))
    admin = get_admin()
    if admin.is_super_admin:
        return redirect(url_for('super_dashboard'))
    page = request.args.get('page', 1, type=int)
    events = Event.query.filter_by(admin_id=admin.id).order_by(desc(Event.created_at)).paginate(page=page, per_page=10)
    total_raised = sum(get_event_total_contributions(e.id) for e in events.items)
    pending_count = Contributor.query.filter_by(status='pending').join(Event).filter(Event.admin_id == admin.id).count()
    return render_template_string(DASHBOARD_HTML, admin=admin, events=events, total_raised=total_raised,
                                  pending_contributions=pending_count)

@app.route('/super-dashboard')
def super_dashboard():
    if not is_admin_logged_in():
        return redirect(url_for('login'))
    admin = get_admin()
    if not admin.is_super_admin:
        flash('Access denied.', 'error')
        return redirect(url_for('dashboard'))
    total_events = Event.query.count()
    total_contributions = db.session.query(func.sum(Contributor.paid_amount)).filter_by(status='approved').scalar() or 0
    total_fees = db.session.query(func.sum(Contributor.fee_amount)).filter_by(status='approved').scalar() or 0
    pending_withdrawals = Withdrawal.query.filter_by(status='pending').count()
    locked_events = Event.query.filter(Event.disabled == True).count()
    pending_feature_requests = FeatureRequest.query.filter_by(status='pending').count()
    contact_messages_count = ContactMessage.query.filter_by(is_read=False).count()
    admins = Admin.query.all()
    can_withdraw = total_fees >= MINIMUM_WITHDRAWAL_FEE
    return render_template_string(SUPER_DASHBOARD_HTML, admin=admin, total_events=total_events,
                                  total_contributions=total_contributions, total_fees=total_fees,
                                  pending_withdrawals=pending_withdrawals, locked_events=locked_events,
                                  admins=admins, pending_feature_requests=pending_feature_requests,
                                  contact_messages_count=contact_messages_count, can_withdraw=can_withdraw)

@app.route('/events/create', methods=['GET', 'POST'])
def create_event():
    if not is_admin_logged_in():
        return redirect(url_for('login'))
    admin = get_admin()
    if admin.is_super_admin:
        flash('Super admins cannot create events. Use a normal admin account.', 'error')
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        token = generate_unique_token()
        while Event.query.filter_by(token=token).first():
            token = generate_unique_token()
        event = Event(
            token=token, admin_id=admin.id,
            event_type=request.form.get('event_type'),
            title=request.form.get('title'),
            description=request.form.get('description'),
            target_amount=float(request.form.get('target_amount', 0)),
            deadline=datetime.strptime(request.form.get('deadline'), '%Y-%m-%dT%H:%M'),
            event_date=datetime.strptime(request.form.get('event_date'), '%Y-%m-%dT%H:%M'),
            picture_url=request.form.get('picture_url'),
            background_image_url=request.form.get('background_image_url'),
            account_name=request.form.get('account_name'),
            paybill=request.form.get('paybill'),
            mpesa_number=request.form.get('mpesa_number'),
            till_number=request.form.get('till_number'),
            bank_name=request.form.get('bank_name'),
            bank_account_name=request.form.get('bank_account_name'),
            bank_account_number=request.form.get('bank_account_number'),
            payment_instructions=request.form.get('payment_instructions'),
            whatsapp_contact=request.form.get('whatsapp_contact'),
            grace_period=int(request.form.get('grace_period', 0)),
            has_grace_period=bool(request.form.get('has_grace_period', False))
        )
        db.session.add(event)
        db.session.commit()
        flash('Event created!', 'success')
        return redirect(url_for('dashboard'))
    return render_template_string(CREATE_EVENT_HTML)

@app.route('/events/<token>')
def event_landing(token):
    event = Event.query.filter_by(token=token).first_or_404()
    if not event.is_active:
        flash('Event inactive.', 'error')
        return redirect(url_for('dashboard'))
    if get_page_lock_status(event):
        return render_template_string("<h1>Event Locked</h1><p>Contact admin.</p>")
    contributor = None
    if is_contributor_logged_in():
        contributor = get_contributor()
    contributions = Contributor.query.filter_by(event_id=event.id, status='approved').order_by(desc(Contributor.created_at)).all()
    total_raised = get_event_total_contributions(event.id)
    chat_messages = ChatMessage.query.filter_by(event_id=event.id).order_by(ChatMessage.timestamp).limit(50).all()
    testimonials = Testimonial.query.filter_by(event_id=event.id).order_by(desc(Testimonial.created_at)).limit(10).all()
    days = (datetime.utcnow() - event.created_at).days + 1
    daily_note = get_daily_note(event.event_type, days)
    return render_template_string(EVENT_LANDING_HTML, event=event, total_raised=total_raised,
                                  chat_messages=chat_messages, testimonials=testimonials, daily_note=daily_note,
                                  contributor=contributor)

@app.route('/events/<token>/edit', methods=['GET', 'POST'])
def edit_event(token):
    if not is_admin_logged_in():
        return redirect(url_for('login'))
    event = Event.query.filter_by(token=token).first_or_404()
    admin = get_admin()
    if event.admin_id != admin.id and not admin.is_super_admin:
        flash('Unauthorized.', 'error')
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        event.title = request.form.get('title')
        event.description = request.form.get('description')
        event.target_amount = float(request.form.get('target_amount', 0))
        event.deadline = datetime.strptime(request.form.get('deadline'), '%Y-%m-%dT%H:%M')
        event.event_date = datetime.strptime(request.form.get('event_date'), '%Y-%m-%dT%H:%M')
        event.picture_url = request.form.get('picture_url')
        event.background_image_url = request.form.get('background_image_url')
        event.account_name = request.form.get('account_name')
        event.paybill = request.form.get('paybill')
        event.mpesa_number = request.form.get('mpesa_number')
        event.till_number = request.form.get('till_number')
        event.bank_name = request.form.get('bank_name')
        event.bank_account_name = request.form.get('bank_account_name')
        event.bank_account_number = request.form.get('bank_account_number')
        event.payment_instructions = request.form.get('payment_instructions')
        event.whatsapp_contact = request.form.get('whatsapp_contact')
        event.grace_period = int(request.form.get('grace_period', 0))
        event.has_grace_period = bool(request.form.get('has_grace_period', False))
        db.session.commit()
        flash('Event updated.', 'success')
        return redirect(url_for('dashboard'))
    return render_template_string(CREATE_EVENT_HTML)

@app.route('/events/<token>/delete', methods=['POST'])
def delete_event(token):
    if not is_admin_logged_in():
        return redirect(url_for('login'))
    event = Event.query.filter_by(token=token).first_or_404()
    admin = get_admin()
    if event.admin_id != admin.id and not admin.is_super_admin:
        flash('Unauthorized.', 'error')
        return redirect(url_for('dashboard'))
    Contributor.query.filter_by(event_id=event.id).delete()
    ChatMessage.query.filter_by(event_id=event.id).delete()
    Testimonial.query.filter_by(event_id=event.id).delete()
    Conversation.query.filter_by(event_id=event.id).delete()
    db.session.delete(event)
    db.session.commit()
    flash('Event deleted.', 'success')
    return redirect(url_for('dashboard'))

@app.route('/events/<token>/toggle-active', methods=['POST'])
def toggle_event_active(token):
    if not is_admin_logged_in():
        return redirect(url_for('login'))
    event = Event.query.filter_by(token=token).first_or_404()
    admin = get_admin()
    if event.admin_id != admin.id and not admin.is_super_admin:
        flash('Unauthorized.', 'error')
        return redirect(url_for('dashboard'))
    event.is_active = not event.is_active
    db.session.commit()
    flash('Event toggled.', 'success')
    return redirect(url_for('dashboard'))

@app.route('/events/<token>/lock-page', methods=['POST'])
def lock_event_page(token):
    if not is_admin_logged_in():
        return redirect(url_for('login'))
    event = Event.query.filter_by(token=token).first_or_404()
    admin = get_admin()
    if event.admin_id != admin.id and not admin.is_super_admin:
        flash('Unauthorized.', 'error')
        return redirect(url_for('dashboard'))
    event.disabled = not event.disabled
    if event.disabled:
        event.disabled_reason = request.form.get('reason', 'Page locked by admin.')
    else:
        event.disabled_reason = None
    db.session.commit()
    flash('Lock status updated.', 'success')
    return redirect(url_for('dashboard'))

@app.route('/events/<token>/contributors')
def manage_contributors(token):
    if not is_admin_logged_in():
        return redirect(url_for('login'))
    event = Event.query.filter_by(token=token).first_or_404()
    admin = get_admin()
    if event.admin_id != admin.id and not admin.is_super_admin:
        flash('Unauthorized.', 'error')
        return redirect(url_for('dashboard'))
    page = request.args.get('page', 1, type=int)
    contributors = Contributor.query.filter_by(event_id=event.id).order_by(desc(Contributor.created_at)).paginate(page=page, per_page=15)
    return render_template_string(CONTRIBUTORS_HTML, event=event, contributors=contributors)

@app.route('/events/<token>/contributor/add', methods=['POST'])
def add_contributor(token):
    if not is_admin_logged_in():
        return redirect(url_for('login'))
    event = Event.query.filter_by(token=token).first_or_404()
    admin = get_admin()
    if event.admin_id != admin.id and not admin.is_super_admin:
        flash('Unauthorized.', 'error')
        return redirect(url_for('dashboard'))
    name = request.form.get('name', '').strip()
    phone = request.form.get('phone', '').strip()
    pledge = float(request.form.get('pledge_amount', 0))
    if not name or not phone or pledge <= 0:
        flash('All fields required.', 'error')
        return redirect(url_for('manage_contributors', token=token))
    ct = generate_unique_token()
    while Contributor.query.filter_by(token=ct).first():
        ct = generate_unique_token()
    contrib = Contributor(
        event_id=event.id, token=ct, pin=generate_pin(),
        name=name, phone=phone, pledge_amount=pledge,
        status='pending'
    )
    db.session.add(contrib)
    db.session.commit()
    if not event.first_contribution_date:
        event.first_contribution_date = datetime.utcnow()
        db.session.commit()
    flash('Contributor added.', 'success')
    return redirect(url_for('manage_contributors', token=event.token))

@app.route('/contributor/<token>')
def contributor_view(token):
    contrib = Contributor.query.filter_by(token=token).first_or_404()
    event = Event.query.get(contrib.event_id)
    payments = Payment.query.filter_by(contributor_id=contrib.id).all()
    show_payments = False
    if contrib.completed_at and (datetime.utcnow() - contrib.completed_at).days >= 7:
        show_payments = True
    conv = Conversation.query.filter_by(event_id=event.id, admin_id=event.admin_id, contributor_id=contrib.id).first()
    if not conv:
        conv = Conversation(event_id=event.id, admin_id=event.admin_id, contributor_id=contrib.id)
        db.session.add(conv)
        db.session.commit()
    is_admin_user = is_admin_logged_in()
    is_contributor_owner = is_contributor_logged_in() and get_contributor().id == contrib.id
    return render_template_string(CONTRIBUTOR_VIEW_HTML, contrib=contrib, event=event, payments=payments,
                                  show_payments=show_payments, is_admin_user=is_admin_user,
                                  is_contributor_owner=is_contributor_owner, now=datetime.utcnow())

@app.route('/contributor/<token>/approve', methods=['POST'])
def approve_contributor(token):
    if not is_admin_logged_in():
        return redirect(url_for('login'))
    admin = get_admin()
    if admin.is_super_admin:
        flash('Super admins cannot approve contributions.', 'error')
        return redirect(url_for('super_dashboard'))
    contrib = Contributor.query.filter_by(token=token).first_or_404()
    event = Event.query.get(contrib.event_id)
    if event.admin_id != admin.id:
        flash('Not your event.', 'error')
        return redirect(url_for('dashboard'))
    if contrib.status == 'pending':
        received = float(request.form.get('received_amount', contrib.pledge_amount))
        if received > 0:
            fee = calculate_fee(received, event.admin_id)
            net = received - fee
            contrib.paid_amount = received
            contrib.fee_amount = fee
            contrib.net_contribution = net
            contrib.status = 'approved'
            contrib.completed_at = datetime.utcnow()
            payment = Payment(contributor_id=contrib.id, amount=received, note=f'Approved. Fee: KES {fee}')
            db.session.add(payment)
            db.session.commit()
            flash(f'Approved! Fee: KES {fee}', 'success')
        else:
            flash('Amount must be > 0.', 'error')
    else:
        flash('Already processed.', 'info')
    return redirect(url_for('manage_contributors', token=event.token))

@app.route('/contributor/<token>/decline', methods=['POST'])
def decline_contributor(token):
    if not is_admin_logged_in():
        return redirect(url_for('login'))
    admin = get_admin()
    if admin.is_super_admin:
        flash('Super admins cannot decline contributions.', 'error')
        return redirect(url_for('super_dashboard'))
    contrib = Contributor.query.filter_by(token=token).first_or_404()
    event = Event.query.get(contrib.event_id)
    if event.admin_id != admin.id:
        flash('Not your event.', 'error')
        return redirect(url_for('dashboard'))
    if contrib.status == 'pending':
        reason = request.form.get('reason', 'No reason provided.')
        contrib.status = 'declined'
        contrib.decline_reason = reason
        db.session.commit()
        flash('Contribution declined.', 'warning')
    else:
        flash('Already processed.', 'info')
    return redirect(url_for('manage_contributors', token=event.token))

@app.route('/contributor/<token>/payment-proof', methods=['POST'])
def submit_payment_proof(token):
    contrib = Contributor.query.filter_by(token=token).first_or_404()
    event = Event.query.get(contrib.event_id)
    sender_name = request.form.get('sender_name', '').strip()
    text = request.form.get('payment_proof_text', '').strip()
    file = request.files.get('screenshot')
    file_path = None
    if file and file.filename:
        ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else 'jpg'
        filename = f"proof_{contrib.token}_{int(datetime.utcnow().timestamp())}.{ext}"
        file_path = os.path.join('static/uploads/proofs', filename)
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        file.save(file_path)
        file_path = file_path.replace('\\', '/')
    contrib.payment_proof_screenshot = file_path
    contrib.payment_proof_text = text
    contrib.sender_name = sender_name
    auto_verified = False
    if event.account_name and sender_name:
        if sender_name.lower().strip() == event.account_name.lower().strip():
            auto_verified = True
    contrib.auto_verified = auto_verified
    db.session.commit()
    admin = Admin.query.get(event.admin_id)
    create_notification(admin.id, f'Payment proof from {contrib.name}. Verified: {auto_verified}', 'info', event.id, contrib.id)
    flash('Proof submitted.', 'info')
    return redirect(url_for('contributor_view', token=contrib.token))

@app.route('/contributor/<token>/receipt')
def contributor_receipt(token):
    contrib = Contributor.query.filter_by(token=token).first_or_404()
    if contrib.status != 'approved' or not contrib.completed_at:
        flash('Only approved contributions have receipts.', 'error')
        return redirect(url_for('contributor_view', token=token))
    is_admin_user = is_admin_logged_in()
    is_contributor_owner = is_contributor_logged_in() and get_contributor().id == contrib.id
    if not is_admin_user:
        if (datetime.utcnow() - contrib.completed_at).days < 7:
            flash('Receipt available after 7 days.', 'error')
            return redirect(url_for('contributor_view', token=token))
    buffer = io.BytesIO()
    p = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    p.setFont("Helvetica-Bold", 16)
    p.drawString(50, height - 50, "CONTRIBUTION RECEIPT")
    p.setFont("Helvetica", 12)
    p.drawString(50, height - 80, f"Name: {contrib.name}")
    p.drawString(50, height - 100, f"Phone: {contrib.phone}")
    p.drawString(50, height - 120, f"Amount Paid: KES {contrib.paid_amount:,.2f}")
    p.drawString(50, height - 140, f"Fee: KES {contrib.fee_amount:,.2f}")
    p.drawString(50, height - 160, f"Net: KES {contrib.net_contribution:,.2f}")
    p.drawString(50, height - 180, f"Event: {contrib.event.title}")
    p.drawString(50, height - 200, f"Date: {contrib.completed_at.strftime('%Y-%m-%d %H:%M')}")
    p.drawString(50, height - 220, f"Receipt #: {contrib.token}")
    p.save()
    buffer.seek(0)
    return send_file(buffer, as_attachment=True, download_name=f"receipt_{contrib.token}.pdf", mimetype='application/pdf')

@app.route('/contributor/register', methods=['GET', 'POST'])
def contributor_register():
    event_token = request.args.get('event_token', '')
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        name = request.form.get('name', '').strip()
        phone = request.form.get('phone', '').strip()
        event_token_post = request.form.get('event_token', '').strip()
        if not username or not password or not name:
            flash('All fields required.', 'error')
            return redirect(url_for('contributor_register', event_token=event_token_post))
        if Contributor.query.filter_by(username=username).first():
            flash('Username taken.', 'error')
            return redirect(url_for('contributor_register', event_token=event_token_post))
        token = generate_unique_token()
        while Contributor.query.filter_by(token=token).first():
            token = generate_unique_token()
        contrib = Contributor(
            username=username,
            password_hash=hash_password(password),
            name=name,
            phone=phone,
            token=token,
            status='pending'
        )
        db.session.add(contrib)
        db.session.commit()
        session['contributor_id'] = contrib.id
        flash('Registration successful!', 'success')
        if event_token_post:
            return redirect(url_for('event_landing', token=event_token_post))
        return redirect(url_for('index'))
    return render_template_string("""
    {% extends "base.html" %}
    {% block content %}
    <div class="row justify-content-center"><div class="col-md-5"><div class="glass-card p-4"><h3 class="golden-text text-center">📝 Contributor Register</h3><form method="POST"><div class="mb-2"><input type="text" name="username" class="form-control" placeholder="Username" required></div><div class="mb-2"><input type="password" name="password" class="form-control" placeholder="Password" required></div><div class="mb-2"><input type="text" name="name" class="form-control" placeholder="Full Name" required></div><div class="mb-2"><input type="tel" name="phone" class="form-control" placeholder="Phone" required></div><input type="hidden" name="event_token" value="{{ request.args.get('event_token', '') }}">
    <button type="submit" class="btn btn-gold w-100">Register</button></form><div class="mt-3 text-center"><small><a href="{{ url_for('contributor_login', event_token=request.args.get('event_token', '')) }}">Already have an account?</a></small></div></div></div></div>
    {% endblock %}
    """)

@app.route('/contributor/login', methods=['GET', 'POST'])
def contributor_login():
    event_token = request.args.get('event_token', '')
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        remember = request.form.get('remember') == 'on'
        event_token_post = request.form.get('event_token', '').strip()
        contrib = Contributor.query.filter_by(username=username, is_active=True).first()
        if contrib and check_password(password, contrib.password_hash):
            session['contributor_id'] = contrib.id
            contrib.last_login = datetime.utcnow()
            db.session.commit()
            if remember:
                session.permanent = True
            flash('Logged in.', 'success')
            if event_token_post:
                return redirect(url_for('event_landing', token=event_token_post))
            return redirect(url_for('index'))
        flash('Invalid credentials.', 'error')
    return render_template_string("""
    {% extends "base.html" %}
    {% block content %}
    <div class="row justify-content-center"><div class="col-md-5"><div class="glass-card p-4"><h3 class="golden-text text-center">🔑 Contributor Login</h3><form method="POST"><div class="mb-3"><input type="text" name="username" class="form-control" placeholder="Username" required></div><div class="mb-3"><input type="password" name="password" class="form-control" placeholder="Password" required></div><div class="mb-3 form-check"><input type="checkbox" name="remember" id="remember" class="form-check-input"><label class="form-check-label" for="remember">Remember me</label></div><input type="hidden" name="event_token" value="{{ request.args.get('event_token', '') }}">
    <button type="submit" class="btn btn-gold w-100">Login</button></form><div class="mt-3 text-center"><small><a href="{{ url_for('contributor_register', event_token=request.args.get('event_token', '')) }}">Create an account</a></small></div></div></div></div>
    {% endblock %}
    """)

@app.route('/contributor/logout')
def contributor_logout():
    session.pop('contributor_id', None)
    flash('Logged out.', 'info')
    return redirect(url_for('contributor_login'))

@app.route('/contributor/dashboard')
def contributor_dashboard():
    if not is_contributor_logged_in():
        flash('Please log in.', 'error')
        return redirect(url_for('contributor_login'))
    contrib = get_contributor()
    contributions = Contributor.query.filter_by(name=contrib.name, phone=contrib.phone).all()
    return render_template_string("""
    <h2 class="golden-text">Contributor Dashboard</h2>
    <p>Name: {{ contrib.name }}</p>
    <ul>{% for c in contributions %}<li>{{ c.event.title }} - {{ c.status }}</li>{% endfor %}</ul>
    """, contrib=contrib, contributions=contributions)

@app.route('/contact', methods=['GET', 'POST'])
def contact():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip()
        phone = request.form.get('phone', '').strip()
        subject = request.form.get('subject', '').strip()
        message = request.form.get('message', '').strip()
        if not name or not email or not subject or not message:
            flash('All fields except phone are required.', 'error')
            return redirect(url_for('contact'))
        msg = ContactMessage(name=name, email=email, phone=phone, subject=subject, message=message)
        db.session.add(msg)
        db.session.commit()
        send_email(SUPPORT_EMAIL, f"[GoldenVow] {subject}", f"From: {name} <{email}>\nPhone: {phone}\n\n{message}")
        flash('✅ Your message has been sent.', 'success')
        return redirect(url_for('contact'))
    return render_template_string(CONTACT_HTML)

@app.route('/contact-messages')
def contact_messages():
    if not is_admin_logged_in() or not get_admin().is_super_admin:
        flash('Unauthorized.', 'error')
        return redirect(url_for('login'))
    messages = ContactMessage.query.order_by(desc(ContactMessage.created_at)).all()
    return render_template_string(CONTACT_MESSAGES_HTML, messages=messages)

@app.route('/contact-message/<int:mid>/read', methods=['POST'])
def mark_contact_read(mid):
    if not is_admin_logged_in() or not get_admin().is_super_admin:
        flash('Unauthorized.', 'error')
        return redirect(url_for('login'))
    msg = ContactMessage.query.get_or_404(mid)
    msg.is_read = True
    db.session.commit()
    flash('Marked as read.', 'success')
    return redirect(url_for('contact_messages'))

@app.route('/profile', methods=['GET', 'POST'])
def profile():
    if not is_admin_logged_in():
        return redirect(url_for('login'))
    admin = get_admin()
    if request.method == 'POST':
        admin.email = request.form.get('email', admin.email)
        admin.phone = request.form.get('phone', admin.phone)
        new_pass = request.form.get('new_password')
        if new_pass:
            admin.password_hash = hash_password(new_pass)
        db.session.commit()
        flash('Profile updated.', 'success')
        return redirect(url_for('profile'))
    return render_template_string(PROFILE_HTML, admin=admin)

@app.route('/notifications')
def notifications():
    if not is_admin_logged_in():
        return redirect(url_for('login'))
    notifs = Notification.query.filter_by(admin_id=get_admin().id).order_by(desc(Notification.created_at)).limit(100).all()
    return render_template_string(NOTIFICATIONS_HTML, notifications=notifs)

@app.route('/withdrawals')
def withdrawals():
    if not is_admin_logged_in() or not get_admin().is_super_admin:
        flash('Unauthorized.', 'error')
        return redirect(url_for('login'))
    wd_list = Withdrawal.query.order_by(desc(Withdrawal.created_at)).all()
    return render_template_string(WITHDRAWALS_HTML, withdrawals=wd_list)

@app.route('/withdrawal/request', methods=['POST'])
def request_withdrawal():
    if not is_admin_logged_in() or not get_admin().is_super_admin:
        flash('Unauthorized.', 'error')
        return redirect(url_for('login'))
    amount = float(request.form.get('amount', 0))
    phone = request.form.get('phone', '').strip()
    if amount < MINIMUM_WITHDRAWAL_FEE:
        flash(f'Minimum withdrawal is KES {MINIMUM_WITHDRAWAL_FEE}.', 'error')
        return redirect(url_for('super_dashboard'))
    total_fees = get_global_total_fees()
    if amount > total_fees:
        flash('Insufficient fees.', 'error')
        return redirect(url_for('super_dashboard'))
    wd = Withdrawal(admin_id=get_admin().id, amount=amount, phone=phone, method='mpesa', status='pending')
    db.session.add(wd)
    db.session.commit()
    flash('Withdrawal request submitted.', 'success')
    return redirect(url_for('super_dashboard'))

@app.route('/withdrawal/<int:wid>/update', methods=['POST'])
def update_withdrawal(wid):
    if not is_admin_logged_in() or not get_admin().is_super_admin:
        flash('Unauthorized.', 'error')
        return redirect(url_for('login'))
    wd = Withdrawal.query.get_or_404(wid)
    status = request.form.get('status')
    if status in ['paid', 'failed', 'cancelled']:
        wd.status = status
        if status == 'paid':
            wd.paid_at = datetime.utcnow()
        db.session.commit()
        flash('Updated.', 'success')
    else:
        flash('Invalid status.', 'error')
    return redirect(url_for('withdrawals'))

@app.route('/help')
def help_page():
    return render_template_string(HELP_HTML)

@app.route('/create_super_admin')
def create_super_admin():
    if Admin.query.count() > 0:
        return "Admin already exists. <a href='/login'>Login</a>"
    username = "super"
    password = "super123"
    admin = Admin(
        username=username,
        password_hash=hash_password(password),
        email="super@goldenvow.com",
        phone="0000000000",
        is_super_admin=True,
        referral_code=generate_referral_code()
    )
    db.session.add(admin)
    db.session.commit()
    return f"""
    ✅ Super Admin created!<br>
    Username: <b>{username}</b><br>
    Password: <b>{password}</b><br>
    <a href='/login'>Login now</a><br>
    <small>Note: Delete this route after first use.</small>
    """

@app.route('/manage-admins')
def manage_admins():
    if not is_admin_logged_in() or not get_admin().is_super_admin:
        flash('Unauthorized.', 'error')
        return redirect(url_for('login'))
    admins = Admin.query.all()
    return render_template_string(MANAGE_ADMINS_HTML, admins=admins)

@app.route('/admin/<int:aid>/toggle', methods=['POST'])
def toggle_admin(aid):
    if not is_admin_logged_in() or not get_admin().is_super_admin:
        flash('Unauthorized.', 'error')
        return redirect(url_for('login'))
    admin = Admin.query.get_or_404(aid)
    if admin.is_super_admin:
        flash('Cannot disable super admin.', 'error')
        return redirect(url_for('manage_admins'))
    admin.is_active = not admin.is_active
    db.session.commit()
    flash('Admin toggled.', 'success')
    return redirect(url_for('manage_admins'))

@app.route('/admin/<int:aid>/delete', methods=['POST'])
def delete_admin(aid):
    if not is_admin_logged_in() or not get_admin().is_super_admin:
        flash('Unauthorized.', 'error')
        return redirect(url_for('login'))
    admin = Admin.query.get_or_404(aid)
    if admin.is_super_admin:
        flash('Cannot delete super admin.', 'error')
        return redirect(url_for('manage_admins'))
    db.session.delete(admin)
    db.session.commit()
    flash('Admin deleted.', 'success')
    return redirect(url_for('manage_admins'))

@app.route('/events/<token>/pay-fee', methods=['POST'])
def pay_event_fee(token):
    if not is_admin_logged_in() or not get_admin().is_super_admin:
        flash('Unauthorized.', 'error')
        return redirect(url_for('login'))
    event = Event.query.filter_by(token=token).first_or_404()
    event.fee_paid = True
    event.fee_paid_date = datetime.utcnow()
    db.session.commit()
    flash('Fee marked as paid.', 'success')
    return redirect(url_for('super_dashboard'))

@app.route('/events/<token>/request-unlock', methods=['POST'])
def request_unlock(token):
    if not is_admin_logged_in():
        return redirect(url_for('login'))
    event = Event.query.filter_by(token=token).first_or_404()
    admin = get_admin()
    if event.admin_id != admin.id:
        flash('Unauthorized.', 'error')
        return redirect(url_for('dashboard'))
    super_admins = Admin.query.filter_by(is_super_admin=True).all()
    for sa in super_admins:
        create_notification(sa.id, f'Fee unlock requested for {event.title}', 'fee_request', event.id)
    flash('Request sent to Super Admin.', 'success')
    return redirect(url_for('manage_contributors', token=event.token))

@app.route('/add_testimonial/<token>', methods=['POST'])
def add_testimonial(token):
    event = Event.query.filter_by(token=token).first_or_404()
    name = request.form.get('name', '').strip()
    rating = int(request.form.get('rating', 0))
    message = request.form.get('message', '').strip()
    if not name or not message or rating < 1:
        flash('All fields required.', 'error')
        return redirect(url_for('event_landing', token=token))
    contrib = Contributor.query.filter_by(event_id=event.id, name=name).first()
    testimonial = Testimonial(event_id=event.id, contributor_id=contrib.id if contrib else None, rating=rating, message=message)
    db.session.add(testimonial)
    db.session.commit()
    flash('Thank you!', 'success')
    return redirect(url_for('event_landing', token=token))

@app.route('/feature-request', methods=['GET', 'POST'])
@app.route('/feature-request/<event_token>', methods=['GET', 'POST'])
def submit_feature_request(event_token=None):
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip()
        title = request.form.get('title', '').strip()
        description = request.form.get('description', '').strip()
        event_token_post = request.form.get('event_token')
        if not name or not title or not description:
            flash('Name, title, and description required.', 'error')
            return redirect(url_for('index'))
        req = FeatureRequest(
            contributor_name=name,
            contributor_email=email,
            title=title,
            description=description,
            event_id=Event.query.filter_by(token=event_token_post).first().id if event_token_post else None
        )
        db.session.add(req)
        db.session.commit()
        super_admins = Admin.query.filter_by(is_super_admin=True).all()
        for sa in super_admins:
            create_notification(sa.id, f'New feature request from {name}', 'feature_request')
        flash('✅ Feature request submitted.', 'success')
        if event_token_post:
            return redirect(url_for('event_landing', token=event_token_post))
        return redirect(url_for('index'))
    return render_template_string("""
    {% extends "base.html" %}
    {% block content %}
    <div class="row justify-content-center"><div class="col-md-6"><div class="glass-card p-4"><h3 class="golden-text text-center">💡 Suggest a Feature</h3><form method="POST"><div class="mb-2"><input type="text" name="name" class="form-control" placeholder="Your Name" required></div><div class="mb-2"><input type="email" name="email" class="form-control" placeholder="Email (optional)"></div><div class="mb-2"><input type="text" name="title" class="form-control" placeholder="Feature Title" required></div><div class="mb-2"><textarea name="description" class="form-control" rows="4" placeholder="Describe your idea..." required></textarea></div><input type="hidden" name="event_token" value="{{ request.args.get('event_token', '') }}">
    <button type="submit" class="btn btn-gold w-100">Submit</button></form></div></div></div>
    {% endblock %}
    """)

@app.route('/manage-feature-requests')
def manage_feature_requests():
    if not is_admin_logged_in() or not get_admin().is_super_admin:
        flash('Unauthorized.', 'error')
        return redirect(url_for('login'))
    requests = FeatureRequest.query.order_by(desc(FeatureRequest.created_at)).all()
    return render_template_string("""
    <h2>Feature Requests</h2><ul>{% for r in requests %}<li>{{ r.title }} – {{ r.status }}<br>{{ r.description }}</li>{% endfor %}</ul>
    """, requests=requests)

@app.route('/feature-request/<int:req_id>/update', methods=['POST'])
def update_feature_request(req_id):
    if not is_admin_logged_in() or not get_admin().is_super_admin:
        flash('Unauthorized.', 'error')
        return redirect(url_for('login'))
    req = FeatureRequest.query.get_or_404(req_id)
    req.status = request.form.get('status')
    req.admin_response = request.form.get('response', '')
    db.session.commit()
    flash('Updated.', 'success')
    return redirect(url_for('manage_feature_requests'))

@app.route('/settings', methods=['GET', 'POST'])
def settings():
    if not is_admin_logged_in() or not get_admin().is_super_admin:
        flash('Unauthorized.', 'error')
        return redirect(url_for('login'))
    setting = Setting.query.filter_by(key='maintenance_mode').first()
    if request.method == 'POST':
        mode = request.form.get('maintenance_mode') == 'on'
        setting.value = 'True' if mode else 'False'
        db.session.commit()
        flash('Settings updated.', 'success')
        return redirect(url_for('settings'))
    maintenance_mode = (setting.value == 'True') if setting else False
    return render_template_string(SETTINGS_HTML, maintenance_mode=maintenance_mode)

@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    return "<h1>Forgot password – under construction</h1>"

@app.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    return "<h1>Reset password – under construction</h1>"

# ---------- SCHEDULER ----------
def check_pending_contributions():
    with app.app_context():
        pending = Contributor.query.filter_by(status='pending').all()
        for c in pending:
            event = Event.query.get(c.event_id)
            if event:
                admin = Admin.query.get(event.admin_id)
                if admin:
                    create_notification(admin.id, f'Pending contribution from {c.name}', 'reminder', event.id, c.id)

scheduler = BackgroundScheduler()
scheduler.add_job(check_pending_contributions, 'interval', hours=3)
scheduler.start()

# ---------- MAIN ----------
if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
