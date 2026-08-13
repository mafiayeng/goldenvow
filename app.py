import os
import uuid
import random
import string
import io
import secrets
import smtplib
import logging
import warnings
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from functools import wraps

# Suppress warnings
warnings.filterwarnings("ignore", category=Warning)

from flask import (
    Flask, render_template, request, redirect, url_for, session,
    flash, jsonify, send_file, abort
)
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import desc, func, inspect, Index
from flask_wtf import FlaskForm, CSRFProtect
from flask_wtf.csrf import CSRFError
from wtforms import StringField, PasswordField, FloatField, DateTimeField, TextAreaField, BooleanField, SelectField, IntegerField
from wtforms.validators import DataRequired, Email, Length, NumberRange, ValidationError, Optional, Regexp, EqualTo
from flask_wtf.file import FileField, FileAllowed
import bcrypt
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
import openai
import requests

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
    app.secret_key = 'dev-secret-key-change-in-production'

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
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY', '')

STATUS_PENDING = 'pending'
STATUS_APPROVED = 'approved'
STATUS_DECLINED = 'declined'
STATUS_PAID = 'paid'
STATUS_FAILED = 'failed'
STATUS_CANCELLED = 'cancelled'

# ---------- Forms ----------
class LoginForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(min=3, max=100)])
    password = PasswordField('Password', validators=[DataRequired()])
    remember = BooleanField('Remember Me')

class RegisterForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(min=3, max=100)])
    email = StringField('Email', validators=[DataRequired(), Email()])
    phone = StringField('Phone Number', validators=[DataRequired(), Length(min=10, max=20)])
    password = PasswordField('Password', validators=[DataRequired(), Length(min=8)])
    confirm_password = PasswordField('Confirm Password', validators=[DataRequired(), EqualTo('password')])
    referral_code = StringField('Referral Code (Optional)', validators=[Optional()])
    super_secret = StringField('Super Admin Secret', validators=[Optional()])
    terms = BooleanField('I agree to the Terms and Conditions', validators=[DataRequired()])

class EventForm(FlaskForm):
    title = StringField('Event Title', validators=[DataRequired(), Length(min=3, max=200)])
    event_type = SelectField('Event Type', choices=[
        ('dowry', 'Dowry/Bride Price'),
        ('burial', 'Burial/Funeral'),
        ('medical', 'Medical'),
        ('education', 'Education'),
        ('harambee', 'Harambee'),
        ('other', 'Other')
    ], validators=[DataRequired()])
    description = TextAreaField('Description', validators=[DataRequired()])
    target_amount = FloatField('Target Amount (KES)', validators=[DataRequired(), NumberRange(min=100)])
    deadline = DateTimeField('Deadline', validators=[DataRequired()], format='%Y-%m-%d %H:%M')
    event_date = DateTimeField('Event Date', validators=[DataRequired()], format='%Y-%m-%d %H:%M')
    picture = FileField('Event Picture', validators=[FileAllowed(['jpg', 'jpeg', 'png', 'gif'])])
    background_image = FileField('Background Image', validators=[FileAllowed(['jpg', 'jpeg', 'png', 'gif'])])
    account_name = StringField('Account Name')
    paybill = StringField('Paybill Number')
    mpesa_number = StringField('M-Pesa Number')
    till_number = StringField('Till Number')
    bank_name = StringField('Bank Name')
    bank_account_name = StringField('Bank Account Name')
    bank_account_number = StringField('Bank Account Number')
    payment_instructions = TextAreaField('Payment Instructions')
    whatsapp_contact = StringField('WhatsApp Contact')
    grace_period = IntegerField('Grace Period (Days)', default=0)
    lock_message = TextAreaField('Lock Message (Optional)')

class ContributorRegisterForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(min=3, max=100)])
    password = PasswordField('Password', validators=[DataRequired(), Length(min=8)])
    confirm_password = PasswordField('Confirm Password', validators=[DataRequired(), EqualTo('password')])
    name = StringField('Full Name', validators=[DataRequired(), Length(min=2, max=150)])
    phone = StringField('Phone Number', validators=[DataRequired(), Length(min=10, max=20)])

class ContributorLoginForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    remember = BooleanField('Remember Me')

class ContactForm(FlaskForm):
    name = StringField('Name', validators=[DataRequired(), Length(min=2, max=150)])
    email = StringField('Email', validators=[DataRequired(), Email()])
    phone = StringField('Phone', validators=[Optional()])
    subject = StringField('Subject', validators=[DataRequired(), Length(min=3, max=200)])
    message = TextAreaField('Message', validators=[DataRequired()])

class ProfileForm(FlaskForm):
    email = StringField('Email', validators=[Optional(), Email()])
    phone = StringField('Phone', validators=[Optional()])
    current_password = PasswordField('Current Password', validators=[Optional()])
    new_password = PasswordField('New Password', validators=[Optional(), Length(min=8)])
    confirm_password = PasswordField('Confirm New Password', validators=[Optional(), EqualTo('new_password')])

class ForgotPasswordForm(FlaskForm):
    identifier = StringField('Email or Username', validators=[DataRequired()])

class VerifyCodeForm(FlaskForm):
    code = StringField('Verification Code', validators=[DataRequired(), Length(min=6, max=6)])

class ResetPasswordForm(FlaskForm):
    password = PasswordField('New Password', validators=[DataRequired(), Length(min=8)])
    confirm_password = PasswordField('Confirm Password', validators=[DataRequired(), EqualTo('password')])

class ContributorForgotPasswordForm(FlaskForm):
    identifier = StringField('Username or Phone', validators=[DataRequired()])

class AnnouncementForm(FlaskForm):
    title = StringField('Title', validators=[DataRequired(), Length(min=3, max=200)])
    content = TextAreaField('Content', validators=[DataRequired()])
    is_active = BooleanField('Active')
    expires_at = DateTimeField('Expires At', format='%Y-%m-%d %H:%M', validators=[Optional()])

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
    login_attempts = db.Column(db.Integer, default=0)
    locked_until = db.Column(db.DateTime, nullable=True)
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
    login_attempts = db.Column(db.Integer, default=0)
    locked_until = db.Column(db.DateTime, nullable=True)
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

class PasswordResetCode(db.Model):
    __tablename__ = 'password_reset_code'
    id = db.Column(db.Integer, primary_key=True)
    admin_id = db.Column(db.Integer, db.ForeignKey('admin.id', ondelete='CASCADE'))
    code = db.Column(db.String(6), nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    used = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    __table_args__ = (Index('idx_reset_code', 'code'), Index('idx_reset_code_expires', 'expires_at'),)

class ContributorPasswordResetCode(db.Model):
    __tablename__ = 'contributor_password_reset_code'
    id = db.Column(db.Integer, primary_key=True)
    contributor_id = db.Column(db.Integer, db.ForeignKey('contributor.id', ondelete='CASCADE'))
    code = db.Column(db.String(6), nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    used = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    __table_args__ = (Index('idx_contributor_reset_code', 'code'), Index('idx_contributor_reset_code_expires', 'expires_at'),)

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

class ChatConversation(db.Model):
    __tablename__ = 'chat_conversation'
    id = db.Column(db.Integer, primary_key=True)
    admin_id = db.Column(db.Integer, db.ForeignKey('admin.id', ondelete='CASCADE'), nullable=True)
    contributor_id = db.Column(db.Integer, db.ForeignKey('contributor.id', ondelete='CASCADE'), nullable=True)
    subject = db.Column(db.String(200), nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    __table_args__ = (Index('idx_chat_conversation_admin', 'admin_id'), Index('idx_chat_conversation_contributor', 'contributor_id'),)

class SupportMessage(db.Model):
    __tablename__ = 'support_message'
    id = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(db.Integer, db.ForeignKey('chat_conversation.id', ondelete='CASCADE'))
    sender_type = db.Column(db.String(20), nullable=False)
    sender_id = db.Column(db.Integer, nullable=False)
    message = db.Column(db.Text, nullable=False)
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    __table_args__ = (Index('idx_support_message_conversation', 'conversation_id'), Index('idx_support_message_created', 'created_at'),)

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
    if count >= 9: 
        return 1.54
    elif count >= 4: 
        return 1.61
    elif count >= 2: 
        return 1.72
    elif count >= 1: 
        return 1.80
    else: 
        return SERVICE_FEE_PERCENTAGE

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

def is_account_locked_admin(admin):
    if admin.locked_until and admin.locked_until > datetime.utcnow():
        return True
    return False

def reset_login_attempts_admin(admin):
    admin.login_attempts = 0
    admin.locked_until = None
    db.session.commit()

def increment_login_attempts_admin(admin):
    admin.login_attempts += 1
    if admin.login_attempts >= 5:
        admin.locked_until = datetime.utcnow() + timedelta(minutes=15)
    db.session.commit()

def is_account_locked_contributor(contributor):
    if contributor.locked_until and contributor.locked_until > datetime.utcnow():
        return True
    return False

def reset_login_attempts_contributor(contributor):
    contributor.login_attempts = 0
    contributor.locked_until = None
    db.session.commit()

def increment_login_attempts_contributor(contributor):
    contributor.login_attempts += 1
    if contributor.login_attempts >= 5:
        contributor.locked_until = datetime.utcnow() + timedelta(minutes=15)
    db.session.commit()

def validate_password_strength(password):
    if len(password) < 8:
        return False, 'Password must be at least 8 characters.'
    if not any(c.isdigit() for c in password):
        return False, 'Password must contain at least one number.'
    if not any(c in '!@#$%^&*()_+-=[]{}|;:,.<>?/~`' for c in password):
        return False, 'Password must contain at least one special character (!@#$%^&* etc.).'
    return True, ''

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
        username = form.username.data.strip().lower()
        password = form.password.data.strip()
        
        admin = Admin.query.filter_by(username=username).first()
        if not admin:
            flash('No account found with that username. Please register.', 'error')
            return render_template('login.html', form=form)
        if not admin.is_active:
            flash('This account is disabled. Contact support.', 'error')
            return render_template('login.html', form=form)
        if is_account_locked_admin(admin):
            remaining = (admin.locked_until - datetime.utcnow()).seconds // 60
            flash(f'Account locked. Try again in {remaining} minutes.', 'error')
            return render_template('login.html', form=form)
        if not check_password(password, admin.password_hash):
            increment_login_attempts_admin(admin)
            attempts_left = 5 - admin.login_attempts
            flash(f'Incorrect password. {attempts_left} attempts remaining.', 'error')
            return render_template('login.html', form=form)
        
        reset_login_attempts_admin(admin)
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
        username = form.username.data.strip().lower()
        password = form.password.data.strip()
        email = form.email.data.strip().lower()
        phone = form.phone.data.strip()
        super_secret = form.super_secret.data.strip()
        ref_code = form.referral_code.data.strip()
        
        valid, msg = validate_password_strength(password)
        if not valid:
            flash(msg, 'error')
            return render_template('register.html', form=form)
        
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
        if super_secret and SUPER_ADMIN_SECRET and super_secret == SUPER_ADMIN_SECRET:
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
    session.pop('reset_admin_id', None)
    session.pop('reset_code', None)
    session.pop('contributor_reset_id', None)
    session.pop('contributor_reset_code', None)
    flash('Logged out.', 'info')
    return redirect(url_for('login'))

@app.route('/dashboard')
@admin_login_required
def dashboard():
    admin = Admin.query.get(session['admin_id'])
    if admin.is_super_admin:
        return redirect(url_for('super_dashboard'))
    
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '').strip()
    
    query = Event.query.filter_by(admin_id=admin.id)
    if search:
        query = query.filter(Event.title.ilike(f'%{search}%'))
    
    events = query.order_by(desc(Event.created_at)).paginate(page=page, per_page=10)
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
    try:
        admin = Admin.query.get(session['admin_id'])
        total_events = Event.query.count()
        total_contributions = db.session.query(func.sum(Contributor.paid_amount)).filter_by(status=STATUS_APPROVED).scalar() or 0
        total_fees = get_global_total_fees()
        pending_withdrawals = Withdrawal.query.filter_by(status=STATUS_PENDING).count()
        
        admins = Admin.query.all()
        admin_list = []
        for a in admins:
            admin_list.append({
                'id': a.id,
                'username': a.username,
                'email': a.email,
                'phone': a.phone,
                'is_super_admin': a.is_super_admin,
                'is_active': a.is_active,
                'event_count': Event.query.filter_by(admin_id=a.id).count()
            })
        
        announcements = Announcement.query.filter_by(is_active=True).filter(
            (Announcement.expires_at > datetime.utcnow()) | (Announcement.expires_at.is_(None))
        ).order_by(desc(Announcement.created_at)).all()
        
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
                                admins=admin_list,
                                announcements=announcements,
                                completed_events=completed_events)
    except Exception as e:
        logger.error(f"Super dashboard error: {e}")
        flash('An error occurred loading the super dashboard.', 'error')
        return redirect(url_for('dashboard'))

# ---------- MISSING ROUTES ADDED ----------

@app.route('/completed-events')
@admin_login_required
@super_admin_required
def completed_events():
    """View all completed events (target reached)"""
    try:
        all_events = Event.query.filter_by(is_active=True).all()
        completed_events_list = []
        for event in all_events:
            raised = get_event_total_contributions(event.id)
            if raised >= event.target_amount and event.target_amount > 0:
                admin = Admin.query.get(event.admin_id)
                completed_events_list.append({
                    'event': event,
                    'raised': raised,
                    'fee': get_event_total_fee(event.id),
                    'admin': admin
                })
        return render_template('completed_events.html', completed_events=completed_events_list)
    except Exception as e:
        logger.error(f"Completed events error: {e}")
        flash('An error occurred loading completed events.', 'error')
        return redirect(url_for('super_dashboard'))

@app.route('/help')
def help_page():
    """Help/FAQ page"""
    return render_template('help.html')

@app.route('/faq')
def faq_page():
    """FAQ page (alias for help)"""
    return redirect(url_for('help_page'))

@app.route('/terms')
def terms_page():
    """Terms and Conditions page"""
    return render_template('terms.html')

@app.route('/privacy')
def privacy_page():
    """Privacy Policy page"""
    return render_template('privacy.html')

@app.route('/about')
def about_page():
    """About page"""
    return render_template('about.html')

@app.route('/super/request-payment/<int:event_id>', methods=['POST'])
@admin_login_required
@super_admin_required
def request_payment_from_admin(event_id):
    event = Event.query.get_or_404(event_id)
    admin = Admin.query.get(event.admin_id)
    
    if not admin:
        flash('Event has no admin assigned.', 'error')
        return redirect(url_for('completed_events'))
    
    create_notification(
        admin.id,
        f"💰 Super admin is requesting payment details for your event '{event.title}'. Please reply with your payment method (M-Pesa, Bank, etc.) via Contact page.",
        'payment_request'
    )
    
    flash(f'✅ Payment request sent to {admin.username} via in-app notification.', 'success')
    return redirect(url_for('completed_events'))

# ---------- Continue with remaining routes ----------

@app.route('/events/create', methods=['GET', 'POST'])
@admin_login_required
def create_event():
    try:
        admin = Admin.query.get(session['admin_id'])
        if admin.is_super_admin:
            flash('Super admins oversee the platform. Please use a regular admin account to create events.', 'info')
            return redirect(url_for('dashboard'))
        
        form = EventForm()
        events_count = Event.query.filter_by(admin_id=admin.id).count()
        
        if form.validate_on_submit():
            token = generate_unique_token()
            while Event.query.filter_by(token=token).first():
                token = generate_unique_token()
            
            picture_path = None
            if form.picture.data:
                try:
                    file = form.picture.data
                    ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else 'jpg'
                    filename = f"event_{token}_{int(datetime.utcnow().timestamp())}.{ext}"
                    upload_dir = os.path.join(os.path.dirname(__file__), 'static', 'uploads', 'events')
                    os.makedirs(upload_dir, exist_ok=True)
                    file_path = os.path.join(upload_dir, filename)
                    file.save(file_path)
                    picture_path = f'/static/uploads/events/{filename}'
                except Exception as e:
                    logger.error(f"Picture upload error: {e}")

            bg_path = None
            if form.background_image.data:
                try:
                    file = form.background_image.data
                    ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else 'jpg'
                    filename = f"bg_{token}_{int(datetime.utcnow().timestamp())}.{ext}"
                    upload_dir = os.path.join(os.path.dirname(__file__), 'static', 'uploads', 'events')
                    os.makedirs(upload_dir, exist_ok=True)
                    file_path = os.path.join(upload_dir, filename)
                    file.save(file_path)
                    bg_path = f'/static/uploads/events/{filename}'
                except Exception as e:
                    logger.error(f"Background upload error: {e}")

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
                paybill=form.paybill.data or '',
                mpesa_number=form.mpesa_number.data or '',
                till_number=form.till_number.data or '',
                bank_name=form.bank_name.data or '',
                bank_account_name=form.bank_account_name.data or '',
                bank_account_number=form.bank_account_number.data or '',
                payment_instructions=form.payment_instructions.data or '',
                whatsapp_contact=form.whatsapp_contact.data or '',
                grace_period=int(form.grace_period.data or 0),
                has_grace_period=bool(form.grace_period.data and form.grace_period.data > 0),
                last_activity=datetime.utcnow(),
                lock_message=form.lock_message.data if form.lock_message.data else None
            )
            db.session.add(event)
            db.session.commit()
            flash('Event created successfully! 🎉', 'success')
            return redirect(url_for('dashboard'))
        
        if form.errors:
            for field, errors in form.errors.items():
                for error in errors:
                    flash(f'{field}: {error}', 'error')
        
        return render_template('create_event.html', form=form, events_count=events_count)
        
    except Exception as e:
        logger.error(f"Create event error: {e}")
        flash(f'An error occurred: {str(e)}', 'error')
        return redirect(url_for('dashboard'))

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
        picture_path = event.picture_url
        if form.picture.data:
            try:
                file = form.picture.data
                ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else 'jpg'
                filename = f"event_{event.token}_{int(datetime.utcnow().timestamp())}.{ext}"
                upload_dir = os.path.join(os.path.dirname(__file__), 'static', 'uploads', 'events')
                os.makedirs(upload_dir, exist_ok=True)
                file_path = os.path.join(upload_dir, filename)
                file.save(file_path)
                picture_path = f'/static/uploads/events/{filename}'
            except Exception as e:
                logger.error(f"Picture upload error: {e}")

        bg_path = event.background_image_url
        if form.background_image.data:
            try:
                file = form.background_image.data
                ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else 'jpg'
                filename = f"bg_{event.token}_{int(datetime.utcnow().timestamp())}.{ext}"
                upload_dir = os.path.join(os.path.dirname(__file__), 'static', 'uploads', 'events')
                os.makedirs(upload_dir, exist_ok=True)
                file_path = os.path.join(upload_dir, filename)
                file.save(file_path)
                bg_path = f'/static/uploads/events/{filename}'
            except Exception as e:
                logger.error(f"Background upload error: {e}")

        event.title = form.title.data
        event.event_type = form.event_type.data
        event.description = form.description.data
        event.target_amount = form.target_amount.data
        event.deadline = form.deadline.data
        event.event_date = form.event_date.data
        event.picture_url = picture_path
        event.background_image_url = bg_path
        event.account_name = form.account_name.data
        event.paybill = form.paybill.data or ''
        event.mpesa_number = form.mpesa_number.data or ''
        event.till_number = form.till_number.data or ''
        event.bank_name = form.bank_name.data or ''
        event.bank_account_name = form.bank_account_name.data or ''
        event.bank_account_number = form.bank_account_number.data or ''
        event.payment_instructions = form.payment_instructions.data or ''
        event.whatsapp_contact = form.whatsapp_contact.data or ''
        event.grace_period = int(form.grace_period.data or 0)
        event.has_grace_period = bool(form.grace_period.data and form.grace_period.data > 0)
        event.lock_message = form.lock_message.data if form.lock_message.data else None
        event.last_activity = datetime.utcnow()
        event.dormant_notified = False
        
        db.session.commit()
        flash('Event updated successfully.', 'success')
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
    if not event.first_contribution_date:
        event.first_contribution_date = datetime.utcnow()
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
        username = form.username.data.strip().lower()
        password = form.password.data.strip()
        contrib = Contributor.query.filter_by(username=username).first()
        if not contrib:
            flash('No account found with that username. Please register.', 'error')
            return render_template('contributor_login.html', form=form, event_token=event_token)
        if not contrib.is_active:
            flash('This account is disabled. Contact support.', 'error')
            return render_template('contributor_login.html', form=form, event_token=event_token)
        if is_account_locked_contributor(contrib):
            remaining = (contrib.locked_until - datetime.utcnow()).seconds // 60
            flash(f'Account locked. Try again in {remaining} minutes.', 'error')
            return render_template('contributor_login.html', form=form, event_token=event_token)
        if not check_password(password, contrib.password_hash):
            increment_login_attempts_contributor(contrib)
            attempts_left = 5 - contrib.login_attempts
            flash(f'Incorrect password. {attempts_left} attempts remaining.', 'error')
            return render_template('contributor_login.html', form=form, event_token=event_token)
        reset_login_attempts_contributor(contrib)
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
        username = form.username.data.strip().lower()
        password = form.password.data.strip()
        name = form.name.data.strip()
        phone = form.phone.data.strip()
        
        valid, msg = validate_password_strength(password)
        if not valid:
            flash(msg, 'error')
            return render_template('contributor_registration.html', form=form, event_token=event_token)
        
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
        
        if form.current_password.data:
            if not check_password(form.current_password.data, admin.password_hash):
                flash('Current password is incorrect.', 'error')
                return render_template('profile.html', form=form, admin=admin)
            if form.new_password.data != form.confirm_password.data:
                flash('New passwords do not match.', 'error')
                return render_template('profile.html', form=form, admin=admin)
            valid, msg = validate_password_strength(form.new_password.data)
            if not valid:
                flash(msg, 'error')
                return render_template('profile.html', form=form, admin=admin)
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
        eta = Setting(key='maintenance_eta', value='We will be back soon.')
        db.session.add(eta)
    db.session.commit()
    
    if request.method == 'POST':
        maintenance.value = 'True' if request.form.get('maintenance_mode') == 'on' else 'False'
        msg.value = request.form.get('maintenance_message', '')
        eta.value = request.form.get('maintenance_eta', '')
        db.session.commit()
        flash('Settings updated.', 'success')
        return redirect(url_for('settings'))
    
    return render_template('settings.html', maintenance=maintenance, msg=msg, eta=eta)

@app.route('/announcements')
@admin_login_required
def announcements():
    admin = Admin.query.get(session['admin_id'])
    if not admin.is_super_admin:
        flash('Only super admins can manage announcements.', 'error')
        return redirect(url_for('dashboard'))
    
    announcements = Announcement.query.order_by(desc(Announcement.created_at)).all()
    return render_template('announcements.html', announcements=announcements)

@app.route('/announcement/create', methods=['GET', 'POST'])
@admin_login_required
@super_admin_required
def create_announcement():
    form = AnnouncementForm()
    if form.validate_on_submit():
        announcement = Announcement(
            title=form.title.data,
            content=form.content.data,
            is_active=form.is_active.data,
            expires_at=form.expires_at.data
        )
        db.session.add(announcement)
        db.session.commit()
        flash('Announcement created successfully.', 'success')
        return redirect(url_for('announcements'))
    return render_template('announcement_form.html', form=form, title='Create Announcement')

@app.route('/announcement/<int:id>/edit', methods=['GET', 'POST'])
@admin_login_required
@super_admin_required
def edit_announcement(id):
    announcement = Announcement.query.get_or_404(id)
    form = AnnouncementForm(obj=announcement)
    if form.validate_on_submit():
        announcement.title = form.title.data
        announcement.content = form.content.data
        announcement.is_active = form.is_active.data
        announcement.expires_at = form.expires_at.data
        db.session.commit()
        flash('Announcement updated.', 'success')
        return redirect(url_for('announcements'))
    return render_template('announcement_form.html', form=form, title='Edit Announcement', announcement=announcement)

@app.route('/announcement/<int:id>/delete', methods=['POST'])
@admin_login_required
@super_admin_required
def delete_announcement(id):
    announcement = Announcement.query.get_or_404(id)
    db.session.delete(announcement)
    db.session.commit()
    flash('Announcement deleted.', 'success')
    return redirect(url_for('announcements'))

@app.route('/announcement/<int:id>/toggle', methods=['POST'])
@admin_login_required
@super_admin_required
def toggle_announcement(id):
    announcement = Announcement.query.get_or_404(id)
    announcement.is_active = not announcement.is_active
    db.session.commit()
    flash(f"Announcement {'activated' if announcement.is_active else 'deactivated'}.", 'success')
    return redirect(url_for('announcements'))

# ---------- Chat Routes ----------
@app.route('/chat')
@admin_login_required
def chat():
    admin = Admin.query.get(session['admin_id'])
    conversations = ChatConversation.query.filter_by(admin_id=admin.id, is_active=True).order_by(desc(ChatConversation.updated_at)).all()
    event_ids = [e.id for e in Event.query.filter_by(admin_id=admin.id).all()]
    contributors = Contributor.query.filter(Contributor.event_id.in_(event_ids)).all()
    return render_template('chat.html', admin=admin, conversations=conversations, contributors=contributors)

@app.route('/api/chat/conversations')
@admin_login_required
def api_get_conversations():
    admin = Admin.query.get(session['admin_id'])
    conversations = ChatConversation.query.filter_by(admin_id=admin.id, is_active=True).order_by(desc(ChatConversation.updated_at)).all()
    result = []
    for conv in conversations:
        contributor = Contributor.query.get(conv.contributor_id)
        last_msg = SupportMessage.query.filter_by(conversation_id=conv.id).order_by(desc(SupportMessage.created_at)).first()
        unread_count = SupportMessage.query.filter_by(conversation_id=conv.id, is_read=False).filter(SupportMessage.sender_type != 'admin').count()
        result.append({
            'id': conv.id,
            'contributor_name': contributor.name if contributor else 'Unknown',
            'contributor_phone': contributor.phone if contributor else '',
            'subject': conv.subject or 'General Chat',
            'last_message': last_msg.message if last_msg else 'No messages yet',
            'last_message_time': last_msg.created_at.isoformat() if last_msg else None,
            'unread_count': unread_count,
            'created_at': conv.created_at.isoformat()
        })
    return jsonify(result)

@app.route('/api/chat/messages/<int:conversation_id>')
@admin_login_required
def api_get_chat_messages(conversation_id):
    conversation = ChatConversation.query.get_or_404(conversation_id)
    admin = Admin.query.get(session['admin_id'])
    if conversation.admin_id != admin.id and not admin.is_super_admin:
        return jsonify({'error': 'Unauthorized'}), 403
    messages = SupportMessage.query.filter_by(conversation_id=conversation_id).order_by(SupportMessage.created_at.asc()).all()
    for msg in messages:
        if msg.sender_type != 'admin' and not msg.is_read:
            msg.is_read = True
    db.session.commit()
    result = []
    for msg in messages:
        sender_name = 'You' if msg.sender_type == 'admin' else 'Contributor'
        if msg.sender_type == 'contributor':
            contrib = Contributor.query.get(msg.sender_id)
            if contrib:
                sender_name = contrib.name
        result.append({
            'id': msg.id,
            'sender_type': msg.sender_type,
            'sender_name': sender_name,
            'message': msg.message,
            'timestamp': msg.created_at.isoformat(),
            'is_read': msg.is_read
        })
    return jsonify(result)

@app.route('/api/chat/send', methods=['POST'])
@admin_login_required
def api_send_chat_message():
    admin = Admin.query.get(session['admin_id'])
    data = request.get_json()
    conversation_id = data.get('conversation_id')
    message = data.get('message', '').strip()
    contributor_id = data.get('contributor_id')
    if not message:
        return jsonify({'error': 'Message is required'}), 400
    if conversation_id:
        conversation = ChatConversation.query.get_or_404(conversation_id)
        if conversation.admin_id != admin.id and not admin.is_super_admin:
            return jsonify({'error': 'Unauthorized'}), 403
        support_msg = SupportMessage(
            conversation_id=conversation_id,
            sender_type='admin',
            sender_id=admin.id,
            message=message
        )
        db.session.add(support_msg)
        conversation.updated_at = datetime.utcnow()
        db.session.commit()
        return jsonify({'success': True, 'message_id': support_msg.id})
    elif contributor_id:
        contributor = Contributor.query.get(contributor_id)
        if not contributor:
            return jsonify({'error': 'Contributor not found'}), 404
        conversation = ChatConversation(
            admin_id=admin.id,
            contributor_id=contributor_id,
            subject=f"Chat with {contributor.name}",
            is_active=True
        )
        db.session.add(conversation)
        db.session.commit()
        support_msg = SupportMessage(
            conversation_id=conversation.id,
            sender_type='admin',
            sender_id=admin.id,
            message=message
        )
        db.session.add(support_msg)
        db.session.commit()
        return jsonify({'success': True, 'conversation_id': conversation.id, 'message_id': support_msg.id})
    return jsonify({'error': 'conversation_id or contributor_id required'}), 400

@app.route('/api/chat/contributors')
@admin_login_required
def api_get_chat_contributors():
    admin = Admin.query.get(session['admin_id'])
    event_ids = [e.id for e in Event.query.filter_by(admin_id=admin.id).all()]
    contributors = Contributor.query.filter(Contributor.event_id.in_(event_ids)).all()
    result = []
    for c in contributors:
        result.append({
            'id': c.id,
            'name': c.name,
            'phone': c.phone,
            'event_id': c.event_id,
            'status': c.status,
            'created_at': c.created_at.isoformat()
        })
    return jsonify(result)

@app.route('/admin/chats')
@admin_login_required
def admin_chats():
    admin = Admin.query.get(session['admin_id'])
    if admin.is_super_admin:
        conversations = ChatConversation.query.filter_by(is_active=True).order_by(desc(ChatConversation.updated_at)).all()
    else:
        conversations = ChatConversation.query.filter_by(admin_id=admin.id, is_active=True).order_by(desc(ChatConversation.updated_at)).all()
    return render_template('admin_chats.html', conversations=conversations, admin=admin)

@app.route('/admin/chat/<int:conversation_id>')
@admin_login_required
def admin_chat_view(conversation_id):
    conversation = ChatConversation.query.get_or_404(conversation_id)
    admin = Admin.query.get(session['admin_id'])
    if conversation.admin_id != admin.id and not admin.is_super_admin:
        flash('Unauthorized.', 'error')
        return redirect(url_for('admin_chats'))
    messages = SupportMessage.query.filter_by(conversation_id=conversation_id).order_by(SupportMessage.created_at.asc()).all()
    contributor = Contributor.query.get(conversation.contributor_id)
    for msg in messages:
        if msg.sender_type != 'admin' and not msg.is_read:
            msg.is_read = True
    db.session.commit()
    return render_template('admin_chat_view.html', conversation=conversation, messages=messages, contributor=contributor, admin=admin)

@app.route('/contributor/chats')
@contributor_login_required
def contributor_chats():
    contributor = Contributor.query.get(session['contributor_id'])
    conversations = ChatConversation.query.filter_by(contributor_id=contributor.id, is_active=True).order_by(desc(ChatConversation.updated_at)).all()
    return render_template('contributor_chats.html', conversations=conversations, contributor=contributor)

@app.route('/contributor/chat/<int:conversation_id>')
@contributor_login_required
def contributor_chat_view(conversation_id):
    conversation = ChatConversation.query.get_or_404(conversation_id)
    contributor = Contributor.query.get(session['contributor_id'])
    if conversation.contributor_id != contributor.id:
        flash('Unauthorized.', 'error')
        return redirect(url_for('contributor_chats'))
    messages = SupportMessage.query.filter_by(conversation_id=conversation_id).order_by(SupportMessage.created_at.asc()).all()
    for msg in messages:
        if msg.sender_type != 'contributor' and not msg.is_read:
            msg.is_read = True
    db.session.commit()
    admin = Admin.query.get(conversation.admin_id)
    return render_template('contributor_chat_view.html', conversation=conversation, messages=messages, admin=admin, contributor=contributor)

@app.route('/api/contributor/chat/send', methods=['POST'])
@contributor_login_required
def api_contributor_send_chat():
    contributor = Contributor.query.get(session['contributor_id'])
    data = request.get_json()
    conversation_id = data.get('conversation_id')
    message = data.get('message', '').strip()
    if not message:
        return jsonify({'error': 'Message is required'}), 400
    conversation = ChatConversation.query.get_or_404(conversation_id)
    if conversation.contributor_id != contributor.id:
        return jsonify({'error': 'Unauthorized'}), 403
    support_msg = SupportMessage(
        conversation_id=conversation_id,
        sender_type='contributor',
        sender_id=contributor.id,
        message=message
    )
    db.session.add(support_msg)
    conversation.updated_at = datetime.utcnow()
    db.session.commit()
    if conversation.admin_id:
        create_notification(
            conversation.admin_id,
            f"📩 New message from {contributor.name}: {message[:50]}{'...' if len(message) > 50 else ''}",
            'chat',
            event_id=None,
            contributor_id=contributor.id
        )
    return jsonify({'success': True, 'message_id': support_msg.id})

# ---------- AI Assistant Routes ----------
@app.route('/ai-helper')
@admin_login_required
def ai_helper():
    return render_template('ai_helper.html')

@app.route('/api/ai-chat', methods=['POST'])
@admin_login_required
def api_ai_chat():
    if not OPENAI_API_KEY:
        return jsonify({'error': 'OpenAI API key not configured. Please add OPENAI_API_KEY to environment variables.'}), 503
    data = request.get_json()
    message = data.get('message', '').strip()
    if not message:
        return jsonify({'error': 'Message is required'}), 400
    try:
        client = openai.OpenAI(api_key=OPENAI_API_KEY)
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": """You are GoldenVow AI Assistant, a helpful assistant for a fundraising platform.
                You help users with information about fundraising, event creation, contributions, and platform features.
                You can answer any question but always provide clear, helpful, and accurate information.
                If asked about something outside your knowledge, say so politely and offer to connect with human support.
                
                GoldenVow is a fundraising platform that helps people raise funds for:
                - Dowry (bride price) contributions
                - Funeral/burial expenses
                - Medical emergencies
                - Education fees
                - Community harambee projects
                - Other personal causes
                
                Features include:
                - Event creation with customizable payment methods (M-Pesa, Paybill, Till, Bank)
                - Contributor registration and login
                - Pledge and payment tracking
                - Fee calculation with referral discounts
                - Admin dashboard for managing events and contributions
                - Super admin dashboard for platform oversight
                - Two-way chat between admins and contributors
                - Payment proof submission
                - Receipt generation
                - Notifications
                - Announcements
                """},
                {"role": "user", "content": message}
            ],
            max_tokens=500,
            temperature=0.7
        )
        ai_response = response.choices[0].message.content
        return jsonify({'success': True, 'response': ai_response})
    except Exception as e:
        logger.error(f"AI Chat error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/ai-handoff', methods=['POST'])
@admin_login_required
def api_ai_handoff():
    data = request.get_json()
    reason = data.get('reason', 'User requested human assistance')
    super_admins = Admin.query.filter_by(is_super_admin=True).all()
    for sa in super_admins:
        create_notification(sa.id, f"🤖 AI Handoff Request: {reason}. A user needs human assistance.", 'ai_handoff')
    return jsonify({'success': True, 'message': 'Your request has been submitted. An admin will contact you shortly.'})

# ---------- Password Reset Routes ----------
@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if session.get('admin_id'):
        return redirect(url_for('dashboard'))
    form = ForgotPasswordForm()
    if form.validate_on_submit():
        identifier = form.identifier.data.strip()
        admin = Admin.query.filter((Admin.email == identifier) | (Admin.username == identifier)).first()
        if not admin:
            flash('No account found with that email or username.', 'error')
            return render_template('forgot_password.html', form=form)
        code = ''.join(random.choices(string.digits, k=6))
        expires_at = datetime.utcnow() + timedelta(minutes=15)
        reset_code = PasswordResetCode(admin_id=admin.id, code=code, expires_at=expires_at)
        db.session.add(reset_code)
        db.session.commit()
        try:
            send_email(admin.email, "Password Reset Code - GoldenVow",
                f"""Hello {admin.username}, Your verification code is: {code}. This code will expire in 15 minutes. If you didn't request this, please ignore this email. Best regards, GoldenVow Team""")
            session['reset_admin_id'] = admin.id
            flash('A verification code has been sent to your email.', 'success')
            return redirect(url_for('verify_reset_code'))
        except Exception as e:
            logger.error(f"Password reset email error: {e}")
            flash('Failed to send verification code. Please try again.', 'error')
    return render_template('forgot_password.html', form=form)

@app.route('/verify-reset-code', methods=['GET', 'POST'])
def verify_reset_code():
    if session.get('admin_id'):
        return redirect(url_for('dashboard'))
    admin_id = session.get('reset_admin_id')
    if not admin_id:
        flash('Please request a password reset first.', 'warning')
        return redirect(url_for('forgot_password'))
    admin = Admin.query.get(admin_id)
    if not admin:
        session.pop('reset_admin_id', None)
        flash('Invalid request.', 'error')
        return redirect(url_for('forgot_password'))
    form = VerifyCodeForm()
    if form.validate_on_submit():
        code = form.code.data.strip()
        reset_code = PasswordResetCode.query.filter_by(admin_id=admin_id, code=code, used=False).first()
        if not reset_code:
            flash('Invalid verification code.', 'error')
            return render_template('verify_reset_code.html', form=form)
        if reset_code.expires_at < datetime.utcnow():
            flash('Verification code has expired. Please request a new one.', 'error')
            return redirect(url_for('forgot_password'))
        reset_code.used = True
        db.session.commit()
        session['reset_code_verified'] = True
        flash('Code verified! Please set your new password.', 'success')
        return redirect(url_for('reset_password'))
    return render_template('verify_reset_code.html', form=form, email=admin.email)

@app.route('/reset-password', methods=['GET', 'POST'])
def reset_password():
    if session.get('admin_id'):
        return redirect(url_for('dashboard'))
    admin_id = session.get('reset_admin_id')
    verified = session.get('reset_code_verified', False)
    if not admin_id or not verified:
        flash('Please verify your code first.', 'warning')
        return redirect(url_for('forgot_password'))
    admin = Admin.query.get(admin_id)
    if not admin:
        session.pop('reset_admin_id', None)
        session.pop('reset_code_verified', None)
        flash('Invalid request.', 'error')
        return redirect(url_for('forgot_password'))
    form = ResetPasswordForm()
    if form.validate_on_submit():
        password = form.password.data
        confirm = form.confirm_password.data
        if password != confirm:
            flash('Passwords do not match.', 'error')
            return render_template('reset_password.html', form=form)
        valid, msg = validate_password_strength(password)
        if not valid:
            flash(msg, 'error')
            return render_template('reset_password.html', form=form)
        admin.password_hash = hash_password(password)
        admin.login_attempts = 0
        admin.locked_until = None
        db.session.commit()
        session.pop('reset_admin_id', None)
        session.pop('reset_code_verified', None)
        flash('Password has been reset successfully! Please login.', 'success')
        return redirect(url_for('login'))
    return render_template('reset_password.html', form=form)

# ---------- Contributor Password Reset ----------
@app.route('/contributor/forgot-password', methods=['GET', 'POST'])
def contributor_forgot_password():
    if session.get('contributor_id'):
        return redirect(url_for('contributor_dashboard'))
    form = ContributorForgotPasswordForm()
    if form.validate_on_submit():
        identifier = form.identifier.data.strip()
        contributor = Contributor.query.filter((Contributor.username == identifier) | (Contributor.phone == identifier)).first()
        if not contributor:
            flash('No account found with that username or phone.', 'error')
            return render_template('contributor_forgot_password.html', form=form)
        code = ''.join(random.choices(string.digits, k=6))
        expires_at = datetime.utcnow() + timedelta(minutes=15)
        reset_code = ContributorPasswordResetCode(contributor_id=contributor.id, code=code, expires_at=expires_at)
        db.session.add(reset_code)
        db.session.commit()
        session['contributor_reset_id'] = contributor.id
        flash(f'Your verification code is: {code}. Please enter it below.', 'info')
        return redirect(url_for('contributor_verify_reset_code'))
    return render_template('contributor_forgot_password.html', form=form)

@app.route('/contributor/verify-reset-code', methods=['GET', 'POST'])
def contributor_verify_reset_code():
    if session.get('contributor_id'):
        return redirect(url_for('contributor_dashboard'))
    contributor_id = session.get('contributor_reset_id')
    if not contributor_id:
        flash('Please request a password reset first.', 'warning')
        return redirect(url_for('contributor_forgot_password'))
    contributor = Contributor.query.get(contributor_id)
    if not contributor:
        session.pop('contributor_reset_id', None)
        flash('Invalid request.', 'error')
        return redirect(url_for('contributor_forgot_password'))
    form = VerifyCodeForm()
    if form.validate_on_submit():
        code = form.code.data.strip()
        reset_code = ContributorPasswordResetCode.query.filter_by(contributor_id=contributor_id, code=code, used=False).first()
        if not reset_code:
            flash('Invalid verification code.', 'error')
            return render_template('contributor_verify_reset_code.html', form=form)
        if reset_code.expires_at < datetime.utcnow():
            flash('Verification code has expired. Please request a new one.', 'error')
            return redirect(url_for('contributor_forgot_password'))
        reset_code.used = True
        db.session.commit()
        session['contributor_reset_verified'] = True
        flash('Code verified! Please set your new password.', 'success')
        return redirect(url_for('contributor_reset_password'))
    return render_template('contributor_verify_reset_code.html', form=form)

@app.route('/contributor/reset-password', methods=['GET', 'POST'])
def contributor_reset_password():
    if session.get('contributor_id'):
        return redirect(url_for('contributor_dashboard'))
    contributor_id = session.get('contributor_reset_id')
    verified = session.get('contributor_reset_verified', False)
    if not contributor_id or not verified:
        flash('Please verify your code first.', 'warning')
        return redirect(url_for('contributor_forgot_password'))
    contributor = Contributor.query.get(contributor_id)
    if not contributor:
        session.pop('contributor_reset_id', None)
        session.pop('contributor_reset_verified', None)
        flash('Invalid request.', 'error')
        return redirect(url_for('contributor_forgot_password'))
    form = ResetPasswordForm()
    if form.validate_on_submit():
        password = form.password.data
        confirm = form.confirm_password.data
        if password != confirm:
            flash('Passwords do not match.', 'error')
            return render_template('contributor_reset_password.html', form=form)
        valid, msg = validate_password_strength(password)
        if not valid:
            flash(msg, 'error')
            return render_template('contributor_reset_password.html', form=form)
        contributor.password_hash = hash_password(password)
        contributor.login_attempts = 0
        contributor.locked_until = None
        db.session.commit()
        session.pop('contributor_reset_id', None)
        session.pop('contributor_reset_verified', None)
        flash('Password has been reset successfully! Please login.', 'success')
        return redirect(url_for('contributor_login'))
    return render_template('contributor_reset_password.html', form=form)

# ---------- Admin User Management ----------
@app.route('/admin/users')
@admin_login_required
@super_admin_required
def admin_users():
    admins = Admin.query.all()
    return render_template('admin_users.html', admins=admins)

@app.route('/admin/user/<int:id>/toggle', methods=['POST'])
@admin_login_required
@super_admin_required
def admin_user_toggle(id):
    admin = Admin.query.get_or_404(id)
    if admin.is_super_admin and admin.id == session.get('admin_id'):
        flash('You cannot deactivate yourself.', 'error')
        return redirect(url_for('admin_users'))
    admin.is_active = not admin.is_active
    db.session.commit()
    flash(f"User {'activated' if admin.is_active else 'deactivated'}.", 'success')
    return redirect(url_for('admin_users'))

@app.route('/admin/user/<int:id>/make-super', methods=['POST'])
@admin_login_required
@super_admin_required
def admin_make_super(id):
    admin = Admin.query.get_or_404(id)
    if admin.id == session.get('admin_id'):
        flash('You are already super admin.', 'info')
        return redirect(url_for('admin_users'))
    admin.is_super_admin = True
    db.session.commit()
    flash(f"{admin.username} is now a super admin.", 'success')
    return redirect(url_for('admin_users'))

@app.route('/admin/user/<int:id>/remove-super', methods=['POST'])
@admin_login_required
@super_admin_required
def admin_remove_super(id):
    admin = Admin.query.get_or_404(id)
    if admin.id == session.get('admin_id'):
        flash('You cannot remove your own super admin status.', 'error')
        return redirect(url_for('admin_users'))
    admin.is_super_admin = False
    db.session.commit()
    flash(f"Super admin status removed from {admin.username}.", 'success')
    return redirect(url_for('admin_users'))

# ---------- API Routes ----------
@app.route('/api/events')
def api_get_events():
    events = Event.query.filter_by(is_active=True).all()
    result = []
    for event in events:
        total_raised = get_event_total_contributions(event.id)
        contributors_count = Contributor.query.filter_by(event_id=event.id, status=STATUS_APPROVED).count()
        result.append({
            'id': event.id,
            'token': event.token,
            'title': event.title,
            'description': event.description,
            'event_type': event.event_type,
            'target_amount': event.target_amount,
            'raised_amount': total_raised,
            'contributors_count': contributors_count,
            'deadline': event.deadline.isoformat(),
            'event_date': event.event_date.isoformat(),
            'picture_url': event.picture_url,
            'created_at': event.created_at.isoformat(),
            'progress': min(100, (total_raised / event.target_amount * 100) if event.target_amount > 0 else 0)
        })
    return jsonify(result)

@app.route('/api/event/<token>')
def api_get_event(token):
    event = Event.query.filter_by(token=token).first_or_404()
    total_raised = get_event_total_contributions(event.id)
    contributors = Contributor.query.filter_by(event_id=event.id, status=STATUS_APPROVED).all()
    return jsonify({
        'id': event.id,
        'token': event.token,
        'title': event.title,
        'description': event.description,
        'event_type': event.event_type,
        'target_amount': event.target_amount,
        'raised_amount': total_raised,
        'deadline': event.deadline.isoformat(),
        'event_date': event.event_date.isoformat(),
        'picture_url': event.picture_url,
        'background_image_url': event.background_image_url,
        'payment_methods': {
            'paybill': event.paybill,
            'mpesa_number': event.mpesa_number,
            'till_number': event.till_number,
            'bank_name': event.bank_name,
            'bank_account_name': event.bank_account_name,
            'bank_account_number': event.bank_account_number
        },
        'contributors_count': len(contributors),
        'created_at': event.created_at.isoformat(),
        'is_active': event.is_active
    })

@app.route('/api/contributors')
@admin_login_required
def api_get_contributors():
    admin = Admin.query.get(session['admin_id'])
    if admin.is_super_admin:
        contributors = Contributor.query.all()
    else:
        event_ids = [e.id for e in Event.query.filter_by(admin_id=admin.id).all()]
        contributors = Contributor.query.filter(Contributor.event_id.in_(event_ids)).all()
    result = []
    for c in contributors:
        event = Event.query.get(c.event_id)
        result.append({
            'id': c.id,
            'name': c.name,
            'phone': c.phone,
            'pledge_amount': c.pledge_amount,
            'paid_amount': c.paid_amount,
            'fee_amount': c.fee_amount,
            'status': c.status,
            'event_title': event.title if event else 'Unknown',
            'created_at': c.created_at.isoformat()
        })
    return jsonify(result)

@app.route('/api/contributor/<token>')
def api_get_contributor(token):
    contributor = Contributor.query.filter_by(token=token).first_or_404()
    event = Event.query.get(contributor.event_id)
    return jsonify({
        'id': contributor.id,
        'token': contributor.token,
        'name': contributor.name,
        'phone': contributor.phone,
        'pledge_amount': contributor.pledge_amount,
        'paid_amount': contributor.paid_amount,
        'fee_amount': contributor.fee_amount,
        'net_contribution': contributor.net_contribution,
        'status': contributor.status,
        'event_title': event.title if event else 'Unknown',
        'created_at': contributor.created_at.isoformat(),
        'completed_at': contributor.completed_at.isoformat() if contributor.completed_at else None
    })

@app.route('/api/dashboard-stats')
@admin_login_required
def api_dashboard_stats():
    admin = Admin.query.get(session['admin_id'])
    if admin.is_super_admin:
        total_events = Event.query.count()
        total_contributors = Contributor.query.count()
        total_raised = db.session.query(func.sum(Contributor.paid_amount)).filter_by(status=STATUS_APPROVED).scalar() or 0
        total_fees = get_global_total_fees()
        pending_count = Contributor.query.filter_by(status=STATUS_PENDING).count()
    else:
        event_ids = [e.id for e in Event.query.filter_by(admin_id=admin.id).all()]
        total_events = len(event_ids)
        total_contributors = Contributor.query.filter(Contributor.event_id.in_(event_ids)).count()
        total_raised = db.session.query(func.sum(Contributor.paid_amount)).filter(
            Contributor.event_id.in_(event_ids), Contributor.status == STATUS_APPROVED
        ).scalar() or 0
        total_fees = db.session.query(func.sum(Contributor.fee_amount)).filter(
            Contributor.event_id.in_(event_ids), Contributor.status == STATUS_APPROVED
        ).scalar() or 0
        pending_count = Contributor.query.filter(
            Contributor.event_id.in_(event_ids), Contributor.status == STATUS_PENDING
        ).count()
    return jsonify({
        'total_events': total_events,
        'total_contributors': total_contributors,
        'total_raised': total_raised,
        'total_fees': total_fees,
        'pending_contributions': pending_count
    })

# ---------- Scheduled Jobs ----------
def check_dormant_events():
    with app.app_context():
        cutoff = datetime.utcnow() - timedelta(days=7)
        dormant_events = Event.query.filter(
            Event.last_activity < cutoff,
            Event.is_active == True,
            Event.dormant_notified == False
        ).all()
        for event in dormant_events:
            admin = Admin.query.get(event.admin_id)
            if admin:
                create_notification(admin.id, f"⏰ Your event '{event.title}' has been dormant for 7 days. Consider sharing it to get more contributions!", 'dormant')
                event.dormant_notified = True
                event.dormant_notified_at = datetime.utcnow()
                db.session.commit()

def check_fee_payments():
    with app.app_context():
        events = Event.query.filter(
            Event.is_active == True,
            Event.fee_paid == False,
            Event.first_contribution_date.isnot(None)
        ).all()
        for event in events:
            if is_fee_overdue(event):
                admin = Admin.query.get(event.admin_id)
                if admin:
                    total_fee = get_event_total_fee(event.id)
                    create_notification(admin.id, f"⚠️ Event '{event.title}' has overdue fees of KES {total_fee:,.2f}. Please pay within 24 hours or your event page may be locked.", 'fee_overdue')

# Initialize scheduler
scheduler = BackgroundScheduler()
scheduler.add_job(check_dormant_events, IntervalTrigger(hours=24))
scheduler.add_job(check_fee_payments, IntervalTrigger(hours=12))
scheduler.start()

# ---------- Create Tables ----------
with app.app_context():
    db.create_all()
    
    # Create default super admin if none exists
    if not Admin.query.filter_by(is_super_admin=True).first():
        super_admin = Admin(
            username='superadmin',
            password_hash=hash_password('SuperAdmin2024!'),
            email='superadmin@goldenvow.com',
            phone='+254700000000',
            is_super_admin=True,
            is_active=True,
            referral_code=generate_referral_code()
        )
        db.session.add(super_admin)
        db.session.commit()
        print("Super admin created: superadmin / SuperAdmin2024!")

# ---------- Main ----------
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
