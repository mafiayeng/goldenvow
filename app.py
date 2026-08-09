import os
import uuid
import random
import string
import io
import secrets
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from functools import wraps

from flask import (
    Flask, render_template, request, redirect, url_for, session,
    flash, jsonify, send_file, abort
)
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import desc, func, inspect, Index
from flask_wtf import FlaskForm, CSRFProtect
from flask_wtf.csrf import CSRFError
from wtforms import StringField, PasswordField, FloatField, DateTimeField, TextAreaField, BooleanField, SelectField
from wtforms.validators import DataRequired, Email, Length, NumberRange, ValidationError, Optional
from flask_wtf.file import FileField, FileAllowed
import bcrypt
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from apscheduler.schedulers.background import BackgroundScheduler

from forms import *

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.template_folder = 'template'
app.secret_key = os.environ.get('SECRET_KEY')
if not app.secret_key:
    raise RuntimeError("SECRET_KEY environment variable is not set")
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get(
    'DATABASE_URL', 'sqlite:///database.db'
)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.permanent_session_lifetime = timedelta(days=7)

csrf = CSRFProtect(app)
db = SQLAlchemy(app)

SERVICE_FEE_PERCENTAGE = float(os.environ.get('SERVICE_FEE_PERCENTAGE', 2.0))
SUPPORT_WHATSAPP = os.environ.get('SUPPORT_WHATSAPP', '254737349468')
SUPPORT_EMAIL = os.environ.get('SUPPORT_EMAIL', 'goldenvowsupport@gmail.com')
SUPER_ADMIN_SECRET = os.environ.get('SUPER_ADMIN_SECRET')
MINIMUM_WITHDRAWAL_FEE = float(os.environ.get('MINIMUM_WITHDRAWAL_FEE', 50.0))
MAX_UPLOAD_SIZE = 5 * 1024 * 1024
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

EMAIL_HOST = os.environ.get('EMAIL_HOST', 'smtp.gmail.com')
EMAIL_PORT = int(os.environ.get('EMAIL_PORT', 587))
EMAIL_USER = os.environ.get('EMAIL_USER', 'goldenvowsupport@gmail.com')
EMAIL_PASS = os.environ.get('EMAIL_PASS')

STATUS_PENDING = 'pending'
STATUS_APPROVED = 'approved'
STATUS_DECLINED = 'declined'
STATUS_PAID = 'paid'
STATUS_FAILED = 'failed'
STATUS_CANCELLED = 'cancelled'

# ---------- Models ----------
class Admin(db.Model):
    __tablename__ = 'admin'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    email = db.Column(db.String(100), unique=True)
    phone = db.Column(db.String(20))
    is_super_admin = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    referral_code = db.Column(db.String(20), unique=True, nullable=False, default='')
    referred_by = db.Column(db.String(20), db.ForeignKey('admin.referral_code'), nullable=True)
    referral_count = db.Column(db.Integer, default=0)
    bonus_earned = db.Column(db.Float, default=0.0)
    last_login = db.Column(db.DateTime, nullable=True)
    __table_args__ = (Index('idx_admin_username', 'username'), Index('idx_admin_email', 'email'),)

class Event(db.Model):
    __tablename__ = 'event'
    id = db.Column(db.Integer, primary_key=True)
    token = db.Column(db.String(100), unique=True, nullable=False)
    admin_id = db.Column(db.Integer, db.ForeignKey('admin.id', ondelete='CASCADE'))
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
    last_activity = db.Column(db.DateTime, default=datetime.utcnow)
    dormant_notified = db.Column(db.Boolean, default=False)
    dormant_notified_at = db.Column(db.DateTime, nullable=True)
    lock_message = db.Column(db.Text, nullable=True)
    __table_args__ = (
        Index('idx_event_admin_id', 'admin_id'),
        Index('idx_event_token', 'token'),
        Index('idx_event_is_active', 'is_active'),
        Index('idx_event_last_activity', 'last_activity'),
    )

class Contributor(db.Model):
    __tablename__ = 'contributor'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=True)
    password_hash = db.Column(db.String(200), nullable=True)
    last_login = db.Column(db.DateTime, nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    event_id = db.Column(db.Integer, db.ForeignKey('event.id', ondelete='CASCADE'), nullable=True)
    token = db.Column(db.String(100), unique=True, nullable=False)
    pin = db.Column(db.String(4), nullable=False, default='0000')
    name = db.Column(db.String(150), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    pledge_amount = db.Column(db.Float, nullable=False)
    fee_amount = db.Column(db.Float, default=0.0)
    net_contribution = db.Column(db.Float, default=0.0)
    paid_amount = db.Column(db.Float, default=0.0)
    status = db.Column(db.String(20), default=STATUS_PENDING)
    decline_reason = db.Column(db.Text, nullable=True)
    sender_name = db.Column(db.String(150), nullable=True)
    auto_verified = db.Column(db.Boolean, default=False)
    payment_proof_screenshot = db.Column(db.String(500))
    payment_proof_text = db.Column(db.Text)
    completed_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    __table_args__ = (
        Index('idx_contributor_event_id', 'event_id'),
        Index('idx_contributor_status', 'status'),
        Index('idx_contributor_phone', 'phone'),
        Index('idx_contributor_token', 'token'),
    )

class Payment(db.Model):
    __tablename__ = 'payment'
    id = db.Column(db.Integer, primary_key=True)
    contributor_id = db.Column(db.Integer, db.ForeignKey('contributor.id', ondelete='CASCADE'))
    amount = db.Column(db.Float, nullable=False)
    date_paid = db.Column(db.DateTime, default=datetime.utcnow)
    note = db.Column(db.String(200))
    __table_args__ = (Index('idx_payment_contributor_id', 'contributor_id'),)

class ChatMessage(db.Model):
    __tablename__ = 'chat_message'
    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey('event.id', ondelete='CASCADE'))
    sender_name = db.Column(db.String(150), nullable=False)
    sender_type = db.Column(db.String(20), default='contributor')
    message = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    __table_args__ = (Index('idx_chat_event_id', 'event_id'), Index('idx_chat_timestamp', 'timestamp'),)

class Conversation(db.Model):
    __tablename__ = 'conversation'
    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey('event.id', ondelete='CASCADE'))
    admin_id = db.Column(db.Integer, db.ForeignKey('admin.id', ondelete='CASCADE'))
    contributor_id = db.Column(db.Integer, db.ForeignKey('contributor.id', ondelete='CASCADE'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class PrivateMessage(db.Model):
    __tablename__ = 'private_message'
    id = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(db.Integer, db.ForeignKey('conversation.id', ondelete='CASCADE'))
    sender_type = db.Column(db.String(20), nullable=False)
    sender_id = db.Column(db.Integer, nullable=False)
    message = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    is_read = db.Column(db.Boolean, default=False)
    __table_args__ = (Index('idx_private_conversation_id', 'conversation_id'),)

class Notification(db.Model):
    __tablename__ = 'notification'
    id = db.Column(db.Integer, primary_key=True)
    admin_id = db.Column(db.Integer, db.ForeignKey('admin.id', ondelete='CASCADE'))
    event_id = db.Column(db.Integer, db.ForeignKey('event.id', ondelete='CASCADE'), nullable=True)
    contributor_id = db.Column(db.Integer, db.ForeignKey('contributor.id', ondelete='CASCADE'), nullable=True)
    message = db.Column(db.Text, nullable=False)
    type = db.Column(db.String(50), default='info')
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    __table_args__ = (Index('idx_notification_admin_id', 'admin_id'), Index('idx_notification_created_at', 'created_at'),)

class Testimonial(db.Model):
    __tablename__ = 'testimonial'
    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey('event.id', ondelete='CASCADE'))
    contributor_id = db.Column(db.Integer, db.ForeignKey('contributor.id', ondelete='CASCADE'))
    rating = db.Column(db.Integer, default=0)
    message = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_approved = db.Column(db.Boolean, default=False)
    __table_args__ = (Index('idx_testimonial_event_id', 'event_id'),)

class Withdrawal(db.Model):
    __tablename__ = 'withdrawal'
    id = db.Column(db.Integer, primary_key=True)
    admin_id = db.Column(db.Integer, db.ForeignKey('admin.id', ondelete='CASCADE'))
    amount = db.Column(db.Float, nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    method = db.Column(db.String(20), default='mpesa')
    status = db.Column(db.String(20), default=STATUS_PENDING)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    paid_at = db.Column(db.DateTime, nullable=True)
    __table_args__ = (Index('idx_withdrawal_status', 'status'), Index('idx_withdrawal_admin_id', 'admin_id'),)

class ContactMessage(db.Model):
    __tablename__ = 'contact_message'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    email = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20), nullable=True)
    subject = db.Column(db.String(200), nullable=False)
    message = db.Column(db.Text, nullable=False)
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    __table_args__ = (Index('idx_contact_created_at', 'created_at'),)

class PasswordReset(db.Model):
    __tablename__ = 'password_reset'
    id = db.Column(db.Integer, primary_key=True)
    admin_id = db.Column(db.Integer, db.ForeignKey('admin.id', ondelete='CASCADE'))
    token = db.Column(db.String(100), unique=True, nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    used = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    __table_args__ = (Index('idx_reset_token', 'token'), Index('idx_reset_expires', 'expires_at'),)

class Setting(db.Model):
    __tablename__ = 'setting'
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(100), unique=True, nullable=False)
    value = db.Column(db.Text, nullable=False)

class Announcement(db.Model):
    __tablename__ = 'announcement'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=True)

# ---------- Helper Functions ----------
def send_email(to, subject, body):
    if not EMAIL_PASS:
        logger.warning(f"EMAIL_PASS not set; email to {to} not sent.")
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
        logger.info(f"Email sent to {to}")
    except Exception as e:
        logger.error(f"Email error: {e}")

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
    try:
        n = Notification(admin_id=admin_id, event_id=event_id,
                         contributor_id=contributor_id, message=message, type=type)
        db.session.add(n)
        db.session.commit()
    except Exception as e:
        logger.error(f"Failed to create notification: {e}")

def get_unread_notifications(admin_id):
    return Notification.query.filter_by(admin_id=admin_id, is_read=False).count()

def get_fee_percentage(admin_id):
    admin = Admin.query.get(admin_id)
    if not admin:
        return SERVICE_FEE_PERCENTAGE
    count = admin.referral_count
    if count >= 9: return 1.54
    elif count >= 4: return 1.61
    elif count >= 2: return 1.72
    elif count >= 1: return 1.80
    else: return SERVICE_FEE_PERCENTAGE

def calculate_fee(amount, admin_id=None):
    fee_pct = get_fee_percentage(admin_id) if admin_id else SERVICE_FEE_PERCENTAGE
    fee = round(amount * (fee_pct / 100), 2)
    return max(fee, 0.0)

def get_event_total_contributions(event_id):
    return db.session.query(func.sum(Contributor.paid_amount)).filter_by(
        event_id=event_id, status=STATUS_APPROVED
    ).scalar() or 0

def get_event_total_fee(event_id):
    return db.session.query(func.sum(Contributor.fee_amount)).filter_by(
        event_id=event_id, status=STATUS_APPROVED
    ).scalar() or 0

def get_global_total_fees():
    return db.session.query(func.sum(Contributor.fee_amount)).filter_by(status=STATUS_APPROVED).scalar() or 0

def get_admin_total_fees(admin_id):
    return db.session.query(func.sum(Contributor.fee_amount))\
        .join(Event, Event.id == Contributor.event_id)\
        .filter(Event.admin_id == admin_id, Contributor.status == STATUS_APPROVED).scalar() or 0

def is_fee_overdue(event):
    if not event.first_contribution_date or event.fee_paid:
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
    if event.disabled or (not event.first_contribution_date) or event.fee_paid:
        return False
    if contributor_token:
        return False
    return is_fee_overdue(event)

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

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

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

# ---------- Decorators ----------
def admin_login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('admin_id'):
            flash('Please log in first.', 'warning')
            return redirect(url_for('login'))
        admin = Admin.query.get(session['admin_id'])
        if not admin or not admin.is_active:
            session.clear()
            flash('Account inactive or not found.', 'error')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def super_admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        admin = Admin.query.get(session.get('admin_id'))
        if not admin or not admin.is_super_admin:
            flash('Super admin access required.', 'error')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function

def contributor_login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('contributor_id'):
            flash('Please log in as contributor.', 'warning')
            return redirect(url_for('contributor_login'))
        contrib = Contributor.query.get(session['contributor_id'])
        if not contrib or not contrib.is_active:
            session.pop('contributor_id', None)
            flash('Contributor account invalid.', 'error')
            return redirect(url_for('contributor_login'))
        return f(*args, **kwargs)
    return decorated_function

# ---------- Context Processor ----------
@app.context_processor
def utility_processor():
    return dict(
        is_admin_logged_in=lambda: bool(session.get('admin_id')),
        is_contributor_logged_in=lambda: bool(session.get('contributor_id')),
        get_admin=lambda: Admin.query.get(session.get('admin_id')),
        get_contributor=lambda: Contributor.query.get(session.get('contributor_id')),
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

# ---------- Maintenance Check ----------
@app.before_request
def check_maintenance():
    if request.endpoint in ['settings', 'static', 'login', 'register', 'contributor_login', 'contributor_register']:
        return
    maintenance = Setting.query.filter_by(key='maintenance_mode').first()
    if maintenance and maintenance.value == 'True':
        admin = Admin.query.get(session.get('admin_id'))
        if admin and admin.is_super_admin:
            return
        msg_setting = Setting.query.filter_by(key='maintenance_message').first()
        eta_setting = Setting.query.filter_by(key='maintenance_eta').first()
        msg = msg_setting.value if msg_setting else "We're currently performing scheduled maintenance."
        eta = eta_setting.value if eta_setting else "We'll be back soon."
        return render_template('maintenance.html', message=msg, eta=eta), 503

# ---------- Error Handlers ----------
@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_error(e):
    logger.error(f"500 error: {e}")
    return render_template('500.html'), 500

@app.errorhandler(CSRFError)
def handle_csrf_error(e):
    flash('CSRF token missing or invalid. Please refresh the page and try again.', 'error')
    return redirect(request.referrer or url_for('index'))

# ---------- Routes ----------
@app.route('/')
def index():
    announcements = Announcement.query.filter_by(is_active=True).filter(
        (Announcement.expires_at > datetime.utcnow()) | (Announcement.expires_at.is_(None))
    ).order_by(desc(Announcement.created_at)).all()
    if session.get('admin_id'):
        admin = Admin.query.get(session['admin_id'])
        if admin and admin.is_super_admin:
            return redirect(url_for('super_dashboard'))
        elif admin:
            return redirect(url_for('dashboard'))
    if session.get('contributor_id'):
        return redirect(url_for('contributor_dashboard'))
    return render_template('landing.html', announcements=announcements)

@app.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        username = form.username.data.strip()
        password = form.password.data.strip()
        admin = Admin.query.filter_by(username=username).first()
        if not admin:
            flash('No account found with that username. Please register.', 'error')
            return render_template('login.html', form=form)
        if not admin.is_active:
            flash('This account is disabled. Contact support.', 'error')
            return render_template('login.html', form=form)
        if not check_password(password, admin.password_hash):
            flash('Incorrect password. Please try again.', 'error')
            return render_template('login.html', form=form)
        session.permanent = True
        session['admin_id'] = admin.id
        admin.last_login = datetime.utcnow()
        db.session.commit()
        flash('Logged in successfully.', 'success')
        if not admin.is_super_admin:
            events_count = Event.query.filter_by(admin_id=admin.id).count()
            if events_count == 0:
                flash('Welcome! Let\'s create your first event.', 'info')
                return redirect(url_for('create_event'))
        if admin.is_super_admin:
            return redirect(url_for('super_dashboard'))
        return redirect(url_for('dashboard'))
    return render_template('login.html', form=form)

@app.route('/register', methods=['GET', 'POST'])
def register():
    form = RegisterForm()
    if form.validate_on_submit():
        username = form.username.data.strip()
        password = form.password.data.strip()
        email = form.email.data.strip()
        phone = form.phone.data.strip()
        super_secret = form.super_secret.data.strip()
        ref_code = form.referral_code.data.strip()

        if Admin.query.filter_by(username=username).first():
            flash('Username already taken.', 'error')
            return render_template('register.html', form=form)
        if Admin.query.filter_by(email=email).first():
            flash('Email already registered.', 'error')
            return render_template('register.html', form=form)
        if Admin.query.filter_by(phone=phone).first():
            flash('Phone number already used by another admin.', 'error')
            return render_template('register.html', form=form)

        referral_code = generate_referral_code()
        while Admin.query.filter_by(referral_code=referral_code).first():
            referral_code = generate_referral_code()

        is_super = False
        if super_secret and super_secret == os.environ.get('SUPER_ADMIN_SECRET'):
            is_super = True
            flash('You have been registered as Super Admin.', 'success')

        admin = Admin(
            username=username,
            password_hash=hash_password(password),
            email=email,
            phone=phone,
            referral_code=referral_code,
            is_super_admin=is_super
        )
        db.session.add(admin)
        db.session.commit()

        if ref_code:
            referrer = Admin.query.filter_by(referral_code=ref_code).first()
            if referrer:
                referrer.referral_count += 1
                db.session.commit()
                flash('Referral code accepted! You now have lower fees.', 'success')
            else:
                flash('Invalid referral code.', 'warning')

        session['admin_id'] = admin.id
        session.permanent = True
        admin.last_login = datetime.utcnow()
        db.session.commit()

        flash('🎉 Welcome! Let\'s create your first event.', 'success')
        return redirect(url_for('create_event'))

    return render_template('register.html', form=form)

@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out.', 'info')
    return redirect(url_for('login'))

@app.route('/dashboard')
@admin_login_required
def dashboard():
    admin = Admin.query.get(session['admin_id'])
    if admin.is_super_admin:
        return redirect(url_for('super_dashboard'))
    page = request.args.get('page', 1, type=int)
    events = Event.query.filter_by(admin_id=admin.id).order_by(desc(Event.created_at)).paginate(page=page, per_page=10)
    total_raised = sum(get_event_total_contributions(e.id) for e in events.items)
    pending_count = Contributor.query.filter_by(status=STATUS_PENDING).join(Event).filter(Event.admin_id == admin.id).count()
    announcements = Announcement.query.filter_by(is_active=True).filter(
        (Announcement.expires_at > datetime.utcnow()) | (Announcement.expires_at.is_(None))
    ).order_by(desc(Announcement.created_at)).all()
    return render_template('dashboard.html', admin=admin, events=events,
                            total_raised=total_raised, pending_contributions=pending_count,
                            announcements=announcements)

@app.route('/super-dashboard')
@admin_login_required
@super_admin_required
def super_dashboard():
    admin = Admin.query.get(session['admin_id'])
    total_events = Event.query.count()
    total_contributions = db.session.query(func.sum(Contributor.paid_amount)).filter_by(status=STATUS_APPROVED).scalar() or 0
    total_fees = get_global_total_fees()
    pending_withdrawals = Withdrawal.query.filter_by(status=STATUS_PENDING).count()
    admins = Admin.query.all()
    announcements = Announcement.query.filter_by(is_active=True).filter(
        (Announcement.expires_at > datetime.utcnow()) | (Announcement.expires_at.is_(None))
    ).order_by(desc(Announcement.created_at)).all()
    
    # Completed events (target reached)
    all_events = Event.query.filter_by(is_active=True).all()
    completed_events = []
    for event in all_events:
        raised = get_event_total_contributions(event.id)
        if raised >= event.target_amount and event.target_amount > 0:
            completed_events.append({
                'event': event,
                'raised': raised,
                'fee': get_event_total_fee(event.id)
            })
    
    return render_template('super_dashboard.html', 
                            admin=admin, 
                            total_events=total_events,
                            total_contributions=total_contributions, 
                            total_fees=total_fees,
                            pending_withdrawals=pending_withdrawals, 
                            admins=admins,
                            announcements=announcements,
                            completed_events=completed_events)

@app.route('/super/completed-events')
@admin_login_required
@super_admin_required
def completed_events():
    all_events = Event.query.filter_by(is_active=True).all()
    completed_events = []
    for event in all_events:
        raised = get_event_total_contributions(event.id)
        if raised >= event.target_amount and event.target_amount > 0:
            completed_events.append({
                'event': event,
                'raised': raised,
                'fee': get_event_total_fee(event.id),
                'admin': event.admin
            })
    return render_template('completed_events.html', completed_events=completed_events)

@app.route('/super/request-payment/<int:event_id>', methods=['POST'])
@admin_login_required
@super_admin_required
def request_payment_from_admin(event_id):
    event = Event.query.get_or_404(event_id)
    admin = event.admin
    
    if not admin:
        flash('Event has no admin assigned.', 'error')
        return redirect(url_for('completed_events'))
    
    # Send in-app notification only (no email)
    create_notification(
        admin.id,
        f"💰 Super admin is requesting payment details for your event '{event.title}'. Please reply with your payment method (M-Pesa, Bank, etc.) via Contact page.",
        'payment_request'
    )
    
    flash(f'✅ Payment request sent to {admin.username} via in-app notification.', 'success')
    return redirect(url_for('completed_events'))

@app.route('/super/withdraw-request', methods=['POST'])
@admin_login_required
@super_admin_required
def super_withdraw_request():
    try:
        amount = float(request.form.get('amount', 0))
        phone = request.form.get('phone', '').strip()
    except ValueError:
        amount = 0
    
    if amount < MINIMUM_WITHDRAWAL_FEE:
        flash(f'Minimum withdrawal is KES {MINIMUM_WITHDRAWAL_FEE}.', 'error')
        return redirect(url_for('super_dashboard'))
    
    total_fees = get_global_total_fees()
    if amount > total_fees:
        flash(f'Insufficient fees available. Total fees: KES {total_fees:,.2f}', 'error')
        return redirect(url_for('super_dashboard'))
    
    wd = Withdrawal(
        admin_id=session['admin_id'],
        amount=amount,
        phone=phone,
        method='mpesa',
        status='pending'
    )
    db.session.add(wd)
    db.session.commit()
    
    # Notify all super admins
    super_admins = Admin.query.filter_by(is_super_admin=True).all()
    for sa in super_admins:
        create_notification(
            sa.id,
            f"💰 New withdrawal request from {sa.username}: KES {amount:,.2f}",
            'withdrawal'
        )
    
    flash(f'Withdrawal request of KES {amount:,.2f} submitted.', 'success')
    return redirect(url_for('super_dashboard'))

@app.route('/events/create', methods=['GET', 'POST'])
@admin_login_required
def create_event():
    admin = Admin.query.get(session['admin_id'])
    if admin.is_super_admin:
        flash('Super admins cannot create events.', 'error')
        return redirect(url_for('dashboard'))
    form = EventForm()
    events_count = Event.query.filter_by(admin_id=admin.id).count()
    if form.validate_on_submit():
        token = generate_unique_token()
        while Event.query.filter_by(token=token).first():
            token = generate_unique_token()
        try:
            # Handle picture upload
            picture_path = None
            if form.picture.data:
                file = form.picture.data
                filename = f"event_{token}_{int(datetime.utcnow().timestamp())}_{file.filename}"
                upload_dir = os.path.join(os.path.dirname(__file__), 'static', 'uploads', 'events')
                os.makedirs(upload_dir, exist_ok=True)
                file_path = os.path.join(upload_dir, filename)
                file.save(file_path)
                picture_path = f'/static/uploads/events/{filename}'

            bg_path = None
            if form.background_image.data:
                file = form.background_image.data
                filename = f"bg_{token}_{int(datetime.utcnow().timestamp())}_{file.filename}"
                upload_dir = os.path.join(os.path.dirname(__file__), 'static', 'uploads', 'events')
                os.makedirs(upload_dir, exist_ok=True)
                file_path = os.path.join(upload_dir, filename)
                file.save(file_path)
                bg_path = f'/static/uploads/events/{filename}'

            event = Event(
                token=token,
                admin_id=admin.id,
                event_type=form.event_type.data,
                title=form.title.data,
                description=form.description.data,
                target_amount=form.target_amount.data,
                deadline=form.deadline.data,
                event_date=form.event_date.data,
                picture_url=picture_path,
                background_image_url=bg_path,
                account_name=form.account_name.data,
                paybill=form.paybill.data,
                mpesa_number=form.mpesa_number.data,
                till_number=form.till_number.data,
                bank_name=form.bank_name.data,
                bank_account_name=form.bank_account_name.data,
                bank_account_number=form.bank_account_number.data,
                payment_instructions=form.payment_instructions.data,
                whatsapp_contact=form.whatsapp_contact.data,
                grace_period=int(form.grace_period.data or 0),
                has_grace_period=bool(form.grace_period.data and form.grace_period.data > 0),
                last_activity=datetime.utcnow(),
                lock_message=form.lock_message.data if form.lock_message.data else None
            )
            db.session.add(event)
            db.session.commit()
            flash('Event created successfully!', 'success')
            return redirect(url_for('dashboard'))
        except Exception as e:
            logger.error(f"Event creation error: {e}")
            flash('An error occurred while creating the event.', 'error')
    return render_template('create_event.html', form=form, events_count=events_count)

@app.route('/events/<token>')
def event_landing(token):
    event = Event.query.filter_by(token=token).first_or_404()
    if not event.is_active:
        flash('Event is inactive.', 'error')
        return redirect(url_for('dashboard'))
    if get_page_lock_status(event) or event.disabled:
        return render_template('event_locked.html', event=event)
    contributor = None
    if session.get('contributor_id'):
        contributor = Contributor.query.get(session['contributor_id'])
    total_raised = get_event_total_contributions(event.id)
    chat_messages = ChatMessage.query.filter_by(event_id=event.id).order_by(ChatMessage.timestamp).limit(50).all()
    testimonials = Testimonial.query.filter_by(event_id=event.id, is_approved=True).order_by(desc(Testimonial.created_at)).limit(10).all()
    days = (datetime.utcnow() - event.created_at).days + 1
    daily_note = get_daily_note(event.event_type, days)
    event.last_activity = datetime.utcnow()
    db.session.commit()
    return render_template('event_landing.html', event=event, total_raised=total_raised,
                            chat_messages=chat_messages, testimonials=testimonials, daily_note=daily_note,
                            contributor=contributor, token=token, show_back_button=True)

@app.route('/events/<token>/edit', methods=['GET', 'POST'])
@admin_login_required
def edit_event(token):
    event = Event.query.filter_by(token=token).first_or_404()
    admin = Admin.query.get(session['admin_id'])
    if event.admin_id != admin.id and not admin.is_super_admin:
        flash('Unauthorized.', 'error')
        return redirect(url_for('dashboard'))
    form = EventForm(obj=event)
    if form.validate_on_submit():
        # Handle file uploads (replace existing if new file uploaded)
        picture_path = event.picture_url  # keep old if no new file
        if form.picture.data:
            file = form.picture.data
            filename = f"event_{event.token}_{int(datetime.utcnow().timestamp())}_{file.filename}"
            upload_dir = os.path.join(os.path.dirname(__file__), 'static', 'uploads', 'events')
            os.makedirs(upload_dir, exist_ok=True)
            file_path = os.path.join(upload_dir, filename)
            file.save(file_path)
            picture_path = f'/static/uploads/events/{filename}'

        bg_path = event.background_image_url
        if form.background_image.data:
            file = form.background_image.data
            filename = f"bg_{event.token}_{int(datetime.utcnow().timestamp())}_{file.filename}"
            upload_dir = os.path.join(os.path.dirname(__file__), 'static', 'uploads', 'events')
            os.makedirs(upload_dir, exist_ok=True)
            file_path = os.path.join(upload_dir, filename)
            file.save(file_path)
            bg_path = f'/static/uploads/events/{filename}'

        form.populate_obj(event)
        event.picture_url = picture_path
        event.background_image_url = bg_path
        event.last_activity = datetime.utcnow()
        event.dormant_notified = False
        db.session.commit()
        flash('Event updated.', 'success')
        return redirect(url_for('dashboard'))
    return render_template('edit_event.html', form=form, event=event, show_back_button=True)

@app.route('/events/<token>/delete', methods=['POST'])
@admin_login_required
def delete_event(token):
    event = Event.query.filter_by(token=token).first_or_404()
    admin = Admin.query.get(session['admin_id'])
    if event.admin_id != admin.id and not admin.is_super_admin:
        flash('Unauthorized.', 'error')
        return redirect(url_for('dashboard'))
    try:
        db.session.delete(event)
        db.session.commit()
        flash('Event deleted.', 'success')
    except Exception as e:
        logger.error(f"Delete event error: {e}")
        flash('Could not delete event.', 'error')
    return redirect(url_for('dashboard'))

@app.route('/events/<token>/toggle-active', methods=['POST'])
@admin_login_required
def toggle_event_active(token):
    event = Event.query.filter_by(token=token).first_or_404()
    admin = Admin.query.get(session['admin_id'])
    if event.admin_id != admin.id and not admin.is_super_admin:
        flash('Unauthorized.', 'error')
        return redirect(url_for('dashboard'))
    event.is_active = not event.is_active
    event.last_activity = datetime.utcnow()
    db.session.commit()
    flash(f"Event {'activated' if event.is_active else 'deactivated'}.", 'success')
    return redirect(url_for('dashboard'))

@app.route('/events/<token>/lock-page', methods=['POST'])
@admin_login_required
def lock_event_page(token):
    event = Event.query.filter_by(token=token).first_or_404()
    admin = Admin.query.get(session['admin_id'])
    if event.admin_id != admin.id and not admin.is_super_admin:
        flash('Unauthorized.', 'error')
        return redirect(url_for('dashboard'))
    event.disabled = not event.disabled
    event.last_activity = datetime.utcnow()
    db.session.commit()
    flash(f"Page {'locked' if event.disabled else 'unlocked'}.", 'success')
    return redirect(url_for('dashboard'))

@app.route('/events/<token>/contributors')
@admin_login_required
def manage_contributors(token):
    event = Event.query.filter_by(token=token).first_or_404()
    admin = Admin.query.get(session['admin_id'])
    if event.admin_id != admin.id and not admin.is_super_admin:
        flash('Unauthorized.', 'error')
        return redirect(url_for('dashboard'))
    page = request.args.get('page', 1, type=int)
    contributors = Contributor.query.filter_by(event_id=event.id).order_by(desc(Contributor.created_at)).paginate(page=page, per_page=15)
    return render_template('contributors.html', event=event, contributors=contributors, show_back_button=True)

@app.route('/events/<token>/contributor/add', methods=['POST'])
@admin_login_required
def add_contributor(token):
    flash('Contributors must register themselves via the event link.', 'info')
    return redirect(url_for('manage_contributors', token=token))

@app.route('/contributor/<token>')
def contributor_view(token):
    contrib = Contributor.query.filter_by(token=token).first_or_404()
    event = Event.query.get(contrib.event_id)
    if not event:
        flash('Event not found.', 'error')
        return redirect(url_for('index'))
    payments = Payment.query.filter_by(contributor_id=contrib.id).all()
    show_payments = False
    if contrib.completed_at and (datetime.utcnow() - contrib.completed_at).days >= 7:
        show_payments = True
    is_admin = session.get('admin_id') and (Admin.query.get(session['admin_id']).id == event.admin_id or Admin.query.get(session['admin_id']).is_super_admin)
    is_owner = session.get('contributor_id') == contrib.id
    if not (is_admin or is_owner):
        flash('You are not authorized to view this page.', 'error')
        return redirect(url_for('index'))
    return render_template('contributor_view.html', contrib=contrib, event=event,
                            payments=payments, show_payments=show_payments, show_back_button=True)

@app.route('/contributor/<token>/approve', methods=['POST'])
@admin_login_required
def approve_contributor(token):
    admin = Admin.query.get(session['admin_id'])
    if admin.is_super_admin:
        flash('Super admins cannot approve contributions.', 'error')
        return redirect(url_for('super_dashboard'))
    contrib = Contributor.query.filter_by(token=token).first_or_404()
    event = Event.query.get(contrib.event_id)
    if event.admin_id != admin.id:
        flash('Not your event.', 'error')
        return redirect(url_for('dashboard'))
    if contrib.status != STATUS_PENDING:
        flash('Already processed.', 'info')
        return redirect(url_for('manage_contributors', token=event.token))
    try:
        received = float(request.form.get('received_amount', contrib.pledge_amount))
    except ValueError:
        received = 0
    if received <= 0:
        flash('Received amount must be > 0.', 'error')
        return redirect(url_for('manage_contributors', token=event.token))
    fee = calculate_fee(received, event.admin_id)
    net = received - fee
    contrib.paid_amount = received
    contrib.fee_amount = fee
    contrib.net_contribution = net
    contrib.status = STATUS_APPROVED
    contrib.completed_at = datetime.utcnow()
    payment = Payment(contributor_id=contrib.id, amount=received, note=f'Approved. Fee: KES {fee}')
    db.session.add(payment)
    db.session.commit()
    event.last_activity = datetime.utcnow()
    event.dormant_notified = False
    db.session.commit()
    flash(f'Approved! Fee: KES {fee:.2f}', 'success')
    return redirect(url_for('manage_contributors', token=event.token))

@app.route('/contributor/<token>/decline', methods=['POST'])
@admin_login_required
def decline_contributor(token):
    admin = Admin.query.get(session['admin_id'])
    if admin.is_super_admin:
        flash('Super admins cannot decline contributions.', 'error')
        return redirect(url_for('super_dashboard'))
    contrib = Contributor.query.filter_by(token=token).first_or_404()
    event = Event.query.get(contrib.event_id)
    if event.admin_id != admin.id:
        flash('Not your event.', 'error')
        return redirect(url_for('dashboard'))
    if contrib.status != STATUS_PENDING:
        flash('Already processed.', 'info')
        return redirect(url_for('manage_contributors', token=event.token))
    reason = request.form.get('reason', 'No reason provided.').strip()
    contrib.status = STATUS_DECLINED
    contrib.decline_reason = reason
    db.session.commit()
    flash('Contribution declined.', 'warning')
    return redirect(url_for('manage_contributors', token=event.token))

@app.route('/contributor/<token>/payment-proof', methods=['POST'])
def submit_payment_proof(token):
    contrib = Contributor.query.filter_by(token=token).first_or_404()
    event = Event.query.get(contrib.event_id)
    text = request.form.get('payment_proof_text', '').strip()
    file = request.files.get('screenshot')
    file_path = None
    if file and file.filename:
        if not allowed_file(file.filename):
            flash('File type not allowed. Please upload a PNG, JPG, or GIF.', 'error')
            return redirect(url_for('contributor_view', token=token))
        if file.content_length > MAX_UPLOAD_SIZE:
            flash('File too large (max 5MB).', 'error')
            return redirect(url_for('contributor_view', token=token))
        try:
            ext = file.filename.rsplit('.', 1)[1].lower()
            filename = f"proof_{contrib.token}_{int(datetime.utcnow().timestamp())}.{ext}"
            upload_dir = os.path.join(os.path.dirname(__file__), 'uploads', 'proofs')
            os.makedirs(upload_dir, exist_ok=True)
            file_path = os.path.join(upload_dir, filename)
            file.save(file_path)
            file_path = file_path.replace('\\', '/')
            contrib.payment_proof_screenshot = file_path
        except Exception as e:
            logger.error(f"File upload error: {e}")
            flash('Error uploading file.', 'error')
            return redirect(url_for('contributor_view', token=token))
    contrib.payment_proof_text = text
    db.session.commit()
    if event:
        event.last_activity = datetime.utcnow()
        db.session.commit()
    admin = Admin.query.get(event.admin_id)
    create_notification(admin.id, f'Payment proof from {contrib.name}.', 'info', event.id, contrib.id)
    flash('Proof submitted successfully.', 'info')
    return redirect(url_for('contributor_view', token=contrib.token))

@app.route('/contributor/<token>/receipt')
def contributor_receipt(token):
    contrib = Contributor.query.filter_by(token=token).first_or_404()
    if contrib.status != STATUS_APPROVED or not contrib.completed_at:
        flash('Only approved contributions have receipts.', 'error')
        return redirect(url_for('contributor_view', token=token))
    is_admin = session.get('admin_id') and (Admin.query.get(session['admin_id']).id == contrib.event.admin_id or Admin.query.get(session['admin_id']).is_super_admin)
    is_contributor = session.get('contributor_id') == contrib.id
    if not is_admin and not is_contributor:
        flash('Unauthorized.', 'error')
        return redirect(url_for('index'))
    if not is_admin and (datetime.utcnow() - contrib.completed_at).days < 7:
        flash('Receipt available after 7 days.', 'error')
        return redirect(url_for('contributor_view', token=token))
    buffer = io.BytesIO()
    p = canvas.Canvas(buffer, pagesize=A4)
    p.setFont("Helvetica-Bold", 16)
    p.drawString(50, 750, "CONTRIBUTION RECEIPT")
    p.setFont("Helvetica", 12)
    p.drawString(50, 720, f"Name: {contrib.name}")
    p.drawString(50, 700, f"Phone: {contrib.phone}")
    p.drawString(50, 680, f"Amount Paid: KES {contrib.paid_amount:,.2f}")
    p.drawString(50, 660, f"Fee: KES {contrib.fee_amount:,.2f}")
    p.drawString(50, 640, f"Net: KES {contrib.net_contribution:,.2f}")
    p.drawString(50, 620, f"Event: {contrib.event.title}")
    p.drawString(50, 600, f"Date: {contrib.completed_at.strftime('%Y-%m-%d %H:%M')}")
    p.drawString(50, 580, f"Receipt #: {contrib.token}")
    p.save()
    buffer.seek(0)
    return send_file(buffer, as_attachment=True, download_name=f"receipt_{contrib.token}.pdf", mimetype='application/pdf')

@app.route('/contributor/login', methods=['GET', 'POST'])
def contributor_login():
    event_token = request.args.get('event_token', '')
    form = ContributorLoginForm()
    if form.validate_on_submit():
        username = form.username.data.strip()
        password = form.password.data.strip()
        contrib = Contributor.query.filter_by(username=username).first()
        if not contrib:
            flash('No account found with that username. Please register.', 'error')
            return render_template('contributor_login.html', form=form, event_token=event_token)
        if not contrib.is_active:
            flash('This account is disabled. Contact support.', 'error')
            return render_template('contributor_login.html', form=form, event_token=event_token)
        if not check_password(password, contrib.password_hash):
            flash('Incorrect password. Please try again.', 'error')
            return render_template('contributor_login.html', form=form, event_token=event_token)
        session['contributor_id'] = contrib.id
        contrib.last_login = datetime.utcnow()
        db.session.commit()
        if form.remember.data:
            session.permanent = True
        flash('Logged in successfully.', 'success')
        if event_token:
            return redirect(url_for('event_landing', token=event_token))
        return redirect(url_for('contributor_dashboard'))
    return render_template('contributor_login.html', form=form, event_token=event_token)

@app.route('/contributor/register', methods=['GET', 'POST'])
def contributor_register():
    event_token = request.args.get('event_token', '')
    form = ContributorRegisterForm()
    if form.validate_on_submit():
        username = form.username.data.strip()
        password = form.password.data.strip()
        name = form.name.data.strip()
        phone = form.phone.data.strip()
        if Contributor.query.filter_by(username=username).first():
            flash('Username already taken.', 'error')
            return render_template('contributor_registration.html', form=form, event_token=event_token)
        token = generate_unique_token()
        while Contributor.query.filter_by(token=token).first():
            token = generate_unique_token()
        contrib = Contributor(
            username=username,
            password_hash=hash_password(password),
            name=name,
            phone=phone,
            token=token,
            status=STATUS_PENDING
        )
        db.session.add(contrib)
        db.session.commit()
        session['contributor_id'] = contrib.id
        flash('Registration successful!', 'success')
        if event_token:
            return redirect(url_for('event_landing', token=event_token))
        return redirect(url_for('contributor_dashboard'))
    return render_template('contributor_registration.html', form=form, event_token=event_token)

@app.route('/contributor/logout')
def contributor_logout():
    session.pop('contributor_id', None)
    flash('Logged out.', 'info')
    return redirect(url_for('contributor_login'))

@app.route('/contributor/dashboard')
@contributor_login_required
def contributor_dashboard():
    contrib = Contributor.query.get(session['contributor_id'])
    contributions = Contributor.query.filter_by(name=contrib.name, phone=contrib.phone).all()
    announcements = Announcement.query.filter_by(is_active=True).filter(
        (Announcement.expires_at > datetime.utcnow()) | (Announcement.expires_at.is_(None))
    ).order_by(desc(Announcement.created_at)).all()
    return render_template('contributor_dashboard.html', contrib=contrib, contributions=contributions, announcements=announcements)

@app.route('/contact', methods=['GET', 'POST'])
def contact():
    form = ContactForm()
    if form.validate_on_submit():
        msg = ContactMessage(
            name=form.name.data,
            email=form.email.data,
            phone=form.phone.data,
            subject=form.subject.data,
            message=form.message.data
        )
        db.session.add(msg)
        db.session.commit()
        super_admins = Admin.query.filter_by(is_super_admin=True).all()
        for sa in super_admins:
            create_notification(sa.id, f"New contact message from {msg.name}: {msg.subject}", 'contact')
        send_email(SUPPORT_EMAIL, f"[GoldenVow] {msg.subject}", f"From: {msg.name} <{msg.email}>\nPhone: {msg.phone}\n\n{msg.message}")
        flash('Your message has been sent.', 'success')
        return redirect(url_for('contact'))
    return render_template('contact.html', form=form)

@app.route('/contact-messages')
@admin_login_required
@super_admin_required
def contact_messages():
    messages = ContactMessage.query.order_by(desc(ContactMessage.created_at)).all()
    admins = Admin.query.filter_by(is_active=True).all()
    return render_template('contact_messages.html', messages=messages, admins=admins)

@app.route('/contact-message/<int:mid>/read', methods=['POST'])
@admin_login_required
@super_admin_required
def mark_contact_read(mid):
    msg = ContactMessage.query.get_or_404(mid)
    msg.is_read = True
    db.session.commit()
    flash('Marked as read.', 'success')
    return redirect(url_for('contact_messages'))

@app.route('/forward-contact/<int:mid>', methods=['POST'])
@admin_login_required
@super_admin_required
def forward_contact(mid):
    msg = ContactMessage.query.get_or_404(mid)
    admin_id = request.form.get('admin_id')
    if not admin_id:
        flash('Please select an admin to forward to.', 'error')
        return redirect(url_for('contact_messages'))
    admin = Admin.query.get(admin_id)
    if not admin or not admin.is_active:
        flash('Selected admin is invalid or inactive.', 'error')
        return redirect(url_for('contact_messages'))
    create_notification(
        admin.id,
        f"📨 Super admin forwarded a contact message from {msg.name} (Subject: {msg.subject}). Check contact messages for details.",
        'contact'
    )
    flash(f'Message forwarded to {admin.username} via in-app notification.', 'success')
    return redirect(url_for('contact_messages'))

@app.route('/profile', methods=['GET', 'POST'])
@admin_login_required
def profile():
    admin = Admin.query.get(session['admin_id'])
    form = ProfileForm(obj=admin)
    if form.validate_on_submit():
        admin.email = form.email.data
        admin.phone = form.phone.data
        if form.new_password.data:
            admin.password_hash = hash_password(form.new_password.data)
        db.session.commit()
        flash('Profile updated.', 'success')
        return redirect(url_for('profile'))
    return render_template('profile.html', form=form, admin=admin)

@app.route('/notifications')
@admin_login_required
def notifications():
    admin = Admin.query.get(session['admin_id'])
    notifs = Notification.query.filter_by(admin_id=admin.id).order_by(desc(Notification.created_at)).limit(100).all()
    return render_template('notifications.html', notifications=notifs)

@app.route('/notification/<int:nid>/read', methods=['POST'])
@admin_login_required
def mark_notification_read(nid):
    notif = Notification.query.get_or_404(nid)
    notif.is_read = True
    db.session.commit()
    return jsonify({'success': True})

@app.route('/notification/mark-all-read', methods=['POST'])
@admin_login_required
def mark_all_notifications_read():
    admin = Admin.query.get(session['admin_id'])
    Notification.query.filter_by(admin_id=admin.id, is_read=False).update({'is_read': True})
    db.session.commit()
    return jsonify({'success': True})

@app.route('/settings', methods=['GET', 'POST'])
@admin_login_required
@super_admin_required
def settings():
    maintenance = Setting.query.filter_by(key='maintenance_mode').first()
    if not maintenance:
        maintenance = Setting(key='maintenance_mode', value='False')
        db.session.add(maintenance)
    msg = Setting.query.filter_by(key='maintenance_message').first()
    if not msg:
        msg = Setting(key='maintenance_message', value='We are currently performing scheduled maintenance.')
        db.session.add(msg)
    eta = Setting.query.filter_by(key='maintenance_eta').first()
    if not eta:
        eta = Setting(key='maintenance_eta', value='We expect to be back online within 2 hours.')
        db.session.add(eta)
    db.session.commit()

    form = SettingsForm()
    if form.validate_on_submit():
        maintenance.value = 'True' if form.maintenance_mode.data else 'False'
        msg.value = form.maintenance_message.data or 'We are currently performing scheduled maintenance.'
        eta.value = form.maintenance_eta.data or 'We\'ll be back soon.'
        db.session.commit()
        flash('Settings updated.', 'success')
        return redirect(url_for('settings'))
    form.maintenance_mode.data = (maintenance.value == 'True')
    form.maintenance_message.data = msg.value
    form.maintenance_eta.data = eta.value
    return render_template('settings.html', form=form)

@app.route('/withdrawals')
@admin_login_required
@super_admin_required
def withdrawals():
    wd_list = Withdrawal.query.order_by(desc(Withdrawal.created_at)).all()
    return render_template('withdrawals.html', withdrawals=wd_list)

@app.route('/help')
def help_page():
    return render_template('help.html')

@app.route('/manage-admins')
@admin_login_required
@super_admin_required
def manage_admins():
    admins = Admin.query.all()
    return render_template('manage_admins.html', admins=admins)

@app.route('/admin/<int:aid>/toggle', methods=['POST'])
@admin_login_required
@super_admin_required
def toggle_admin(aid):
    admin = Admin.query.get_or_404(aid)
    if admin.is_super_admin:
        flash('Cannot disable super admin.', 'error')
        return redirect(url_for('manage_admins'))
    admin.is_active = not admin.is_active
    db.session.commit()
    flash('Admin status toggled.', 'success')
    return redirect(url_for('manage_admins'))

@app.route('/admin/<int:aid>/toggle-super', methods=['POST'])
@admin_login_required
@super_admin_required
def toggle_super_admin(aid):
    admin = Admin.query.get_or_404(aid)
    if admin.id == session['admin_id']:
        flash('You cannot change your own super admin status.', 'error')
        return redirect(url_for('manage_admins'))
    admin.is_super_admin = not admin.is_super_admin
    db.session.commit()
    flash(f"Admin '{admin.username}' super admin status toggled.", 'success')
    return redirect(url_for('manage_admins'))

@app.route('/admin/<int:aid>/delete', methods=['POST'])
@admin_login_required
@super_admin_required
def delete_admin(aid):
    admin = Admin.query.get_or_404(aid)
    if admin.is_super_admin:
        flash('Cannot delete super admin.', 'error')
        return redirect(url_for('manage_admins'))
    db.session.delete(admin)
    db.session.commit()
    flash('Admin deleted.', 'success')
    return redirect(url_for('manage_admins'))

@app.route('/add_testimonial/<token>', methods=['POST'])
def add_testimonial(token):
    event = Event.query.filter_by(token=token).first_or_404()
    message = request.form.get('message', '').strip()
    rating = int(request.form.get('rating', 0))
    if not message:
        flash('Please enter a testimonial.', 'error')
        return redirect(url_for('event_landing', token=token))
    testimonial = Testimonial(
        event_id=event.id,
        message=message,
        rating=rating,
        is_approved=False
    )
    db.session.add(testimonial)
    db.session.commit()
    flash('Thank you for your testimonial! It will be reviewed.', 'success')
    return redirect(url_for('event_landing', token=token))

@app.route('/ai-helper')
@admin_login_required
def ai_helper():
    return render_template('ai_helper.html', show_back_button=True)

@app.route('/api/chat', methods=['POST'])
@csrf.exempt
@admin_login_required
def chat():
    try:
        data = request.get_json()
        user_message = data.get('message', '').strip().lower()
        if not user_message:
            return jsonify({'error': 'Message is required'}), 400

        admin = Admin.query.get(session['admin_id'])
        admin_name = admin.username if admin else "Unknown"

        total_events = Event.query.count()
        total_raised = db.session.query(func.sum(Contributor.paid_amount)).filter_by(status=STATUS_APPROVED).scalar() or 0
        pending_contributions = Contributor.query.filter_by(status=STATUS_PENDING).count()
        total_fees = get_global_total_fees()
        active_admins = Admin.query.filter_by(is_active=True).count()
        super_admins = Admin.query.filter_by(is_super_admin=True).count()
        recent_events = Event.query.order_by(desc(Event.created_at)).limit(5).all()
        recent_events_text = "\n".join([f"- {e.title} (created {e.created_at.strftime('%Y-%m-%d')})" for e in recent_events])

        def escalate_to_support_in_app(question):
            super_admins_list = Admin.query.filter_by(is_super_admin=True).all()
            for sa in super_admins_list:
                create_notification(
                    sa.id,
                    f"🤖 AI support request from {admin_name}: {question[:100]}{'...' if len(question) > 100 else ''}",
                    'support'
                )
            return "✅ Your question has been sent to the support team via in-app notifications. Check your bell icon for updates."

        def respond(msg):
            if any(word in msg for word in ['human', 'agent', 'support', 'talk to', 'contact support']):
                return escalate_to_support_in_app(user_message)
            if 'event' in msg and ('count' in msg or 'many' in msg or 'total' in msg):
                return f"📊 You currently have **{total_events}** events."
            if 'raised' in msg or 'total raised' in msg or 'collected' in msg:
                return f"💰 Total contributions raised: **KES {total_raised:,.2f}**."
            if 'pending' in msg or 'approval' in msg:
                return f"⏳ There are **{pending_contributions}** pending contribution approvals."
            if 'fee' in msg or 'fees' in msg:
                return f"💎 Total fees collected: **KES {total_fees:,.2f}**. Fee percentage is {SERVICE_FEE_PERCENTAGE}%."
            if 'admin' in msg:
                if 'active' in msg:
                    return f"👥 There are **{active_admins}** active admins, of which **{super_admins}** are super admins."
                return f"👥 Total admins: **{active_admins}** active, **{super_admins}** super admins."
            if 'recent' in msg or 'latest' in msg:
                if recent_events_text:
                    return f"📅 Recent events:\n{recent_events_text}"
                return "No recent events found."
            if 'help' in msg or 'guide' in msg or 'how' in msg:
                return """📖 **Quick Guide**
1. **Create an event** – click “Create Event” and fill the details.
2. **Add contributors** – under the event, click “Manage” → “Add Contributor”.
3. **Approve contributions** – when a contributor submits proof, review and click “Approve”.
4. **Withdraw fees** – as super admin, go to Withdrawals → Request.
5. **Lock page** – if you want to disable contributions, use the “Lock Page” button.
For more, visit the Help page."""
            if 'hello' in msg or 'hi' in msg or 'hey' in msg:
                return "👋 Hello! I'm your GoldenVow assistant. Ask me about events, contributions, fees, or how to do things."
            return escalate_to_support_in_app(user_message)

        response = respond(user_message)
        return jsonify({'response': response})

    except Exception as e:
        logger.error(f"AI Chat error: {e}")
        return jsonify({'error': 'An internal error occurred. Please try again.'}), 500

# ---------- Password Reset ----------
@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    form = ForgotPasswordForm()
    if form.validate_on_submit():
        email = form.email.data.strip()
        admin = Admin.query.filter_by(email=email).first()
        if admin:
            token = secrets.token_urlsafe(32)
            expires = datetime.utcnow() + timedelta(hours=1)
            reset = PasswordReset(admin_id=admin.id, token=token, expires_at=expires)
            db.session.add(reset)
            db.session.commit()
            reset_link = url_for('reset_password', token=token, _external=True)
            body = f"To reset your password, click here: {reset_link}\nThis link expires in 1 hour."
            send_email(email, "Password Reset - GoldenVow", body)
            flash('A password reset link has been sent to your email.', 'info')
        else:
            flash('No account found with that email.', 'error')
        return redirect(url_for('forgot_password'))
    return render_template('forgot_password.html', form=form)

@app.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    reset = PasswordReset.query.filter_by(token=token, used=False).first()
    if not reset or reset.expires_at < datetime.utcnow():
        flash('Invalid or expired token.', 'error')
        return redirect(url_for('forgot_password'))
    form = ResetPasswordForm()
    if form.validate_on_submit():
        admin = Admin.query.get(reset.admin_id)
        admin.password_hash = hash_password(form.password.data)
        reset.used = True
        db.session.commit()
        flash('Password reset successful. Please login.', 'success')
        return redirect(url_for('login'))
    return render_template('reset_password.html', form=form)

@app.route('/manage-feature-requests')
@admin_login_required
@super_admin_required
def manage_feature_requests():
    return render_template('feature_requests.html')

@app.route('/feature-request', methods=['GET', 'POST'])
@app.route('/feature-request/<event_token>', methods=['GET', 'POST'])
def submit_feature_request(event_token=None):
    flash('Feature request feature is coming soon.', 'info')
    return redirect(url_for('index'))

# ---------- Create Super Admin ----------
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
    return f"Super Admin created!<br>Username: {username}<br>Password: {password}<br><a href='/login'>Login</a>"

# ---------- Scheduler Jobs ----------
def check_dormant_events():
    with app.app_context():
        cutoff = datetime.utcnow() - timedelta(days=7)
        events = Event.query.filter(
            Event.is_active == True,
            Event.last_activity < cutoff,
            Event.dormant_notified == False
        ).all()
        for event in events:
            admin = Admin.query.get(event.admin_id)
            if admin and admin.email:
                subject = f"⚠️ Your event '{event.title}' is inactive – action required"
                body = f"""
Your event '{event.title}' has had no activity for 7 days.
To keep it active, please log in and make a change (e.g., add a contributor, edit details).
If we don't hear from you within 7 hours, the event will be automatically deleted.
"""
                send_email(admin.email, subject, body)
                event.dormant_notified = True
                event.dormant_notified_at = datetime.utcnow()
                db.session.commit()
                logger.info(f"Dormant notification sent for event {event.id}")

def delete_dormant_events():
    with app.app_context():
        cutoff = datetime.utcnow() - timedelta(hours=7)
        events = Event.query.filter(
            Event.dormant_notified == True,
            Event.dormant_notified_at < cutoff,
            Event.is_active == True
        ).all()
        for event in events:
            db.session.delete(event)
            db.session.commit()
            logger.info(f"Dormant event {event.id} deleted")

scheduler = BackgroundScheduler()
scheduler.add_job(check_dormant_events, 'interval', days=1)
scheduler.add_job(delete_dormant_events, 'interval', hours=1)
scheduler.start()

# ---------- Main ----------
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        try:
            db.engine.execute('ALTER TABLE event ADD COLUMN lock_message TEXT')
        except Exception as e:
            logger.info(f"Column lock_message may already exist: {e}")
        for key, default in [
            ('maintenance_mode', 'False'),
            ('maintenance_message', 'We are currently performing scheduled maintenance.'),
            ('maintenance_eta', 'We expect to be back online within 2 hours.'),
        ]:
            if not Setting.query.filter_by(key=key).first():
                db.session.add(Setting(key=key, value=default))
        if Announcement.query.count() == 0:
            ann = Announcement(
                title="Welcome to GoldenVow!",
                content="Start by creating your first event and inviting contributors.",
                is_active=True,
                expires_at=datetime.utcnow() + timedelta(days=30)
            )
            db.session.add(ann)
        db.session.commit()
    app.run(debug=False, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
