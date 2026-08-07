import os
import secrets
from datetime import datetime, timedelta
from io import BytesIO
from flask import Flask, render_template_string, request, redirect, url_for, session, flash, send_file, abort
from flask_sqlalchemy import SQLAlchemy
from flask_socketio import SocketIO, emit, join_room, leave_room
from apscheduler.schedulers.background import BackgroundScheduler
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
import bcrypt
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv
from jinja2 import BaseLoader, TemplateNotFound

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', secrets.token_hex(16))
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///goldenvow.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)

db = SQLAlchemy(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# -------------------- HELPERS --------------------
def hash_password(password):
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def check_password(password, hashed):
    if not hashed:
        return False
    return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))

def generate_token():
    return secrets.token_urlsafe(32)

def get_setting(key, default=None):
    setting = Setting.query.filter_by(key=key).first()
    return setting.value if setting else default

def send_email(to, subject, html_body, text_body=None):
    if not os.environ.get('EMAIL_USER') or not os.environ.get('EMAIL_PASS'):
        print(f"EMAIL (simulated): To={to}, Subject={subject}\n{html_body}")
        return True
    try:
        msg = MIMEMultipart('alternative')
        msg['From'] = os.environ['EMAIL_USER']
        msg['To'] = to
        msg['Subject'] = subject
        if text_body:
            msg.attach(MIMEText(text_body, 'plain'))
        msg.attach(MIMEText(html_body, 'html'))
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(os.environ['EMAIL_USER'], os.environ['EMAIL_PASS'])
        server.send_message(msg)
        server.quit()
        return True
    except Exception as e:
        print(f"Email error: {e}")
        return False

def create_notification(user_type, user_id, message, link=None):
    notif = Notification(user_type=user_type, user_id=user_id, message=message, link=link)
    db.session.add(notif)
    db.session.commit()

def get_unread_notifications(user_type, user_id):
    return Notification.query.filter_by(user_type=user_type, user_id=user_id, is_read=False).count()

# -------------------- DECORATORS --------------------
def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session or session.get('user_type') not in ['admin', 'contributor', 'super']:
            flash('Please login first.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if session.get('user_type') not in ['admin', 'super']:
            flash('Admin access required.', 'danger')
            return redirect(url_for('login'))
        admin = Admin.query.get(session.get('user_id'))
        if not admin or not admin.is_active:
            flash('Account inactive or not found.', 'danger')
            return redirect(url_for('logout'))
        return f(*args, **kwargs)
    return decorated

def super_admin_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if session.get('user_type') != 'super':
            flash('Super Admin access required.', 'danger')
            return redirect(url_for('login'))
        admin = Admin.query.get(session.get('user_id'))
        if not admin or not admin.is_super_admin:
            flash('Super Admin privileges required.', 'danger')
            return redirect(url_for('logout'))
        return f(*args, **kwargs)
    return decorated

# -------------------- MODELS --------------------
class Admin(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    is_super_admin = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    phone = db.Column(db.String(20))
    events = db.relationship('Event', backref='admin', lazy=True)

class Event(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    category = db.Column(db.String(50), nullable=False)
    target_amount = db.Column(db.Float, nullable=False)
    raised_amount = db.Column(db.Float, default=0.0)
    admin_id = db.Column(db.Integer, db.ForeignKey('admin.id'), nullable=False)
    event_token = db.Column(db.String(100), unique=True, nullable=False)
    logo_url = db.Column(db.String(300))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    deadline = db.Column(db.DateTime)
    is_locked = db.Column(db.Boolean, default=False)
    contributors = db.relationship('Contributor', backref='event', lazy=True)
    payments = db.relationship('Payment', backref='event', lazy=True)

class Contributor(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(20))
    password_hash = db.Column(db.String(200))
    event_id = db.Column(db.Integer, db.ForeignKey('event.id'), nullable=False)
    pledge_amount = db.Column(db.Float, nullable=False)
    paid_amount = db.Column(db.Float, default=0.0)
    sender_name = db.Column(db.String(100))
    referred_by = db.Column(db.String(100))
    referral_discount = db.Column(db.Float, default=0.0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    payments = db.relationship('Payment', backref='contributor', lazy=True)

class Payment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey('event.id'), nullable=False)
    contributor_id = db.Column(db.Integer, db.ForeignKey('contributor.id'), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    sender_name = db.Column(db.String(100), nullable=False)
    proof_image = db.Column(db.String(300))
    status = db.Column(db.String(20), default='pending')
    admin_notes = db.Column(db.Text)
    fee_deducted = db.Column(db.Float, default=0.0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    approved_at = db.Column(db.DateTime)

class ChatMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sender_type = db.Column(db.String(20), nullable=False)
    sender_id = db.Column(db.Integer, nullable=False)
    sender_name = db.Column(db.String(100))
    message = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    room = db.Column(db.String(50), default='public')

class PrivateMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(db.Integer, db.ForeignKey('conversation.id'), nullable=False)
    sender_type = db.Column(db.String(20), nullable=False)
    sender_id = db.Column(db.Integer, nullable=False)
    message = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    is_read = db.Column(db.Boolean, default=False)

class Conversation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    admin_id = db.Column(db.Integer, db.ForeignKey('admin.id'), nullable=False)
    contributor_id = db.Column(db.Integer, db.ForeignKey('contributor.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    messages = db.relationship('PrivateMessage', backref='conversation', lazy=True)

class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_type = db.Column(db.String(20), nullable=False)
    user_id = db.Column(db.Integer, nullable=False)
    message = db.Column(db.Text, nullable=False)
    link = db.Column(db.String(300))
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Testimonial(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    content = db.Column(db.Text, nullable=False)
    rating = db.Column(db.Integer, default=5)
    is_approved = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Withdrawal(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    admin_id = db.Column(db.Integer, db.ForeignKey('admin.id'), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    phone_number = db.Column(db.String(20), nullable=False)
    status = db.Column(db.String(20), default='pending')
    requested_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime)

class ContactMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), nullable=False)
    subject = db.Column(db.String(200))
    message = db.Column(db.Text, nullable=False)
    is_resolved = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class PasswordReset(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), nullable=False)
    token = db.Column(db.String(100), unique=True, nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    used = db.Column(db.Boolean, default=False)
    user_type = db.Column(db.String(20), nullable=False)

class Setting(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(100), unique=True, nullable=False)
    value = db.Column(db.Text)
    description = db.Column(db.String(300))

class FeatureRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False)
    user_type = db.Column(db.String(20))
    user_id = db.Column(db.Integer)
    votes = db.Column(db.Integer, default=0)
    status = db.Column(db.String(20), default='pending')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# -------------------- CUSTOM JINJA LOADER --------------------
BASE_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>GoldenVow – {% block title %}Fundraising with Trust{% endblock %}</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0-alpha1/dist/css/bootstrap.min.css" rel="stylesheet">
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.10.0/font/bootstrap-icons.css">
    <style>
        :root { --primary: #d4af37; --primary-dark: #b8960f; --dark-bg: #05050f; --glass: rgba(255,255,255,0.08); --glass-border: rgba(255,255,255,0.12); }
        * { box-sizing: border-box; }
        body {
            background: var(--dark-bg);
            background-image: radial-gradient(ellipse at 20% 50%, rgba(212,175,55,0.08) 0%, transparent 70%), radial-gradient(ellipse at 80% 50%, rgba(212,175,55,0.05) 0%, transparent 70%), url('data:image/svg+xml,%3Csvg xmlns="http://www.w3.org/2000/svg" width="400" height="400"%3E%3Ctext x="50%25" y="50%25" font-size="60" fill="rgba(212,175,55,0.03)" transform="rotate(-30,200,200)"%3EGoldenVow%3C/text%3E%3C/svg%3E');
            background-repeat: repeat, no-repeat, repeat;
            background-size: auto, cover, 300px 300px;
            background-attachment: fixed;
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            min-height: 100vh;
            color: #eee;
        }
        .glass-card { background: var(--glass); backdrop-filter: blur(12px); border: 1px solid var(--glass-border); box-shadow: 0 8px 32px rgba(0,0,0,0.4); border-radius: 20px; transition: 0.3s; }
        .glass-card:hover { transform: translateY(-6px); box-shadow: 0 12px 40px rgba(212,175,55,0.15); }
        .navbar-gold { background: rgba(10,10,26,0.85); backdrop-filter: blur(10px); border-bottom: 2px solid var(--primary); }
        .navbar-gold .navbar-brand, .navbar-gold .nav-link { color: #fff; }
        .navbar-gold .nav-link:hover { color: var(--primary); }
        .btn-gold { background: linear-gradient(135deg, var(--primary), var(--primary-dark)); color: #fff; border: none; box-shadow: 0 4px 15px rgba(212,175,55,0.3); transition: 0.3s; }
        .btn-gold:hover { transform: scale(1.04); box-shadow: 0 6px 25px rgba(212,175,55,0.5); color: #fff; }
        .btn-outline-gold { border: 2px solid var(--primary); color: var(--primary); background: transparent; }
        .btn-outline-gold:hover { background: var(--primary); color: #fff; }
        .admin-sidebar { background: rgba(5,5,15,0.85); backdrop-filter: blur(12px); border-radius: 20px 0 0 20px; min-height: 100vh; padding: 25px 15px; border-right: 2px solid var(--primary); }
        .admin-sidebar .nav-link { color: #bbb; border-radius: 12px; padding: 10px 15px; }
        .admin-sidebar .nav-link:hover, .admin-sidebar .nav-link.active { background: rgba(212,175,55,0.15); color: var(--primary); }
        .admin-sidebar h5 { color: var(--primary); }
        .hero-section { background: radial-gradient(ellipse at center, rgba(212,175,55,0.12) 0%, transparent 70%); border-radius: 30px; padding: 60px 20px; border: 1px solid rgba(212,175,55,0.15); }
        .whatsapp-float { position: fixed; bottom: 20px; right: 20px; z-index: 1000; background: #25D366; box-shadow: 0 4px 20px rgba(37,211,102,0.4); border-radius: 50px; padding: 12px 24px; color: #fff; font-weight: bold; }
        .whatsapp-float:hover { transform: scale(1.05); background: #128C7E; color: #fff; }
        .chat-container { background: rgba(255,255,255,0.05); backdrop-filter: blur(8px); border: 1px solid var(--glass-border); border-radius: 15px; padding: 15px; }
        .chat-msg.admin { background: var(--primary); color: #000; }
        .chat-msg.contributor { background: rgba(255,255,255,0.15); color: #fff; }
        .chat-msg.super { background: #dc3545; color: #fff; }
        .footer { background: rgba(5,5,15,0.9); border-top: 1px solid var(--primary); color: #aaa; }
        .footer a { color: var(--primary); }
        .maintenance-banner { background: #ffc107; color: #000; }
        .intro-container { height: 100vh; display: flex; align-items: center; justify-content: center; background: radial-gradient(ellipse at 30% 40%, rgba(212,175,55,0.2), transparent 70%), radial-gradient(ellipse at 70% 60%, rgba(212,175,55,0.1), transparent 60%), var(--dark-bg); text-align: center; position: relative; overflow: hidden; }
        .intro-container::before { content: ''; position: absolute; top: -50%; left: -50%; width: 200%; height: 200%; background: repeating-linear-gradient(45deg, transparent, transparent 30px, rgba(212,175,55,0.02) 30px, rgba(212,175,55,0.02) 60px); animation: shimmer 20s linear infinite; }
        @keyframes shimmer { 0% { transform: translateX(-50%) translateY(-50%) rotate(0deg); } 100% { transform: translateX(-50%) translateY(-50%) rotate(360deg); } }
        .intro-title { font-size: 4.5rem; font-weight: 800; letter-spacing: 6px; text-shadow: 0 0 40px rgba(212,175,55,0.3); position: relative; z-index: 1; }
        .intro-sub { font-size: 1.8rem; opacity: 0.8; position: relative; z-index: 1; }
        .intro-btn { margin-top: 40px; padding: 18px 60px; font-size: 1.3rem; border-radius: 50px; background: linear-gradient(135deg, var(--primary), var(--primary-dark)); color: #fff; border: none; box-shadow: 0 8px 30px rgba(212,175,55,0.4); transition: 0.3s; position: relative; z-index: 1; }
        .intro-btn:hover { transform: scale(1.06); box-shadow: 0 12px 40px rgba(212,175,55,0.6); }
        .gold-sparkle { position: absolute; width: 100%; height: 100%; background: radial-gradient(circle at 20% 30%, rgba(212,175,55,0.1), transparent 60%); pointer-events: none; z-index: 0; }
        .table { background: rgba(255,255,255,0.05); border-radius: 15px; overflow: hidden; color: #eee; }
        .table thead { background: rgba(212,175,55,0.2); }
        .table td, .table th { border-color: rgba(255,255,255,0.05); }
        .list-group-item { background: rgba(255,255,255,0.03); border-color: rgba(255,255,255,0.05); color: #eee; }
        .list-group-item:hover { background: rgba(212,175,55,0.08); }
        .badge { font-weight: 500; }
        .accordion-item { background: rgba(255,255,255,0.03); border-color: rgba(255,255,255,0.05); }
        .accordion-button { background: transparent; color: #eee; }
        .accordion-button:not(.collapsed) { background: rgba(212,175,55,0.15); color: var(--primary); }
        .accordion-button:focus { box-shadow: none; border-color: var(--primary); }
        .accordion-body { background: rgba(255,255,255,0.02); color: #ddd; }
        @media (max-width: 768px) { .admin-sidebar { border-radius: 0; min-height: auto; } .intro-title { font-size: 2.8rem; } .intro-sub { font-size: 1.2rem; } }
    </style>
    {% block extra_css %}{% endblock %}
</head>
<body>
    {% set maintenance = get_setting('maintenance_mode', 'false') == 'true' %}
    {% if maintenance and (session.user_type != 'super' and session.user_type != 'admin') %}
    <div class="maintenance-banner">🔧 GoldenVow is currently under maintenance. Please check back later.</div>
    {% endif %}
    <nav class="navbar navbar-expand-lg navbar-gold">
        <div class="container">
            <a class="navbar-brand" href="{{ url_for('landing') }}"><i class="bi bi-award"></i> GoldenVow</a>
            <button class="navbar-toggler" type="button" data-bs-toggle="collapse" data-bs-target="#navMenu">
                <span class="navbar-toggler-icon"></span>
            </button>
            <div class="collapse navbar-collapse" id="navMenu">
                <ul class="navbar-nav ms-auto">
                    {% if session.user_type %}
                        <li class="nav-item"><a class="nav-link" href="{{ url_for('dashboard_redirect') }}"><i class="bi bi-speedometer2"></i> Dashboard</a></li>
                        <li class="nav-item"><a class="nav-link" href="{{ url_for('logout') }}"><i class="bi bi-box-arrow-right"></i> Logout</a></li>
                    {% else %}
                        <li class="nav-item"><a class="nav-link" href="{{ url_for('login') }}"><i class="bi bi-box-arrow-in-right"></i> Login</a></li>
                        <li class="nav-item"><a class="nav-link" href="{{ url_for('register') }}"><i class="bi bi-person-plus"></i> Register</a></li>
                    {% endif %}
                    <li class="nav-item"><a class="nav-link" href="{{ url_for('help_page') }}"><i class="bi bi-question-circle"></i> Help</a></li>
                    <li class="nav-item"><a class="nav-link" href="{{ url_for('contact') }}"><i class="bi bi-envelope"></i> Contact</a></li>
                </ul>
            </div>
        </div>
    </nav>
    <div class="container mt-3">
        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
                {% for category, message in messages %}
                    <div class="alert alert-{{ category if category != 'message' else 'info' }} alert-dismissible fade show">
                        {{ message }}
                        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
                    </div>
                {% endfor %}
            {% endif %}
        {% endwith %}
    </div>
    <main>
        {# Back button - visible on all pages except landing, login, admin_login, register, intro #}
        {% if request.endpoint not in ['landing', 'login', 'admin_login', 'register', 'intro'] %}
        <div class="container mt-2">
            <button onclick="history.back()" class="btn btn-outline-gold btn-sm">
                <i class="bi bi-arrow-left"></i> Back
            </button>
        </div>
        {% endif %}
        {% block content %}{% endblock %}
    </main>
    <footer class="footer">
        <div class="container text-center">
            <p class="mb-0">&copy; 2026 GoldenVow – Fundraising with Integrity. <br>
            <a href="{{ url_for('help_page') }}">Help</a> | <a href="{{ url_for('contact') }}">Contact</a></p>
        </div>
    </footer>
    <a href="https://wa.me/{{ get_setting('support_whatsapp', '254700000000') }}" class="whatsapp-float" target="_blank">
        <i class="bi bi-whatsapp"></i> Chat
    </a>
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0-alpha1/dist/js/bootstrap.bundle.min.js"></script>
    <script src="https://cdn.socket.io/4.5.4/socket.io.min.js"></script>
    {% block extra_js %}{% endblock %}
</body>
</html>
"""

class StringLoader(BaseLoader):
    def get_source(self, environment, template):
        if template == 'base.html':
            return BASE_TEMPLATE, None, lambda: True
        raise TemplateNotFound(template)

app.jinja_env.loader = StringLoader()
app.jinja_env.globals['get_setting'] = get_setting
app.jinja_env.globals['unread_notifications'] = get_unread_notifications

# -------------------- ROUTES --------------------

@app.route('/intro')
def intro():
    if session.get('seen_intro'):
        return redirect(url_for('landing'))
    session['seen_intro'] = True
    return render_template_string("""
{% extends 'base.html' %}
{% block title %}Welcome to GoldenVow{% endblock %}
{% block content %}
<div class="intro-container">
    <div class="gold-sparkle"></div>
    <div style="position:relative; z-index:1;">
        <h1 class="intro-title"><i class="bi bi-award"></i> GoldenVow</h1>
        <p class="intro-sub">Transforming communities, one vow at a time.</p>
        <a href="{{ url_for('landing') }}" class="intro-btn">Enter Site <i class="bi bi-arrow-right"></i></a>
    </div>
</div>
<script>
    window.addEventListener('load', function() {
        var msg = new SpeechSynthesisUtterance("Welcome to Golden Vow, transforming the community.");
        msg.rate = 1.0; msg.pitch = 0.8; msg.volume = 1; msg.lang = 'en-US';
        var voices = window.speechSynthesis.getVoices();
        var maleVoice = voices.find(v => v.name.includes('Male') || v.name.includes('Google UK') || v.name.includes('Samantha'));
        if (maleVoice) msg.voice = maleVoice;
        window.speechSynthesis.speak(msg);
    });
</script>
{% endblock %}
""")

@app.route('/')
def landing():
    if not session.get('seen_intro'):
        return redirect(url_for('intro'))
    events = Event.query.filter_by(is_locked=False).order_by(Event.created_at.desc()).limit(9).all()
    testimonials = Testimonial.query.filter_by(is_approved=True).order_by(Testimonial.created_at.desc()).limit(6).all()
    return render_template_string("""
{% extends 'base.html' %}
{% block content %}
<div class="hero-section text-center py-5" style="margin-bottom:30px;">
    <div class="container">
        <h1 class="display-3 fw-bold"><i class="bi bi-award"></i> GoldenVow</h1>
        <p class="lead">Empowering communities through transparent fundraising for dowry, burial, medical, education & harambee.</p>
        <a href="{{ url_for('login') }}" class="btn btn-gold btn-lg mt-3"><i class="bi bi-box-arrow-in-right"></i> Get Started</a>
    </div>
</div>
<div class="container my-5">
    <h2 class="text-center mb-4">Featured Events</h2>
    <div class="row g-4">
        {% for event in events %}
        <div class="col-md-4">
            <div class="card glass-card h-100">
                <div class="card-body">
                    <h5 class="card-title">{{ event.title }}</h5>
                    <p class="text-muted small">{{ event.category.capitalize() }}</p>
                    <div class="progress mb-2" style="height:8px; background: rgba(255,255,255,0.1);">
                        <div class="progress-bar bg-warning" style="width:{{ (event.raised_amount/event.target_amount*100)|round|int if event.target_amount>0 else 0 }}%;"></div>
                    </div>
                    <p class="card-text">Raised: KES {{ "%.2f"|format(event.raised_amount) }} / {{ "%.2f"|format(event.target_amount) }}</p>
                    <a href="{{ url_for('event_landing', event_token=event.event_token) }}" class="btn btn-outline-gold btn-sm">View</a>
                </div>
            </div>
        </div>
        {% endfor %}
    </div>
</div>
<div class="container my-5">
    <h2 class="text-center mb-4">What Our Community Says</h2>
    <div class="row g-4">
        {% for t in testimonials %}
        <div class="col-md-4">
            <div class="card glass-card h-100">
                <div class="card-body">
                    <p><i class="bi bi-quote"></i> {{ t.content }}</p>
                    <footer class="blockquote-footer">{{ t.name }} <span class="text-warning">{% for i in range(t.rating) %}★{% endfor %}</span></footer>
                </div>
            </div>
        </div>
        {% endfor %}
    </div>
</div>
{% endblock %}
""", events=events, testimonials=testimonials)

# ---------- FIX LOGIN ROUTE ----------
@app.route('/fix_login')
def fix_login():
    admin = Admin.query.filter_by(username='super').first()
    if not admin:
        return "Super admin not found. Visit /create_super_admin first."
    admin.password_hash = hash_password('super123')
    db.session.commit()
    return "✅ Super admin password reset to 'super123'. Now login at /login"

# ---------- FORGOT PASSWORD ----------
@app.route('/forgot_password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email')
        if not email:
            flash('Please enter your email.', 'danger')
            return redirect(url_for('forgot_password'))
        admin = Admin.query.filter_by(email=email).first()
        if admin:
            token = generate_token()
            reset = PasswordReset(email=email, token=token, expires_at=datetime.utcnow() + timedelta(hours=1), user_type='admin')
            db.session.add(reset)
            db.session.commit()
            send_reset_email(email, token, 'admin')
            flash('Password reset link sent to your email.', 'success')
            return redirect(url_for('login'))
        contributor = Contributor.query.filter_by(email=email).first()
        if contributor:
            token = generate_token()
            reset = PasswordReset(email=email, token=token, expires_at=datetime.utcnow() + timedelta(hours=1), user_type='contributor')
            db.session.add(reset)
            db.session.commit()
            send_reset_email(email, token, 'contributor')
            flash('Password reset link sent to your email.', 'success')
            return redirect(url_for('login'))
        flash('No account found with that email.', 'danger')
    return render_template_string("""
{% extends 'base.html' %}
{% block content %}
<div class="row justify-content-center mt-5">
    <div class="col-md-5">
        <div class="card glass-card">
            <div class="card-header"><h4>Forgot Password</h4></div>
            <div class="card-body">
                <p>Enter your email address and we'll send you a link to reset your password.</p>
                <form method="post">
                    <div class="mb-3"><label>Email</label><input type="email" name="email" class="form-control" required></div>
                    <button type="submit" class="btn btn-gold w-100">Send Reset Link</button>
                </form>
                <p class="mt-2"><a href="{{ url_for('login') }}">Back to Login</a></p>
            </div>
        </div>
    </div>
</div>
{% endblock %}
""")

def send_reset_email(email, token, user_type):
    reset_link = url_for('reset_password', token=token, _external=True)
    subject = "Reset your GoldenVow password"
    html = f"""
    <h2>Password Reset</h2>
    <p>You requested to reset your password for your {user_type} account.</p>
    <p>Click the link below to set a new password:</p>
    <p><a href="{reset_link}">{reset_link}</a></p>
    <p>This link expires in 1 hour.</p>
    <p>If you didn't request this, ignore this email.</p>
    """
    return send_email(email, subject, html)

@app.route('/reset_password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    reset = PasswordReset.query.filter_by(token=token, used=False).first()
    if not reset or reset.expires_at < datetime.utcnow():
        flash('Invalid or expired reset link.', 'danger')
        return redirect(url_for('forgot_password'))
    if request.method == 'POST':
        password = request.form.get('password')
        confirm = request.form.get('confirm_password')
        if password != confirm:
            flash('Passwords do not match.', 'danger')
            return redirect(url_for('reset_password', token=token))
        hashed = hash_password(password)
        if reset.user_type == 'admin':
            admin = Admin.query.filter_by(email=reset.email).first()
            if admin:
                admin.password_hash = hashed
                db.session.commit()
                reset.used = True
                db.session.commit()
                flash('Password reset successful. Please login.', 'success')
                return redirect(url_for('login'))
        elif reset.user_type == 'contributor':
            contributor = Contributor.query.filter_by(email=reset.email).first()
            if contributor:
                contributor.password_hash = hashed
                db.session.commit()
                reset.used = True
                db.session.commit()
                flash('Password reset successful. Please login.', 'success')
                return redirect(url_for('login'))
        flash('Account not found.', 'danger')
        return redirect(url_for('login'))
    return render_template_string("""
{% extends 'base.html' %}
{% block content %}
<div class="row justify-content-center mt-5">
    <div class="col-md-5">
        <div class="card glass-card">
            <div class="card-header"><h4>Reset Password</h4></div>
            <div class="card-body">
                <form method="post">
                    <div class="mb-3"><label>New Password</label><input type="password" name="password" class="form-control" required></div>
                    <div class="mb-3"><label>Confirm Password</label><input type="password" name="confirm_password" class="form-control" required></div>
                    <button type="submit" class="btn btn-gold w-100">Reset Password</button>
                </form>
            </div>
        </div>
    </div>
</div>
{% endblock %}
""")

# ---------- SUPER ADMIN CREATION ----------
@app.route('/create_super_admin')
def create_super_admin():
    if Admin.query.filter_by(is_super_admin=True).first():
        return "Super admin already exists. Login with default credentials: super / super123"
    admin = Admin(
        username='super',
        email='super@goldenvow.com',
        password_hash=hash_password('super123'),
        is_super_admin=True,
        is_active=True
    )
    db.session.add(admin)
    db.session.commit()
    return "Super admin created! Login: super / super123"

# ---------- REGISTER ----------
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        full_name = request.form['full_name']
        email = request.form['email']
        phone = request.form['phone']
        password = request.form['password']
        confirm = request.form['confirm_password']
        if password != confirm:
            flash('Passwords do not match.', 'danger')
            return redirect(url_for('register'))
        existing = Contributor.query.filter_by(email=email).first()
        if existing:
            flash('Email already registered. Please login.', 'warning')
            return redirect(url_for('login'))
        general_event = Event.query.filter_by(title='General Fund').first()
        if not general_event:
            admin = Admin.query.first()
            if not admin:
                flash('No admin exists. Please contact support.', 'danger')
                return redirect(url_for('register'))
            general_event = Event(
                title='General Fund',
                description='Default event for registered contributors.',
                category='harambee',
                target_amount=1000000,
                admin_id=admin.id,
                event_token=generate_token()
            )
            db.session.add(general_event)
            db.session.commit()
        hashed = hash_password(password)
        contributor = Contributor(
            full_name=full_name,
            email=email,
            phone=phone,
            password_hash=hashed,
            event_id=general_event.id,
            pledge_amount=0.0
        )
        db.session.add(contributor)
        db.session.commit()
        flash('Registration successful! Please login.', 'success')
        return redirect(url_for('login'))
    return render_template_string("""
{% extends 'base.html' %}
{% block content %}
<div class="row justify-content-center mt-5">
    <div class="col-md-5">
        <div class="card glass-card">
            <div class="card-header"><h4>Register as Contributor</h4></div>
            <div class="card-body">
                <form method="post">
                    <div class="mb-3"><label>Full Name</label><input type="text" name="full_name" class="form-control" required></div>
                    <div class="mb-3"><label>Email</label><input type="email" name="email" class="form-control" required></div>
                    <div class="mb-3"><label>Phone</label><input type="text" name="phone" class="form-control" required></div>
                    <div class="mb-3"><label>Password</label><input type="password" name="password" class="form-control" required></div>
                    <div class="mb-3"><label>Confirm Password</label><input type="password" name="confirm_password" class="form-control" required></div>
                    <button type="submit" class="btn btn-gold w-100">Register</button>
                </form>
                <p class="mt-2">Already have an account? <a href="{{ url_for('login') }}">Login</a></p>
            </div>
        </div>
    </div>
</div>
{% endblock %}
""")

# ---------- LOGIN ----------
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        admin = Admin.query.filter_by(username=username).first()
        if admin and check_password(password, admin.password_hash):
            if not admin.is_active:
                flash('Account disabled.', 'danger')
                return redirect(url_for('login'))
            session.permanent = True
            session['user_id'] = admin.id
            session['user_type'] = 'super' if admin.is_super_admin else 'admin'
            session['username'] = admin.username
            return redirect(url_for('dashboard_redirect'))
        contributor = Contributor.query.filter_by(email=username).first()
        if contributor:
            if contributor.password_hash and check_password(password, contributor.password_hash):
                session.permanent = True
                session['user_id'] = contributor.id
                session['user_type'] = 'contributor'
                session['username'] = contributor.full_name
                return redirect(url_for('dashboard_redirect'))
            elif not contributor.password_hash and password == contributor.phone:
                contributor.password_hash = hash_password(password)
                db.session.commit()
                session.permanent = True
                session['user_id'] = contributor.id
                session['user_type'] = 'contributor'
                session['username'] = contributor.full_name
                return redirect(url_for('dashboard_redirect'))
        flash('Invalid credentials.', 'danger')
    return render_template_string("""
{% extends 'base.html' %}
{% block content %}
<div class="row justify-content-center mt-5">
    <div class="col-md-4">
        <div class="card glass-card">
            <div class="card-header"><h4>Login</h4></div>
            <div class="card-body">
                <form method="post">
                    <div class="mb-3"><label>Username / Email</label><input type="text" name="username" class="form-control" required></div>
                    <div class="mb-3"><label>Password</label><input type="password" name="password" class="form-control" required></div>
                    <button type="submit" class="btn btn-gold w-100">Login</button>
                </form>
                <hr>
                <p class="small"><a href="{{ url_for('forgot_password') }}">Forgot Password?</a></p>
                <p class="small">Admin? <a href="{{ url_for('admin_login') }}">Admin Login</a></p>
                <p class="small">New user? <a href="{{ url_for('register') }}">Register</a></p>
            </div>
        </div>
    </div>
</div>
{% endblock %}
""")

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        admin = Admin.query.filter_by(username=username).first()
        if admin and check_password(password, admin.password_hash) and admin.is_active:
            session.permanent = True
            session['user_id'] = admin.id
            session['user_type'] = 'super' if admin.is_super_admin else 'admin'
            session['username'] = admin.username
            return redirect(url_for('dashboard_redirect'))
        flash('Invalid admin credentials.', 'danger')
    return render_template_string("""
{% extends 'base.html' %}
{% block content %}
<div class="row justify-content-center mt-5">
    <div class="col-md-4">
        <div class="card glass-card">
            <div class="card-header"><h4>Admin Login</h4></div>
            <div class="card-body">
                <form method="post">
                    <div class="mb-3"><label>Username</label><input type="text" name="username" class="form-control" required></div>
                    <div class="mb-3"><label>Password</label><input type="password" name="password" class="form-control" required></div>
                    <button type="submit" class="btn btn-gold w-100">Login</button>
                </form>
                <p class="mt-2"><a href="{{ url_for('forgot_password') }}">Forgot Password?</a></p>
                <p class="mt-2"><a href="{{ url_for('login') }}">Contributor login</a></p>
            </div>
        </div>
    </div>
</div>
{% endblock %}
""")

@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out.', 'info')
    return redirect(url_for('landing'))

@app.route('/dashboard')
def dashboard_redirect():
    if session.get('user_type') in ['admin', 'super']:
        return redirect(url_for('admin_dashboard'))
    elif session.get('user_type') == 'contributor':
        return redirect(url_for('contributor_dashboard'))
    return redirect(url_for('login'))

# ---------- ADMIN DASHBOARD ----------
@app.route('/admin/dashboard')
@admin_required
def admin_dashboard():
    admin = Admin.query.get(session['user_id'])
    events = Event.query.filter_by(admin_id=admin.id).all()
    pending_payments = Payment.query.filter_by(status='pending').join(Event).filter(Event.admin_id==admin.id).count()
    total_raised = sum(e.raised_amount for e in events)
    return render_template_string("""
{% extends 'base.html' %}
{% block content %}
<div class="row">
    <div class="col-md-3 admin-sidebar">
        <h5>Welcome, {{ session.username }}</h5>
        <ul class="nav flex-column">
            <li class="nav-item"><a class="nav-link active" href="{{ url_for('admin_dashboard') }}"><i class="bi bi-speedometer2"></i> Dashboard</a></li>
            <li class="nav-item"><a class="nav-link" href="{{ url_for('create_event') }}"><i class="bi bi-plus-circle"></i> Create Event</a></li>
            <li class="nav-item"><a class="nav-link" href="{{ url_for('public_chat') }}"><i class="bi bi-chat-dots"></i> Public Chat</a></li>
            <li class="nav-item"><a class="nav-link" href="{{ url_for('contact') }}"><i class="bi bi-envelope"></i> Contact</a></li>
            <li class="nav-item"><a class="nav-link" href="{{ url_for('feature_request') }}"><i class="bi bi-lightbulb"></i> Feature Requests</a></li>
            {% if session.user_type == 'super' %}
            <li class="nav-item"><a class="nav-link" href="{{ url_for('super_dashboard') }}"><i class="bi bi-shield-lock"></i> Super Admin</a></li>
            {% endif %}
        </ul>
    </div>
    <div class="col-md-9">
        <h3>Dashboard</h3>
        <div class="row g-3 mb-4">
            <div class="col-md-4"><div class="card glass-card p-3"><h5>Total Events</h5><h2>{{ events|length }}</h2></div></div>
            <div class="col-md-4"><div class="card glass-card p-3"><h5>Pending Payments</h5><h2>{{ pending_payments }}</h2></div></div>
            <div class="col-md-4"><div class="card glass-card p-3"><h5>Total Raised</h5><h2>KES {{ "%.2f"|format(total_raised) }}</h2></div></div>
        </div>
        <h4>My Events</h4>
        <div class="row">
            {% for event in events %}
            <div class="col-md-4 mb-3">
                <div class="card glass-card h-100">
                    <div class="card-body">
                        <h5>{{ event.title }}</h5>
                        <p class="small">Status: {% if event.is_locked %}<span class="badge bg-danger">Locked</span>{% else %}<span class="badge bg-success">Active</span>{% endif %}</p>
                        <p>Raised: KES {{ "%.2f"|format(event.raised_amount) }} / {{ "%.2f"|format(event.target_amount) }}</p>
                        <a href="{{ url_for('manage_event', event_id=event.id) }}" class="btn btn-gold btn-sm">Manage</a>
                        <a href="{{ url_for('event_landing', event_token=event.event_token) }}" class="btn btn-outline-gold btn-sm">View</a>
                    </div>
                </div>
            </div>
            {% endfor %}
        </div>
    </div>
</div>
{% endblock %}
""", events=events, pending_payments=pending_payments, total_raised=total_raised)

@app.route('/admin/create_event', methods=['GET', 'POST'])
@admin_required
def create_event():
    if request.method == 'POST':
        title = request.form['title']
        desc = request.form['description']
        category = request.form['category']
        target = float(request.form['target_amount'])
        deadline = request.form.get('deadline')
        admin = Admin.query.get(session['user_id'])
        token = generate_token()
        event = Event(
            title=title, description=desc, category=category,
            target_amount=target, admin_id=admin.id, event_token=token,
            deadline=datetime.strptime(deadline, '%Y-%m-%d') if deadline else None
        )
        db.session.add(event)
        db.session.commit()
        flash('Event created successfully!', 'success')
        return redirect(url_for('admin_dashboard'))
    return render_template_string("""
{% extends 'base.html' %}
{% block content %}
<div class="row justify-content-center mt-4">
    <div class="col-md-6">
        <div class="card glass-card">
            <div class="card-header"><h4>Create Event</h4></div>
            <div class="card-body">
                <form method="post">
                    <div class="mb-3"><label>Title</label><input type="text" name="title" class="form-control" required></div>
                    <div class="mb-3"><label>Description</label><textarea name="description" class="form-control" rows="3"></textarea></div>
                    <div class="mb-3">
                        <label>Category</label>
                        <select name="category" class="form-select">
                            <option value="dowry">Dowry</option>
                            <option value="burial">Burial</option>
                            <option value="medical">Medical</option>
                            <option value="education">Education</option>
                            <option value="harambee">Harambee</option>
                        </select>
                    </div>
                    <div class="mb-3"><label>Target Amount (KES)</label><input type="number" step="0.01" name="target_amount" class="form-control" required></div>
                    <div class="mb-3"><label>Deadline (optional)</label><input type="date" name="deadline" class="form-control"></div>
                    <button type="submit" class="btn btn-gold w-100">Create Event</button>
                </form>
            </div>
        </div>
    </div>
</div>
{% endblock %}
""")

@app.route('/admin/event/<int:event_id>/manage')
@admin_required
def manage_event(event_id):
    event = Event.query.get_or_404(event_id)
    if event.admin_id != session['user_id'] and session.get('user_type') != 'super':
        abort(403)
    payments = Payment.query.filter_by(event_id=event.id).order_by(Payment.created_at.desc()).all()
    contributors = Contributor.query.filter_by(event_id=event.id).all()
    return render_template_string("""
{% extends 'base.html' %}
{% block content %}
<h3>Manage: {{ event.title }}</h3>
<div class="row">
    <div class="col-md-8">
        <h5>Payments</h5>
        <div class="table-responsive">
            <table class="table table-bordered">
                <thead><tr><th>Contributor</th><th>Amount</th><th>Sender</th><th>Status</th><th>Actions</th></tr></thead>
                <tbody>
                {% for p in payments %}
                <tr>
                    <td>{{ p.contributor.full_name }}</td>
                    <td>KES {{ "%.2f"|format(p.amount) }}</td>
                    <td>{{ p.sender_name }}</td>
                    <td><span class="badge bg-{% if p.status=='pending' %}warning{% elif p.status=='approved' %}success{% else %}danger{% endif %}">{{ p.status }}</span></td>
                    <td>
                        {% if p.status == 'pending' %}
                        <a href="{{ url_for('approve_payment', payment_id=p.id) }}" class="btn btn-sm btn-success">Approve</a>
                        <a href="{{ url_for('decline_payment', payment_id=p.id) }}" class="btn btn-sm btn-danger">Decline</a>
                        {% endif %}
                        <a href="{{ url_for('generate_receipt', payment_id=p.id) }}" class="btn btn-sm btn-outline-gold">Receipt</a>
                    </td>
                </tr>
                {% endfor %}
                </tbody>
            </table>
        </div>
    </div>
    <div class="col-md-4">
        <h5>Contributors</h5>
        <ul class="list-group">
            {% for c in contributors %}
            <li class="list-group-item">{{ c.full_name }} - KES {{ "%.2f"|format(c.pledge_amount) }}</li>
            {% endfor %}
        </ul>
        <hr>
        <a href="{{ url_for('event_landing', event_token=event.event_token) }}" class="btn btn-gold w-100">View Public Page</a>
    </div>
</div>
{% endblock %}
""", event=event, payments=payments, contributors=contributors)

@app.route('/admin/payment/<int:payment_id>/approve')
@admin_required
def approve_payment(payment_id):
    payment = Payment.query.get_or_404(payment_id)
    event = payment.event
    if event.admin_id != session['user_id'] and session.get('user_type') != 'super':
        abort(403)
    payment.status = 'approved'
    payment.approved_at = datetime.utcnow()
    event.raised_amount = (event.raised_amount or 0) + payment.amount
    referral_discount = payment.contributor.referral_discount or 0
    fee = calculate_fee(payment.amount, referral_discount)
    payment.fee_deducted = fee
    db.session.commit()
    create_notification('contributor', payment.contributor_id, f'Your payment of KES {payment.amount} for {event.title} has been approved!')
    flash('Payment approved.', 'success')
    return redirect(url_for('manage_event', event_id=event.id))

@app.route('/admin/payment/<int:payment_id>/decline')
@admin_required
def decline_payment(payment_id):
    payment = Payment.query.get_or_404(payment_id)
    event = payment.event
    if event.admin_id != session['user_id'] and session.get('user_type') != 'super':
        abort(403)
    payment.status = 'declined'
    db.session.commit()
    create_notification('contributor', payment.contributor_id, f'Your payment of KES {payment.amount} for {event.title} was declined.')
    flash('Payment declined.', 'warning')
    return redirect(url_for('manage_event', event_id=event.id))

def calculate_fee(amount, referral_discount=0.0):
    fee_percentage = float(get_setting('service_fee_percentage', '2.0'))
    fee = amount * (fee_percentage / 100.0)
    discount = fee * (referral_discount / 100.0) if referral_discount > 0 else 0
    return max(0, fee - discount)

@app.route('/receipt/<int:payment_id>')
def generate_receipt(payment_id):
    payment = Payment.query.get_or_404(payment_id)
    if session.get('user_type') in ['admin', 'super']:
        pass
    elif session.get('user_type') == 'contributor' and session['user_id'] == payment.contributor_id:
        if (datetime.utcnow() - payment.created_at).days < 7:
            flash('Receipt available after 7 days.', 'warning')
            return redirect(url_for('contributor_dashboard'))
    else:
        flash('Access denied.', 'danger')
        return redirect(url_for('login'))
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    # Watermark
    c.saveState()
    c.setFillColorRGB(0.9, 0.9, 0.9, alpha=0.2)
    c.setFont("Helvetica-Bold", 60)
    c.rotate(45)
    c.drawString(200, -100, "GoldenVow")
    c.restoreState()
    # Content
    c.setFont("Helvetica-Bold", 16)
    c.drawString(200, 750, "GOLDENVOW RECEIPT")
    c.setFont("Helvetica", 12)
    y = 700
    c.drawString(50, y, f"Receipt #: {payment.id}")
    y -= 30
    c.drawString(50, y, f"Event: {payment.event.title}")
    y -= 25
    c.drawString(50, y, f"Contributor: {payment.contributor.full_name}")
    y -= 25
    c.drawString(50, y, f"Amount: KES {payment.amount:.2f}")
    y -= 25
    c.drawString(50, y, f"Fee Deducted: KES {payment.fee_deducted:.2f}")
    y -= 25
    c.drawString(50, y, f"Date: {payment.created_at.strftime('%Y-%m-%d %H:%M')}")
    y -= 25
    c.drawString(50, y, f"Status: {payment.status.upper()}")
    c.save()
    buffer.seek(0)
    return send_file(buffer, as_attachment=True, download_name=f'receipt_{payment.id}.pdf', mimetype='application/pdf')

# ---------- CONTRIBUTOR ROUTES ----------
@app.route('/event/<event_token>')
def event_landing(event_token):
    event = Event.query.filter_by(event_token=event_token).first_or_404()
    if event.is_locked:
        flash('This event is currently locked due to unpaid fees.', 'warning')
    contributors = Contributor.query.filter_by(event_id=event.id).all()
    testimonials = Testimonial.query.filter_by(is_approved=True).order_by(db.func.random()).limit(3).all()
    return render_template_string("""
{% extends 'base.html' %}
{% block content %}
<div class="row">
    <div class="col-md-8">
        <h2>{{ event.title }}</h2>
        <p><span class="badge bg-secondary">{{ event.category.capitalize() }}</span></p>
        <p>{{ event.description }}</p>
        <div class="progress mb-3" style="height:20px; background: rgba(255,255,255,0.1);">
            <div class="progress-bar bg-warning" style="width:{{ (event.raised_amount/event.target_amount*100)|round|int if event.target_amount>0 else 0 }}%;">
                {{ "%.0f"|format((event.raised_amount/event.target_amount*100)|round|int if event.target_amount>0 else 0) }}%
            </div>
        </div>
        <p><strong>Raised:</strong> KES {{ "%.2f"|format(event.raised_amount) }} / {{ "%.2f"|format(event.target_amount) }}</p>
        {% if event.deadline %}<p><strong>Deadline:</strong> {{ event.deadline.strftime('%Y-%m-%d') }}</p>{% endif %}
        <div class="card glass-card mt-3">
            <div class="card-body">
                <h5>Contribute Now</h5>
                <form action="{{ url_for('contributor_register', event_token=event.event_token) }}" method="post">
                    <div class="mb-2"><input type="text" name="full_name" placeholder="Full Name" class="form-control" required></div>
                    <div class="mb-2"><input type="email" name="email" placeholder="Email" class="form-control" required></div>
                    <div class="mb-2"><input type="text" name="phone" placeholder="Phone" class="form-control" required></div>
                    <div class="mb-2"><input type="number" step="0.01" name="pledge_amount" placeholder="Pledge Amount (KES)" class="form-control" required></div>
                    <div class="mb-2"><input type="text" name="sender_name" placeholder="M-PESA Sender Name (for verification)" class="form-control"></div>
                    <div class="mb-2"><input type="text" name="referred_by" placeholder="Referred By (optional)" class="form-control"></div>
                    <div class="mb-2"><input type="password" name="password" placeholder="Create Password" class="form-control" required></div>
                    <div class="mb-2"><input type="password" name="confirm_password" placeholder="Confirm Password" class="form-control" required></div>
                    <button type="submit" class="btn btn-gold w-100">Submit Pledge</button>
                </form>
            </div>
        </div>
    </div>
    <div class="col-md-4">
        <div class="card glass-card">
            <div class="card-body">
                <h5>Contributors</h5>
                <ul class="list-group list-group-flush">
                {% for c in contributors %}
                    <li class="list-group-item">{{ c.full_name }} - KES {{ "%.2f"|format(c.pledge_amount) }}</li>
                {% endfor %}
                </ul>
            </div>
        </div>
        <div class="card glass-card mt-3">
            <div class="card-body">
                <h5>Recent Testimonials</h5>
                {% for t in testimonials %}
                    <blockquote class="small">"{{ t.content }}" - {{ t.name }}</blockquote>
                {% endfor %}
            </div>
        </div>
    </div>
</div>
{% endblock %}
""", event=event, contributors=contributors, testimonials=testimonials)

@app.route('/contributor/register/<event_token>', methods=['POST'])
def contributor_register(event_token):
    event = Event.query.filter_by(event_token=event_token).first_or_404()
    if event.is_locked:
        flash('Event is locked.', 'danger')
        return redirect(url_for('event_landing', event_token=event_token))
    full_name = request.form['full_name']
    email = request.form['email']
    phone = request.form.get('phone')
    pledge = float(request.form['pledge_amount'])
    sender = request.form.get('sender_name')
    referred = request.form.get('referred_by')
    password = request.form['password']
    confirm = request.form['confirm_password']
    if password != confirm:
        flash('Passwords do not match.', 'danger')
        return redirect(url_for('event_landing', event_token=event_token))
    hashed = hash_password(password)
    contributor = Contributor(
        full_name=full_name, email=email, phone=phone,
        event_id=event.id, pledge_amount=pledge,
        sender_name=sender, referred_by=referred,
        password_hash=hashed
    )
    db.session.add(contributor)
    db.session.commit()
    payment = Payment(
        event_id=event.id, contributor_id=contributor.id,
        amount=pledge, sender_name=sender or full_name,
        status='pending'
    )
    db.session.add(payment)
    db.session.commit()
    flash('Pledge submitted! Please upload payment proof.', 'success')
    return redirect(url_for('upload_proof', event_token=event_token, contributor_id=contributor.id))

@app.route('/contributor/upload/<event_token>/<int:contributor_id>', methods=['GET', 'POST'])
def upload_proof(event_token, contributor_id):
    event = Event.query.filter_by(event_token=event_token).first_or_404()
    contributor = Contributor.query.get_or_404(contributor_id)
    if request.method == 'POST':
        proof_text = request.form.get('proof_text', 'Payment sent via M-PESA')
        sender = request.form.get('sender_name', contributor.sender_name)
        payment = Payment.query.filter_by(contributor_id=contributor.id, event_id=event.id, status='pending').first()
        if payment:
            payment.sender_name = sender
            payment.proof_image = proof_text
            if sender and contributor.sender_name and sender.lower() == contributor.sender_name.lower():
                payment.status = 'approved'
                payment.approved_at = datetime.utcnow()
                event.raised_amount = (event.raised_amount or 0) + payment.amount
                fee = calculate_fee(payment.amount, contributor.referral_discount or 0)
                payment.fee_deducted = fee
                flash('Payment auto-verified and approved!', 'success')
            else:
                flash('Proof uploaded. Awaiting admin verification.', 'info')
            db.session.commit()
            check_event_lock(event)
        return redirect(url_for('event_landing', event_token=event_token))
    return render_template_string("""
{% extends 'base.html' %}
{% block content %}
<div class="row justify-content-center mt-4">
    <div class="col-md-5">
        <div class="card glass-card">
            <div class="card-body">
                <h4>Upload Payment Proof</h4>
                <p>Event: {{ event.title }}</p>
                <p>Contributor: {{ contributor.full_name }}</p>
                <form method="post">
                    <div class="mb-2"><label>Sender Name (as on M-PESA)</label>
                        <input type="text" name="sender_name" class="form-control" value="{{ contributor.sender_name or '' }}"></div>
                    <div class="mb-2"><label>Proof details / Transaction code</label>
                        <textarea name="proof_text" class="form-control" rows="3"></textarea></div>
                    <button type="submit" class="btn btn-gold w-100">Submit Proof</button>
                </form>
            </div>
        </div>
    </div>
</div>
{% endblock %}
""", event=event, contributor=contributor)

@app.route('/contributor/dashboard')
@login_required
def contributor_dashboard():
    if session.get('user_type') != 'contributor':
        return redirect(url_for('login'))
    contributor = Contributor.query.get(session['user_id'])
    payments = Payment.query.filter_by(contributor_id=contributor.id).all()
    return render_template_string("""
{% extends 'base.html' %}
{% block content %}
<h3>My Dashboard</h3>
<p>Welcome, {{ contributor.full_name }}</p>
<div class="row">
    <div class="col-md-6">
        <h5>Your Payments</h5>
        <ul class="list-group">
            {% for p in payments %}
            <li class="list-group-item d-flex justify-content-between">
                {{ p.event.title }} - KES {{ "%.2f"|format(p.amount) }}
                <span class="badge bg-{% if p.status=='pending' %}warning{% elif p.status=='approved' %}success{% else %}danger{% endif %}">{{ p.status }}</span>
            </li>
            {% endfor %}
        </ul>
    </div>
    <div class="col-md-6">
        <a href="{{ url_for('public_chat') }}" class="btn btn-gold w-100 mb-2">Public Chat</a>
        <a href="{{ url_for('feature_request') }}" class="btn btn-outline-gold w-100">Suggest a Feature</a>
    </div>
</div>
{% endblock %}
""", contributor=contributor, payments=payments)

# ---------- CHAT ----------
@app.route('/chat')
def public_chat():
    messages = ChatMessage.query.order_by(ChatMessage.timestamp.desc()).limit(50).all()[::-1]
    return render_template_string("""
{% extends 'base.html' %}
{% block content %}
<h3>Public Chat</h3>
<div class="chat-container" id="chatBox">
    {% for msg in messages %}
    <div class="chat-msg {{ msg.sender_type }}">
        <strong>{{ msg.sender_name or msg.sender_type }}</strong><br>
        {{ msg.message }}
        <span class="small text-muted">{{ msg.timestamp.strftime('%H:%M') }}</span>
    </div>
    {% endfor %}
</div>
<div class="mt-3">
    <input type="text" id="chatInput" class="form-control" placeholder="Type your message...">
    <button class="btn btn-gold mt-2" id="sendChat">Send</button>
</div>
{% endblock %}
{% block extra_js %}
<script>
    var socket = io();
    var room = 'public';
    var userType = '{{ session.user_type or "guest" }}';
    var userName = '{{ session.username or "Guest" }}';

    socket.emit('join', {room: room});
    document.getElementById('sendChat').addEventListener('click', function() {
        var msg = document.getElementById('chatInput').value;
        if(msg) {
            socket.emit('chat_message', {room: room, message: msg, sender_type: userType, sender_name: userName});
            document.getElementById('chatInput').value = '';
        }
    });
    socket.on('message', function(data) {
        var box = document.getElementById('chatBox');
        var div = document.createElement('div');
        div.className = 'chat-msg ' + data.sender_type;
        div.innerHTML = '<strong>' + (data.sender_name || data.sender_type) + '</strong><br>' + data.message;
        box.appendChild(div);
        box.scrollTop = box.scrollHeight;
    });
</script>
{% endblock %}
""", messages=messages)

@socketio.on('join')
def handle_join(data):
    join_room(data['room'])

@socketio.on('chat_message')
def handle_chat_message(data):
    msg = ChatMessage(
        sender_type=data['sender_type'],
        sender_id=session.get('user_id', 0),
        sender_name=data.get('sender_name', 'Guest'),
        message=data['message'],
        room=data['room']
    )
    db.session.add(msg)
    db.session.commit()
    emit('message', {'sender_type': data['sender_type'], 'sender_name': data.get('sender_name'), 'message': data['message']}, room=data['room'])

# ---------- CONTACT, HELP, FEATURE ----------
@app.route('/contact', methods=['GET', 'POST'])
def contact():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        subject = request.form.get('subject', '')
        message = request.form['message']
        contact = ContactMessage(name=name, email=email, subject=subject, message=message)
        db.session.add(contact)
        db.session.commit()
        html = f"<h3>New Contact Message</h3><p>From: {name} ({email})</p><p>{message}</p>"
        send_email(os.environ.get('SUPPORT_EMAIL', 'admin@goldenvow.com'), f"Contact: {subject}", html)
        flash('Message sent. We\'ll get back to you.', 'success')
        return redirect(url_for('contact'))
    return render_template_string("""
{% extends 'base.html' %}
{% block content %}
<div class="row justify-content-center mt-4">
    <div class="col-md-6">
        <div class="card glass-card">
            <div class="card-body">
                <h4>Contact Us</h4>
                <form method="post">
                    <div class="mb-2"><input type="text" name="name" placeholder="Your Name" class="form-control" required></div>
                    <div class="mb-2"><input type="email" name="email" placeholder="Email" class="form-control" required></div>
                    <div class="mb-2"><input type="text" name="subject" placeholder="Subject" class="form-control"></div>
                    <div class="mb-2"><textarea name="message" rows="5" class="form-control" placeholder="Message" required></textarea></div>
                    <button type="submit" class="btn btn-gold w-100">Send</button>
                </form>
            </div>
        </div>
    </div>
</div>
{% endblock %}
""")

@app.route('/help')
def help_page():
    faqs = [
        {'q': 'How do I contribute?', 'a': 'Visit an event page, fill in your details, and submit a pledge. Then upload your payment proof.'},
        {'q': 'How are fees calculated?', 'a': 'A 2% service fee is deducted from each approved payment. Referral discounts may apply.'},
        {'q': 'What happens if an event locks?', 'a': 'If unpaid fees exceed KES 50 for 3+ days, the event is locked until fees are settled.'},
        {'q': 'How do I get a receipt?', 'a': 'Admins can generate receipts anytime. Contributors can download after 7 days.'},
        {'q': 'Can I chat privately with an admin?', 'a': 'Yes, use the private chat option from your dashboard.'}
    ]
    return render_template_string("""
{% extends 'base.html' %}
{% block content %}
<h3>Help Center</h3>
<div class="accordion" id="faqAccordion">
    {% for faq in faqs %}
    <div class="accordion-item">
        <h2 class="accordion-header">
            <button class="accordion-button collapsed" type="button" data-bs-toggle="collapse" data-bs-target="#faq{{ loop.index }}">
                {{ faq.q }}
            </button>
        </h2>
        <div id="faq{{ loop.index }}" class="accordion-collapse collapse" data-bs-parent="#faqAccordion">
            <div class="accordion-body">{{ faq.a }}</div>
        </div>
    </div>
    {% endfor %}
</div>
<p class="mt-3">Still need help? <a href="{{ url_for('contact') }}">Contact us</a></p>
{% endblock %}
""", faqs=faqs)

@app.route('/feature_request', methods=['GET', 'POST'])
def feature_request():
    if request.method == 'POST':
        title = request.form['title']
        desc = request.form['description']
        fr = FeatureRequest(
            title=title, description=desc,
            user_type=session.get('user_type', 'guest'),
            user_id=session.get('user_id', 0)
        )
        db.session.add(fr)
        db.session.commit()
        flash('Feature request submitted!', 'success')
        return redirect(url_for('feature_request'))
    requests = FeatureRequest.query.order_by(FeatureRequest.votes.desc()).limit(20).all()
    return render_template_string("""
{% extends 'base.html' %}
{% block content %}
<div class="row">
    <div class="col-md-6">
        <h4>Submit Feature Request</h4>
        <form method="post">
            <div class="mb-2"><input type="text" name="title" class="form-control" placeholder="Title" required></div>
            <div class="mb-2"><textarea name="description" class="form-control" rows="4" placeholder="Describe your idea..." required></textarea></div>
            <button type="submit" class="btn btn-gold">Submit</button>
        </form>
    </div>
    <div class="col-md-6">
        <h4>Top Requests</h4>
        <ul class="list-group">
            {% for fr in requests %}
            <li class="list-group-item d-flex justify-content-between">
                <div><strong>{{ fr.title }}</strong><br><small>{{ fr.description[:100] }}</small></div>
                <span class="badge bg-secondary">👍 {{ fr.votes }}</span>
            </li>
            {% endfor %}
        </ul>
    </div>
</div>
{% endblock %}
""", requests=requests)

# ---------- SUPER ADMIN ----------
@app.route('/super/dashboard')
@super_admin_required
def super_dashboard():
    admins = Admin.query.all()
    events = Event.query.all()
    pending_withdrawals = Withdrawal.query.filter_by(status='pending').count()
    total_fees = db.session.query(db.func.sum(Payment.fee_deducted)).scalar() or 0
    return render_template_string("""
{% extends 'base.html' %}
{% block content %}
<div class="row">
    <div class="col-md-3 admin-sidebar">
        <h5>Super Admin</h5>
        <ul class="nav flex-column">
            <li class="nav-item"><a class="nav-link active" href="{{ url_for('super_dashboard') }}"><i class="bi bi-speedometer2"></i> Dashboard</a></li>
            <li class="nav-item"><a class="nav-link" href="{{ url_for('toggle_maintenance') }}"><i class="bi bi-tools"></i> Maintenance</a></li>
            <li class="nav-item"><a class="nav-link" href="{{ url_for('admin_dashboard') }}"><i class="bi bi-arrow-left"></i> Back to Admin</a></li>
        </ul>
    </div>
    <div class="col-md-9">
        <h3>Super Admin Dashboard</h3>
        <div class="row g-3 mb-4">
            <div class="col-md-3"><div class="card glass-card p-3"><h5>Admins</h5><h2>{{ admins|length }}</h2></div></div>
            <div class="col-md-3"><div class="card glass-card p-3"><h5>Events</h5><h2>{{ events|length }}</h2></div></div>
            <div class="col-md-3"><div class="card glass-card p-3"><h5>Pending Withdrawals</h5><h2>{{ pending_withdrawals }}</h2></div></div>
            <div class="col-md-3"><div class="card glass-card p-3"><h5>Total Fees</h5><h2>KES {{ "%.2f"|format(total_fees) }}</h2></div></div>
        </div>
        <div class="row">
            <div class="col-md-6">
                <h5>Manage Admins</h5>
                <ul class="list-group">
                    {% for a in admins %}
                    <li class="list-group-item d-flex justify-content-between">
                        {{ a.username }} ({{ 'Super' if a.is_super_admin else 'Admin' }})
                        <span>
                            <a href="{{ url_for('toggle_admin', admin_id=a.id) }}" class="btn btn-sm {% if a.is_active %}btn-warning{% else %}btn-success{% endif %}">
                                {% if a.is_active %}Disable{% else %}Enable{% endif %}
                            </a>
                        </span>
                    </li>
                    {% endfor %}
                </ul>
            </div>
            <div class="col-md-6">
                <h5>Withdrawal Requests</h5>
                <ul class="list-group">
                    {% for w in withdrawals %}
                    <li class="list-group-item d-flex justify-content-between">
                        Admin: {{ w.admin.username }} - KES {{ "%.2f"|format(w.amount) }}
                        <span>
                            <a href="{{ url_for('complete_withdrawal', w_id=w.id) }}" class="btn btn-sm btn-success">Complete</a>
                        </span>
                    </li>
                    {% endfor %}
                </ul>
                <a href="{{ url_for('request_withdrawal') }}" class="btn btn-gold mt-2">Request Withdrawal</a>
            </div>
        </div>
        <div class="mt-3">
            <a href="{{ url_for('toggle_maintenance') }}" class="btn btn-outline-gold">
                {% if get_setting('maintenance_mode') == 'true' %}Disable Maintenance{% else %}Enable Maintenance{% endif %}
            </a>
        </div>
    </div>
</div>
{% endblock %}
""", admins=admins, events=events, pending_withdrawals=pending_withdrawals, total_fees=total_fees, withdrawals=Withdrawal.query.order_by(Withdrawal.requested_at.desc()).limit(10).all())

@app.route('/super/admin/<int:admin_id>/toggle')
@super_admin_required
def toggle_admin(admin_id):
    admin = Admin.query.get_or_404(admin_id)
    if admin.is_super_admin:
        flash('Cannot disable super admin.', 'danger')
        return redirect(url_for('super_dashboard'))
    admin.is_active = not admin.is_active
    db.session.commit()
    flash('Admin status toggled.', 'info')
    return redirect(url_for('super_dashboard'))

@app.route('/super/withdrawal/request', methods=['GET', 'POST'])
@super_admin_required
def request_withdrawal():
    if request.method == 'POST':
        amount = float(request.form['amount'])
        phone = request.form['phone']
        admin = Admin.query.get(session['user_id'])
        total_fees = db.session.query(db.func.sum(Payment.fee_deducted)).scalar() or 0
        withdrawn = db.session.query(db.func.sum(Withdrawal.amount)).filter(Withdrawal.status=='completed').scalar() or 0
        available = total_fees - withdrawn
        if amount > available:
            flash(f'Insufficient fees. Available: KES {available:.2f}', 'danger')
            return redirect(url_for('request_withdrawal'))
        w = Withdrawal(admin_id=admin.id, amount=amount, phone_number=phone)
        db.session.add(w)
        db.session.commit()
        flash('Withdrawal request submitted.', 'success')
        return redirect(url_for('super_dashboard'))
    return render_template_string("""
{% extends 'base.html' %}
{% block content %}
<div class="row justify-content-center">
    <div class="col-md-5">
        <div class="card glass-card">
            <div class="card-body">
                <h4>Request Withdrawal</h4>
                <form method="post">
                    <div class="mb-2"><label>Amount (KES)</label><input type="number" step="0.01" name="amount" class="form-control" required></div>
                    <div class="mb-2"><label>Phone Number</label><input type="text" name="phone" class="form-control" required></div>
                    <button type="submit" class="btn btn-gold w-100">Request</button>
                </form>
            </div>
        </div>
    </div>
</div>
{% endblock %}
""")

@app.route('/super/withdrawal/<int:w_id>/complete')
@super_admin_required
def complete_withdrawal(w_id):
    w = Withdrawal.query.get_or_404(w_id)
    w.status = 'completed'
    w.completed_at = datetime.utcnow()
    db.session.commit()
    flash('Withdrawal completed.', 'success')
    return redirect(url_for('super_dashboard'))

@app.route('/super/maintenance/toggle')
@super_admin_required
def toggle_maintenance():
    setting = Setting.query.filter_by(key='maintenance_mode').first()
    if setting:
        setting.value = 'false' if setting.value == 'true' else 'true'
    else:
        setting = Setting(key='maintenance_mode', value='true')
        db.session.add(setting)
    db.session.commit()
    flash('Maintenance mode toggled.', 'info')
    return redirect(url_for('super_dashboard'))

# ---------- EVENT LOCK HELPER ----------
def check_event_lock(event):
    if event.is_locked:
        return True
    total_unpaid = 0.0
    for payment in event.payments:
        if payment.status != 'approved':
            total_unpaid += payment.amount
    if total_unpaid >= 50:
        first_contrib = Contributor.query.filter_by(event_id=event.id).order_by(Contributor.created_at).first()
        if first_contrib:
            days_since_first = (datetime.utcnow() - first_contrib.created_at).days
            if days_since_first >= 3:
                event.is_locked = True
                db.session.commit()
                return True
    return False

# ---------- SCHEDULER ----------
def send_reminders():
    with app.app_context():
        pending = Payment.query.filter_by(status='pending').filter(Payment.created_at < datetime.utcnow() - timedelta(days=2)).all()
        for p in pending:
            create_notification('contributor', p.contributor_id, f'Reminder: Your payment of KES {p.amount} for {p.event.title} is still pending verification.')
        events = Event.query.filter_by(is_locked=False).all()
        for event in events:
            check_event_lock(event)

scheduler = BackgroundScheduler()
scheduler.add_job(func=send_reminders, trigger="interval", hours=3)
scheduler.start()

# ---------- ERROR HANDLERS ----------
@app.errorhandler(404)
def not_found(e):
    return render_template_string("{% extends 'base.html' %}{% block content %}<h1>404</h1><p>Page not found.</p>{% endblock %}"), 404

@app.errorhandler(500)
def server_error(e):
    return render_template_string("{% extends 'base.html' %}{% block content %}<h1>500</h1><p>Server error. Please try again later.</p>{% endblock %}"), 500

# ---------- CREATE TABLES ----------
with app.app_context():
    db.create_all()

# ---------- RUN ----------
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    socketio.run(app, host='0.0.0.0', port=port, debug=False, allow_unsafe_werkzeug=True)
