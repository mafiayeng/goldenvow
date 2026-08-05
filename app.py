# ==================== app.py – COMPLETE FINAL VERSION ====================
import os, uuid, random, string, io, secrets
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, send_file
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import desc, func, inspect
from flask_socketio import SocketIO, emit, join_room, leave_room
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

# 🔥 SocketIO with threading mode – works on Render without eventlet
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# ---------- CONFIG ----------
SERVICE_FEE_PERCENTAGE = float(os.environ.get('SERVICE_FEE_PERCENTAGE', 2.0))
SUPPORT_WHATSAPP = os.environ.get('SUPPORT_WHATSAPP', '0737349468')
SUPPORT_EMAIL = os.environ.get('SUPPORT_EMAIL', 'support@goldenvow.com')
SUPER_ADMIN_SECRET = os.environ.get('SUPER_ADMIN_SECRET', 'changeme_super_secret_123')
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
    last_action = db.Column(db.DateTime, nullable=True)

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
    last_weekly_receipt = db.Column(db.DateTime, nullable=True)

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
        cols = [c['name'] for c in inspector.get_columns('admin')]
        if 'is_active' not in cols:
            db.engine.execute('ALTER TABLE admin ADD COLUMN is_active BOOLEAN DEFAULT 1')
        cols = [c['name'] for c in inspector.get_columns('event')]
        if 'account_name' not in cols:
            db.engine.execute('ALTER TABLE event ADD COLUMN account_name VARCHAR(150)')
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

def get_app_logo(size=40):
    return f'''<svg width="{size}" height="{size}" viewBox="0 0 {size} {size}">
        <circle cx="{size/2}" cy="{size/2}" r="{size/2-3}" fill="#1A2A3A"/>
        <circle cx="{size/2}" cy="{size/2}" r="{size/2-8}" stroke="#D4AF37" stroke-width="2" fill="none"/>
        <text x="{size/2}" y="{size/2+5}" text-anchor="middle" fill="#D4AF37" font-size="{size/3}" font-weight="bold">GV</text>
        <text x="{size/4}" y="{size/4}" fill="#D4AF37" font-size="{size/8}">✦</text>
        <text x="{size*0.75}" y="{size/4}" fill="#D4AF37" font-size="{size/8}">✦</text>
    </svg>'''

# ---------- CONTEXT PROCESSOR ----------
@app.context_processor
def utility_processor():
    return dict(
        get_app_logo=get_app_logo,
        get_fee_percentage=get_fee_percentage,
        get_event_total_contributions=get_event_total_contributions,
        get_event_total_fee=get_event_total_fee,
        get_admin_total_fees=get_admin_total_fees,
        get_global_total_fees=get_global_total_fees,
        get_page_lock_status=get_page_lock_status,
        generate_event_logo=generate_event_logo,
        get_unread_notifications=get_unread_notifications,
        is_admin_logged_in=is_admin_logged_in,
        is_contributor_logged_in=is_contributor_logged_in,
        get_admin=get_admin,
        get_contributor=get_contributor,
        support_whatsapp=SUPPORT_WHATSAPP,
        support_email=SUPPORT_EMAIL,
        fee_percentage=SERVICE_FEE_PERCENTAGE,
        minimum_withdrawal_fee=MINIMUM_WITHDRAWAL_FEE,
        now=datetime.utcnow
    )

# ---------- MAINTENANCE FILTER ----------
@app.before_request
def check_maintenance():
    if request.endpoint in ['static', 'force_maintenance_off', 'run_migration']:
        return
    if is_admin_logged_in() and get_admin() and get_admin().is_super_admin:
        return
    setting = Setting.query.filter_by(key='maintenance_mode').first()
    if setting and setting.value == 'True':
        allowed = ['login', 'register', 'maintenance', 'contact', 'forgot_password', 'reset_password', 
                   'contributor_login', 'contributor_register', 'contributor_dashboard']
        if request.endpoint not in allowed:
            msg = Setting.query.filter_by(key='maintenance_message').first()
            eta = Setting.query.filter_by(key='maintenance_eta').first()
            return render_template('maintenance.html',
                                   message=msg.value if msg else "We are upgrading the system. Sorry for the inconvenience.",
                                   eta=eta.value if eta else "We'll be back soon."), 503

# ---------- SOCKET.IO EVENTS ----------
@socketio.on('connect')
def handle_connect():
    print('Client connected')

@socketio.on('join_event')
def handle_join_event(data):
    room = data.get('event_token')
    if room:
        join_room(room)
        emit('joined', {'room': room})

@socketio.on('chat_message')
def handle_chat(data):
    event_token = data.get('event_token')
    sender = data.get('sender_name')
    msg = data.get('message')
    event = Event.query.filter_by(token=event_token).first()
    if event:
        chat = ChatMessage(event_id=event.id, sender_name=sender, sender_type='contributor', message=msg)
        db.session.add(chat)
        db.session.commit()
        emit('new_chat', {'sender': sender, 'message': msg, 'time': datetime.utcnow().strftime('%H:%M')}, room=event_token)

@socketio.on('private_message')
def handle_private_message(data):
    conv_id = data.get('conversation_id')
    sender_type = data.get('sender_type')
    sender_id = data.get('sender_id')
    message = data.get('message')
    conv = Conversation.query.get(conv_id)
    if not conv:
        return
    pm = PrivateMessage(conversation_id=conv_id, sender_type=sender_type, sender_id=sender_id, message=message)
    db.session.add(pm)
    db.session.commit()
    if sender_type == 'admin':
        pass
    else:
        admin = Admin.query.get(conv.admin_id)
        if admin:
            create_notification(admin.id, f'New private message from contributor {conv.contributor_id}', 'chat', conv.event_id)
    room = f"conversation_{conv_id}"
    emit('new_private_message', {
        'sender_type': sender_type,
        'sender_id': sender_id,
        'message': message,
        'time': datetime.utcnow().strftime('%H:%M')
    }, room=room)

@socketio.on('join_conversation')
def handle_join_conversation(data):
    conv_id = data.get('conversation_id')
    room = f"conversation_{conv_id}"
    join_room(room)

def emit_contribution_update(event_token):
    event = Event.query.filter_by(token=event_token).first()
    if event:
        total = get_event_total_contributions(event.id)
        fee = get_event_total_fee(event.id)
        socketio.emit('total_updated', {'total': total, 'fee': fee}, room=event_token)

# ---------- ROUTES ----------
@app.route('/force_maintenance_off')
def force_maintenance_off():
    secret = request.args.get('secret')
    if secret != 'c4eB9xQmW8vN2kR5yTzH7bJ4dF6sA1cX0':
        return "Unauthorized", 401
    setting = Setting.query.filter_by(key='maintenance_mode').first()
    if setting:
        setting.value = 'False'
        db.session.commit()
    return "Maintenance off."

@app.route('/run-migration')
def run_migration():
    secret = request.args.get('secret')
    if secret != 'c4eB9xQmW8vN2kR5yTzH7bJ4dF6sA1cX0':
        return "Unauthorized", 401
    return "Migration done."

# ---------- ADMIN AUTH ----------
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
            return render_template('register.html')
        if Admin.query.filter_by(username=username).first():
            flash('Username taken.', 'error')
            return render_template('register.html')
        if Admin.query.filter_by(email=email).first():
            flash('Email already registered.', 'error')
            return render_template('register.html')
        referral_code = generate_referral_code()
        while Admin.query.filter_by(referral_code=referral_code).first():
            referral_code = generate_referral_code()
        admin = Admin(username=username, password_hash=hash_password(password), email=email, phone=phone,
                      referral_code=referral_code, is_super_admin=False)
        if super_secret == SUPER_ADMIN_SECRET:
            admin.is_super_admin = True
            flash('You are now the Super Admin!', 'success')
        elif Admin.query.count() == 0:
            admin.is_super_admin = True
            flash('First user registered as Super Admin.', 'success')
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
    return render_template('register.html')

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
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out.', 'info')
    return redirect(url_for('login'))

@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email')
        admin = Admin.query.filter_by(email=email).first()
        if not admin:
            flash('No account with that email.', 'error')
            return render_template('forgot_password.html')
        token = secrets.token_urlsafe(32)
        expires = datetime.utcnow() + timedelta(hours=1)
        reset = PasswordReset(admin_id=admin.id, token=token, expires_at=expires)
        db.session.add(reset)
        db.session.commit()
        flash('Password reset link sent to your email.', 'success')
        return redirect(url_for('login'))
    return render_template('forgot_password.html')

@app.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    reset = PasswordReset.query.filter_by(token=token, used=False).first()
    if not reset or reset.expires_at < datetime.utcnow():
        flash('Invalid or expired reset link.', 'error')
        return redirect(url_for('login'))
    if request.method == 'POST':
        password = request.form.get('password')
        confirm = request.form.get('confirm')
        if password != confirm:
            flash('Passwords do not match.', 'error')
            return render_template('reset_password.html', token=token)
        admin = Admin.query.get(reset.admin_id)
        admin.password_hash = hash_password(password)
        reset.used = True
        db.session.commit()
        flash('Password updated. Please login.', 'success')
        return redirect(url_for('login'))
    return render_template('reset_password.html', token=token)

# ---------- CONTRIBUTOR AUTH ----------
@app.route('/contributor/register', methods=['GET', 'POST'])
def contributor_register():
    event_token = request.args.get('event_token', '')
    event = None
    if event_token:
        event = Event.query.filter_by(token=event_token).first()
    
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        name = request.form.get('name', '').strip()
        phone = request.form.get('phone', '').strip()
        event_token_post = request.form.get('event_token', '').strip()
        
        if not username or not password or not name:
            flash('Username, password, and name are required.', 'error')
            return render_template('contributor_register.html', event_token=event_token_post, event=event)
        
        if Contributor.query.filter_by(username=username).first():
            flash('Username already taken.', 'error')
            return render_template('contributor_register.html', event_token=event_token_post, event=event)
        
        token = generate_unique_token()
        while Contributor.query.filter_by(token=token).first():
            token = generate_unique_token()
        
        contrib = Contributor(
            token=token,
            username=username,
            password_hash=hash_password(password),
            name=name,
            phone=phone,
            status='pending'
        )
        db.session.add(contrib)
        db.session.commit()
        
        session['contributor_id'] = contrib.id
        
        flash('Registration successful! You are now logged in.', 'success')
        if event_token_post:
            return redirect(url_for('event_landing', token=event_token_post))
        return redirect(url_for('contributor_dashboard'))
    
    return render_template('contributor_register.html', event_token=event_token, event=event)

@app.route('/contributor/login', methods=['GET', 'POST'])
def contributor_login():
    event_token = request.args.get('event_token', '')
    event = None
    if event_token:
        event = Event.query.filter_by(token=event_token).first()
    
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
            flash('Logged in successfully!', 'success')
            if event_token_post:
                return redirect(url_for('event_landing', token=event_token_post))
            return redirect(url_for('contributor_dashboard'))
        flash('Invalid username or password.', 'error')
    
    return render_template('contributor_login.html', event_token=event_token, event=event)

@app.route('/contributor/logout')
def contributor_logout():
    session.pop('contributor_id', None)
    flash('Logged out.', 'info')
    return redirect(url_for('contributor_login'))

@app.route('/contributor/dashboard')
def contributor_dashboard():
    if not is_contributor_logged_in():
        flash('Please log in first.', 'error')
        return redirect(url_for('contributor_login'))
    
    contrib = get_contributor()
    if not contrib:
        session.pop('contributor_id', None)
        return redirect(url_for('contributor_login'))
    
    contributions = Contributor.query.filter_by(name=contrib.name, phone=contrib.phone).order_by(desc(Contributor.created_at)).all()
    
    return render_template('contributor_dashboard.html', contrib=contrib, contributions=contributions)

# ---------- ADMIN DASHBOARDS ----------
@app.route('/')
def index():
    if is_admin_logged_in():
        admin = get_admin()
        if admin.is_super_admin:
            return redirect(url_for('super_dashboard'))
        return redirect(url_for('dashboard'))
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
    return render_template('dashboard.html', admin=admin, events=events, total_raised=total_raised,
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
    return render_template('super_dashboard.html', admin=admin, total_events=total_events,
                           total_contributions=total_contributions, total_fees=total_fees,
                           pending_withdrawals=pending_withdrawals, locked_events=locked_events,
                           admins=admins, pending_feature_requests=pending_feature_requests,
                           contact_messages_count=contact_messages_count, can_withdraw=can_withdraw)

@app.route('/manage-admins')
def manage_admins():
    if not is_admin_logged_in() or not get_admin().is_super_admin:
        flash('Unauthorized.', 'error')
        return redirect(url_for('login'))
    admins = Admin.query.all()
    return render_template('manage_admins.html', admins=admins)

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
    flash('Admin status toggled.', 'success')
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

# ---------- EVENT MANAGEMENT ----------
@app.route('/events/create', methods=['GET', 'POST'])
def create_event():
    if not is_admin_logged_in():
        return redirect(url_for('login'))
    admin = get_admin()
    if admin.is_super_admin:
        flash('Super admins cannot create events. Use a normal admin account.', 'error')
        return redirect(url_for('super_dashboard'))
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
    return render_template('create_event.html')

@app.route('/events/<token>')
def event_landing(token):
    event = Event.query.filter_by(token=token).first_or_404()
    if not event.is_active:
        flash('Event inactive.', 'error')
        return redirect(url_for('dashboard'))
    if get_page_lock_status(event):
        return render_template('event_locked.html', event=event)
    
    contributor = None
    if is_contributor_logged_in():
        contributor = get_contributor()
    
    contributions = Contributor.query.filter_by(event_id=event.id, status='approved').order_by(desc(Contributor.created_at)).all()
    total_raised = get_event_total_contributions(event.id)
    chat_messages = ChatMessage.query.filter_by(event_id=event.id).order_by(ChatMessage.timestamp).limit(50).all()
    testimonials = Testimonial.query.filter_by(event_id=event.id).order_by(desc(Testimonial.created_at)).limit(10).all()
    days = (datetime.utcnow() - event.created_at).days + 1
    daily_note = get_daily_note(event.event_type, days)
    return render_template('event_landing.html', event=event, contributions=contributions,
                           total_raised=total_raised, chat_messages=chat_messages,
                           testimonials=testimonials, daily_note=daily_note,
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
    return render_template('edit_event.html', event=event)

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

# ---------- FEE PAYMENT ----------
@app.route('/events/<token>/pay-fee', methods=['POST'])
def pay_event_fee(token):
    if not is_admin_logged_in():
        return redirect(url_for('login'))
    admin = get_admin()
    if not admin.is_super_admin:
        flash('Only super admin can mark fee as paid.', 'error')
        return redirect(url_for('dashboard'))
    event = Event.query.filter_by(token=token).first_or_404()
    event.fee_paid = True
    event.fee_paid_date = datetime.utcnow()
    db.session.commit()
    flash('Fee marked as paid. Event unlocked.', 'success')
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
        create_notification(sa.id, f'Fee payment requested for event: {event.title} by {admin.username}. Please mark as paid.', 'fee_request', event.id)
    flash('Request sent to super admin.', 'success')
    return redirect(url_for('manage_contributors', token=event.token))

# ---------- CONTRIBUTORS ----------
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
    return render_template('contributors.html', event=event, contributors=contributors)

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
    
    return render_template('contributor_view.html', contrib=contrib, event=event, payments=payments,
                           show_payments=show_payments, conversation_id=conv.id,
                           is_admin_user=is_admin_user, is_contributor_owner=is_contributor_owner)

@app.route('/contributor/<token>/approve', methods=['POST'])
def approve_contributor(token):
    if not is_admin_logged_in():
        return redirect(url_for('login'))
    
    admin = get_admin()
    if admin.is_super_admin:
        flash('Super admins cannot approve contributions. Use a normal admin account.', 'error')
        return redirect(url_for('super_dashboard'))
    
    contrib = Contributor.query.filter_by(token=token).first_or_404()
    event = Event.query.get(contrib.event_id)
    
    if event.admin_id != admin.id:
        flash('You are not the admin of this event.', 'error')
        return redirect(url_for('dashboard'))
    
    if contrib.status == 'pending':
        received = float(request.form.get('received_amount', contrib.pledge_amount))
        if received <= 0:
            flash('Received amount must be > 0.', 'error')
            return redirect(url_for('manage_contributors', token=event.token))
        
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
        
        create_notification(admin.id, f'Contribution from {contrib.name} approved.', 'success', event.id, contrib.id)
        emit_contribution_update(event.token)
        
        flash(f'✅ Contribution approved! Fee: KES {fee}', 'success')
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
        flash('Unauthorized.', 'error')
        return redirect(url_for('dashboard'))
    if contrib.status == 'pending':
        reason = request.form.get('reason', 'No reason provided.')
        contrib.status = 'declined'
        contrib.decline_reason = reason
        db.session.commit()
        create_notification(admin.id, f'Contribution from {contrib.name} declined.', 'danger', event.id, contrib.id)
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
    create_notification(
        admin.id,
        f'📎 Payment proof from {contrib.name}. System verification: {"✅ MATCH" if auto_verified else "⚠️ MISMATCH"}',
        'info',
        event.id,
        contrib.id
    )
    
    flash('📎 Payment proof submitted. Admin will review.', 'info')
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

# ---------- PRIVATE CHAT ----------
@app.route('/chat/admin')
def admin_chat_list():
    if not is_admin_logged_in():
        return redirect(url_for('login'))
    admin = get_admin()
    conversations = Conversation.query.filter_by(admin_id=admin.id).order_by(desc(Conversation.updated_at)).all()
    return render_template('chat_admin_list.html', admin=admin, conversations=conversations)

@app.route('/chat/admin/<int:conv_id>')
def admin_chat(conv_id):
    if not is_admin_logged_in():
        return redirect(url_for('login'))
    admin = get_admin()
    conv = Conversation.query.get_or_404(conv_id)
    if conv.admin_id != admin.id:
        flash('Unauthorized.', 'error')
        return redirect(url_for('dashboard'))
    messages = PrivateMessage.query.filter_by(conversation_id=conv_id).order_by(PrivateMessage.timestamp).all()
    for msg in messages:
        if msg.sender_type == 'contributor' and not msg.is_read:
            msg.is_read = True
    db.session.commit()
    return render_template('chat_admin.html', conv=conv, messages=messages, admin=admin)

@app.route('/chat/contributor/<token>')
def contributor_chat(token):
    contrib = Contributor.query.filter_by(token=token).first_or_404()
    event = Event.query.get(contrib.event_id)
    conv = Conversation.query.filter_by(event_id=event.id, admin_id=event.admin_id, contributor_id=contrib.id).first()
    if not conv:
        conv = Conversation(event_id=event.id, admin_id=event.admin_id, contributor_id=contrib.id)
        db.session.add(conv)
        db.session.commit()
    messages = PrivateMessage.query.filter_by(conversation_id=conv.id).order_by(PrivateMessage.timestamp).all()
    for msg in messages:
        if msg.sender_type == 'admin' and not msg.is_read:
            msg.is_read = True
    db.session.commit()
    return render_template('chat_contributor.html', conv=conv, messages=messages, contrib=contrib, event=event)

# ---------- FEATURE REQUESTS ----------
@app.route('/feature-request', methods=['GET', 'POST'])
@app.route('/feature-request/<event_token>', methods=['GET', 'POST'])
def submit_feature_request(event_token=None):
    event = None
    contributor_token = request.args.get('contributor_token')
    if event_token:
        event = Event.query.filter_by(token=event_token).first_or_404()
    contributor_name = request.args.get('name', '')
    contributor_email = request.args.get('email', '')
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip()
        title = request.form.get('title', '').strip()
        description = request.form.get('description', '').strip()
        event_token_post = request.form.get('event_token')
        contributor_token_post = request.form.get('contributor_token')
        if not name or not title or not description:
            flash('Name, title, and description are required.', 'error')
            return render_template('feature_request.html', event=event, contributor_name=name, contributor_email=email)
        contributor_id = None
        if contributor_token_post:
            contrib = Contributor.query.filter_by(token=contributor_token_post).first()
            if contrib:
                contributor_id = contrib.id
        event_id = None
        if event_token_post:
            ev = Event.query.filter_by(token=event_token_post).first()
            if ev:
                event_id = ev.id
        feature = FeatureRequest(
            event_id=event_id,
            contributor_id=contributor_id,
            contributor_name=name,
            contributor_email=email,
            title=title,
            description=description,
            status='pending'
        )
        db.session.add(feature)
        db.session.commit()
        super_admins = Admin.query.filter_by(is_super_admin=True).all()
        for sa in super_admins:
            create_notification(sa.id, f'💡 New feature request from {name}: {title}', 'feature_request', event_id, contributor_id)
        flash('✅ Thank you! Your feature suggestion has been submitted.', 'success')
        if event:
            return redirect(url_for('event_landing', token=event.token))
        return redirect(url_for('dashboard'))
    return render_template('feature_request.html', event=event, contributor_name=contributor_name,
                           contributor_email=contributor_email, contributor_token=contributor_token)

@app.route('/manage-feature-requests')
def manage_feature_requests():
    if not is_admin_logged_in() or not get_admin().is_super_admin:
        flash('Unauthorized.', 'error')
        return redirect(url_for('login'))
    requests = FeatureRequest.query.order_by(desc(FeatureRequest.created_at)).all()
    return render_template('manage_feature_requests.html', requests=requests)

@app.route('/feature-request/<int:req_id>/update', methods=['POST'])
def update_feature_request(req_id):
    if not is_admin_logged_in() or not get_admin().is_super_admin:
        flash('Unauthorized.', 'error')
        return redirect(url_for('login'))
    req = FeatureRequest.query.get_or_404(req_id)
    status = request.form.get('status')
    response = request.form.get('response', '').strip()
    if status in ['pending', 'reviewing', 'approved', 'declined']:
        req.status = status
        req.admin_response = response
        req.updated_at = datetime.utcnow()
        db.session.commit()
        flash(f'✅ Feature request updated to {status}.', 'success')
    else:
        flash('Invalid status.', 'error')
    return redirect(url_for('manage_feature_requests'))

# ---------- CONTACT SUPER ADMIN ----------
@app.route('/contact-super', methods=['GET', 'POST'])
def contact_super():
    if not is_admin_logged_in():
        return redirect(url_for('login'))
    admin = get_admin()
    if request.method == 'POST':
        name = request.form.get('name', admin.username)
        email = request.form.get('email', admin.email)
        phone = request.form.get('phone', admin.phone or '')
        subject = request.form.get('subject', '').strip()
        message = request.form.get('message', '').strip()
        if not subject or not message:
            flash('Subject and message are required.', 'error')
            return render_template('contact_super.html', admin=admin)
        super_admins = Admin.query.filter_by(is_super_admin=True).all()
        for sa in super_admins:
            create_notification(sa.id, f'📩 New message from {name} (Admin): {subject}', 'info', None, None)
            contact_msg = ContactMessage(
                name=name,
                email=email,
                phone=phone,
                subject=f'[Admin Message] {subject}',
                message=f"From Admin: {name}\nEmail: {email}\nPhone: {phone}\n\n{message}",
                is_read=False
            )
            db.session.add(contact_msg)
        db.session.commit()
        flash('✅ Your message has been sent to the Super Admin.', 'success')
        return redirect(url_for('dashboard'))
    return render_template('contact_super.html', admin=admin)

# ---------- WITHDRAWALS ----------
@app.route('/withdrawals')
def withdrawals():
    if not is_admin_logged_in() or not get_admin().is_super_admin:
        flash('Unauthorized.', 'error')
        return redirect(url_for('login'))
    wd_list = Withdrawal.query.order_by(desc(Withdrawal.created_at)).all()
    return render_template('withdrawals.html', withdrawals=wd_list)

@app.route('/withdrawal/request', methods=['POST'])
def request_withdrawal():
    if not is_admin_logged_in():
        return redirect(url_for('login'))
    admin = get_admin()
    if not admin.is_super_admin:
        flash('Only Super Admin can request withdrawal.', 'error')
        return redirect(url_for('dashboard'))
    
    amount = float(request.form.get('amount', 0))
    phone = request.form.get('phone', '').strip()
    method = request.form.get('method', 'mpesa')
    
    if amount <= 0 or not phone:
        flash('Invalid amount or phone.', 'error')
        return redirect(url_for('super_dashboard'))
    
    if amount < MINIMUM_WITHDRAWAL_FEE:
        flash(f'Minimum withdrawal amount is KES {MINIMUM_WITHDRAWAL_FEE}.', 'error')
        return redirect(url_for('super_dashboard'))
    
    total_fees = db.session.query(func.sum(Contributor.fee_amount)).filter_by(status='approved').scalar() or 0
    if amount > total_fees:
        flash(f'Insufficient fees earned. You have KES {total_fees:.2f}.', 'error')
        return redirect(url_for('super_dashboard'))
    
    wd = Withdrawal(admin_id=admin.id, amount=amount, phone=phone, method=method, status='pending')
    db.session.add(wd)
    db.session.commit()
    flash(f'Withdrawal request of KES {amount:.2f} submitted.', 'success')
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

# ---------- CONTACT ----------
@app.route('/contact', methods=['GET', 'POST'])
def contact():
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        phone = request.form.get('phone')
        subject = request.form.get('subject')
        message = request.form.get('message')
        if not all([name, email, subject, message]):
            flash('All fields required.', 'error')
            return render_template('contact.html')
        msg = ContactMessage(name=name, email=email, phone=phone, subject=subject, message=message)
        db.session.add(msg)
        db.session.commit()
        super_admins = Admin.query.filter_by(is_super_admin=True).all()
        for sa in super_admins:
            create_notification(sa.id, f'New contact message from {name}: {subject}', 'info')
        flash('Message sent.', 'success')
        return redirect(url_for('contact'))
    return render_template('contact.html')

@app.route('/contact-messages')
def contact_messages():
    if not is_admin_logged_in() or not get_admin().is_super_admin:
        flash('Unauthorized.', 'error')
        return redirect(url_for('login'))
    messages = ContactMessage.query.order_by(desc(ContactMessage.created_at)).all()
    return render_template('contact_messages.html', messages=messages)

@app.route('/contact-message/<int:mid>/read', methods=['POST'])
def mark_contact_read(mid):
    if not is_admin_logged_in() or not get_admin().is_super_admin:
        flash('Unauthorized.', 'error')
        return redirect(url_for('login'))
    msg = ContactMessage.query.get_or_404(mid)
    msg.is_read = True
    db.session.commit()
    flash('Marked read.', 'success')
    return redirect(url_for('contact_messages'))

# ---------- NOTIFICATIONS ----------
@app.route('/notifications')
def notifications():
    if not is_admin_logged_in():
        return redirect(url_for('login'))
    admin = get_admin()
    notifs = Notification.query.filter_by(admin_id=admin.id).order_by(desc(Notification.created_at)).limit(100).all()
    return render_template('notifications.html', notifications=notifs)

@app.route('/notification/<int:nid>/read', methods=['POST'])
def mark_notification_read(nid):
    if not is_admin_logged_in():
        return jsonify({'error': 'Unauthorized'}), 401
    notif = Notification.query.get_or_404(nid)
    if notif.admin_id != session['admin_id']:
        return jsonify({'error': 'Unauthorized'}), 401
    notif.is_read = True
    db.session.commit()
    return jsonify({'success': True})

@app.route('/notification/mark-all-read', methods=['POST'])
def mark_all_notifications_read():
    if not is_admin_logged_in():
        return jsonify({'error': 'Unauthorized'}), 401
    Notification.query.filter_by(admin_id=session['admin_id'], is_read=False).update({'is_read': True})
    db.session.commit()
    return jsonify({'success': True})

# ---------- SETTINGS ----------
@app.route('/settings', methods=['GET', 'POST'])
def settings():
    if not is_admin_logged_in() or not get_admin().is_super_admin:
        flash('Unauthorized.', 'error')
        return redirect(url_for('login'))
    def get_setting(key, default=''):
        s = Setting.query.filter_by(key=key).first()
        if not s:
            s = Setting(key=key, value=default)
            db.session.add(s)
            db.session.commit()
        return s
    maintenance_mode = get_setting('maintenance_mode', 'False')
    maintenance_message = get_setting('maintenance_message', 'We are currently upgrading the platform. We apologize for the inconvenience.')
    maintenance_eta = get_setting('maintenance_eta', 'We will be back online in a few hours.')
    if request.method == 'POST':
        mode = request.form.get('maintenance_mode') == 'on'
        msg = request.form.get('maintenance_message', '').strip()
        eta = request.form.get('maintenance_eta', '').strip()
        maintenance_mode.value = 'True' if mode else 'False'
        maintenance_message.value = msg if msg else 'We are currently upgrading the platform. We apologize for the inconvenience.'
        maintenance_eta.value = eta if eta else 'We will be back online in a few hours.'
        db.session.commit()
        flash('Settings updated.', 'success')
        return redirect(url_for('settings'))
    return render_template('settings.html',
                           maintenance_mode=(maintenance_mode.value == 'True'),
                           maintenance_message=maintenance_message.value,
                           maintenance_eta=maintenance_eta.value,
                           Admin=Admin)

# ---------- PROFILE ----------
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
    return render_template('profile.html', admin=admin)

# ---------- HELP PAGE ----------
@app.route('/help')
def help_page():
    if not is_admin_logged_in():
        return redirect(url_for('login'))
    return render_template('help.html')

# ---------- SCHEDULER ----------
def check_pending_contributions():
    with app.app_context():
        pending = Contributor.query.filter_by(status='pending').all()
        for c in pending:
            event = Event.query.get(c.event_id)
            if not event:
                continue
            admin = Admin.query.get(event.admin_id)
            if not admin:
                continue
            last = Notification.query.filter_by(
                admin_id=admin.id,
                event_id=event.id,
                contributor_id=c.id,
                type='reminder'
            ).order_by(desc(Notification.created_at)).first()
            if not last or (datetime.utcnow() - last.created_at).total_seconds() > 10800:
                create_notification(admin.id, f'⏰ Pending contribution from {c.name} needs approval.', 'reminder', event.id, c.id)

scheduler = BackgroundScheduler()
scheduler.add_job(check_pending_contributions, 'interval', hours=3)
scheduler.start()

# ---------- MAIN ----------
if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
