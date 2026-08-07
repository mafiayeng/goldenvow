# =============================================================================
# GOLDENVOW – COMPLETE APPLICATION (Separate Templates)
# =============================================================================
import os, uuid, random, string, io, secrets, smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, send_file
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import desc, func, inspect
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

# ---------- CREATE TABLES ----------
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

# ---------- ROUTES ----------
@app.route('/')
def index():
    if is_admin_logged_in():
        admin = get_admin()
        if admin is None:
            session.clear()
            flash('Session invalid.', 'error')
            return redirect(url_for('login'))
        if admin.is_super_admin:
            return redirect(url_for('super_dashboard'))
        return redirect(url_for('dashboard'))
    if is_contributor_logged_in():
        return redirect(url_for('contributor_dashboard'))
    return render_template('landing.html')

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
    return render_template('login.html')

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
    return render_template('register.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out.', 'info')
    return redirect(url_for('login'))

@app.route('/dashboard')
def dashboard():
    if not is_admin_logged_in():
        flash('Please login.', 'error')
        return redirect(url_for('login'))
    admin = get_admin()
    if admin is None:
        session.clear()
        flash('Session invalid.', 'error')
        return redirect(url_for('login'))
    if admin.is_super_admin:
        return redirect(url_for('super_dashboard'))
    page = request.args.get('page', 1, type=int)
    events = Event.query.filter_by(admin_id=admin.id).order_by(desc(Event.created_at)).paginate(page=page, per_page=10)
    total_raised = sum(get_event_total_contributions(e.id) for e in events.items)
    pending_count = Contributor.query.filter_by(status='pending').join(Event).filter(Event.admin_id == admin.id).count()
    return render_template('dashboard.html', admin=admin, events=events,
                            total_raised=total_raised, pending_contributions=pending_count)

@app.route('/super-dashboard')
def super_dashboard():
    if not is_admin_logged_in():
        flash('Please login.', 'error')
        return redirect(url_for('login'))
    admin = get_admin()
    if admin is None:
        session.clear()
        flash('Session invalid.', 'error')
        return redirect(url_for('login'))
    if not admin.is_super_admin:
        flash('Access denied.', 'error')
        return redirect(url_for('dashboard'))
    total_events = Event.query.count()
    total_contributions = db.session.query(func.sum(Contributor.paid_amount)).filter_by(status='approved').scalar() or 0
    total_fees = db.session.query(func.sum(Contributor.fee_amount)).filter_by(status='approved').scalar() or 0
    pending_withdrawals = Withdrawal.query.filter_by(status='pending').count()
    admins = Admin.query.all()
    return render_template('super_dashboard.html', admin=admin, total_events=total_events,
                            total_contributions=total_contributions, total_fees=total_fees,
                            pending_withdrawals=pending_withdrawals, admins=admins)

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
        return render_template('event_locked.html', event=event)  # We'll create a simple locked page later
    contributor = None
    if is_contributor_logged_in():
        contributor = get_contributor()
    total_raised = get_event_total_contributions(event.id)
    chat_messages = ChatMessage.query.filter_by(event_id=event.id).order_by(ChatMessage.timestamp).limit(50).all()
    testimonials = Testimonial.query.filter_by(event_id=event.id).order_by(desc(Testimonial.created_at)).limit(10).all()
    days = (datetime.utcnow() - event.created_at).days + 1
    daily_note = get_daily_note(event.event_type, days)
    return render_template('event_landing.html', event=event, total_raised=total_raised,
                            chat_messages=chat_messages, testimonials=testimonials, daily_note=daily_note,
                            contributor=contributor, token=token)

@app.route('/events/<token>/edit', methods=['GET', 'POST'])
def edit_event(token):
    # For now, a placeholder – you can reuse the create form with pre-filled data.
    flash('Edit coming soon.', 'info')
    return redirect(url_for('dashboard'))

@app.route('/events/<token>/delete', methods=['POST'])
def delete_event(token):
    flash('Delete coming soon.', 'info')
    return redirect(url_for('dashboard'))

@app.route('/events/<token>/toggle-active', methods=['POST'])
def toggle_event_active(token):
    flash('Toggle coming soon.', 'info')
    return redirect(url_for('dashboard'))

@app.route('/events/<token>/lock-page', methods=['POST'])
def lock_event_page(token):
    flash('Lock coming soon.', 'info')
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
    return render_template('contributors_list.html', event=event, contributors=contributors)

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
    return render_template('contributor_view_page.html', contrib=contrib, event=event,
                            payments=payments, show_payments=show_payments)

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
    file = request.files.get('screenshot')
    text = request.form.get('payment_proof_text', '').strip()
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
    db.session.commit()
    admin = Admin.query.get(event.admin_id)
    create_notification(admin.id, f'Payment proof from {contrib.name}.', 'info', event.id, contrib.id)
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
    return render_template('contributor_login.html', event_token=event_token)

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
        contrib = Contributor(username=username, password_hash=hash_password(password), name=name, phone=phone,
                              token=token, status='pending')
        db.session.add(contrib)
        db.session.commit()
        session['contributor_id'] = contrib.id
        flash('Registered!', 'success')
        if event_token_post:
            return redirect(url_for('event_landing', token=event_token_post))
        return redirect(url_for('index'))
    return render_template('contributor_register.html', event_token=event_token)

@app.route('/contributor/logout')
def contributor_logout():
    session.pop('contributor_id', None)
    flash('Logged out.', 'info')
    return redirect(url_for('contributor_login'))

@app.route('/contributor/dashboard')
def contributor_dashboard():
    if not is_contributor_logged_in():
        flash('Please login.', 'error')
        return redirect(url_for('contributor_login'))
    contrib = get_contributor()
    if not contrib:
        session.clear()
        flash('Session invalid.', 'error')
        return redirect(url_for('contributor_login'))
    contributions = Contributor.query.filter_by(name=contrib.name, phone=contrib.phone).all()
    return render_template('contributor_dashboard.html', contrib=contrib, contributions=contributions)

@app.route('/contact', methods=['GET', 'POST'])
def contact():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip()
        phone = request.form.get('phone', '').strip()
        subject = request.form.get('subject', '').strip()
        message = request.form.get('message', '').strip()
        if not name or not email or not subject or not message:
            flash('All fields required.', 'error')
            return redirect(url_for('contact'))
        msg = ContactMessage(name=name, email=email, phone=phone, subject=subject, message=message)
        db.session.add(msg)
        db.session.commit()
        send_email(SUPPORT_EMAIL, f"[GoldenVow] {subject}", f"From: {name} <{email}>\nPhone: {phone}\n\n{message}")
        flash('Message sent!', 'success')
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

@app.route('/notifications')
def notifications():
    if not is_admin_logged_in():
        return redirect(url_for('login'))
    notifs = Notification.query.filter_by(admin_id=get_admin().id).order_by(desc(Notification.created_at)).limit(100).all()
    return render_template('notifications.html', notifications=notifs)

@app.route('/notification/<int:nid>/read', methods=['POST'])
def mark_notification_read(nid):
    return jsonify({'success': True})

@app.route('/notification/mark-all-read', methods=['POST'])
def mark_all_notifications_read():
    return jsonify({'success': True})

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
    return render_template('settings.html', maintenance_mode=maintenance_mode)

@app.route('/withdrawals')
def withdrawals():
    if not is_admin_logged_in() or not get_admin().is_super_admin:
        flash('Unauthorized.', 'error')
        return redirect(url_for('login'))
    wd_list = Withdrawal.query.order_by(desc(Withdrawal.created_at)).all()
    return render_template('withdrawals.html', withdrawals=wd_list)

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
    return render_template('help.html')

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
    flash('Toggled.', 'success')
    return redirect(url_for('manage_admins'))

@app.route('/admin/<int:aid>/delete', methods=['POST'])
def delete_admin(aid):
    flash('Not implemented.', 'info')
    return redirect(url_for('manage_admins'))

@app.route('/manage-feature-requests')
def manage_feature_requests():
    return "<h1>Feature requests</h1>"

@app.route('/feature-request', methods=['GET', 'POST'])
@app.route('/feature-request/<event_token>', methods=['GET', 'POST'])
def submit_feature_request(event_token=None):
    flash('Feature request submitted.', 'info')
    return redirect(url_for('index'))

@app.route('/contact-super', methods=['GET', 'POST'])
def contact_super():
    flash('Message sent to Super Admin.', 'info')
    return redirect(url_for('dashboard'))

@app.route('/add_testimonial/<token>', methods=['POST'])
def add_testimonial(token):
    flash('Testimonial added.', 'success')
    return redirect(url_for('event_landing', token=token))

@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    return "<h1>Forgot password – coming soon</h1>"

@app.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    return "<h1>Reset password – coming soon</h1>"

@app.route('/create_super_admin')
def create_super_admin():
    if Admin.query.count() > 0:
        return "Admin already exists. <a href='/login'>Login</a>"
    username = "super"
    password = "super123"
    admin = Admin(username=username, password_hash=hash_password(password), email="super@goldenvow.com",
                  phone="0000000000", is_super_admin=True, referral_code=generate_referral_code())
    db.session.add(admin)
    db.session.commit()
    return f"Super Admin created!<br>Username: {username}<br>Password: {password}<br><a href='/login'>Login</a>"

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
