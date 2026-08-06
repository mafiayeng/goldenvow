# ==================== GoldenVow – NO TEMPLATES NEEDED ====================
import os, uuid, random, string, io, secrets
from datetime import datetime, timedelta
from flask import Flask, render_template_string, request, redirect, url_for, session, flash, jsonify, send_file
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import desc, func, inspect
import bcrypt

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'pL3x9QmW8vN2kR5yTzH7bJ4dF6sA1cX0')
database_url = os.environ.get('DATABASE_URL')
app.config['SQLALCHEMY_DATABASE_URI'] = database_url if database_url else 'sqlite:///database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.permanent_session_lifetime = timedelta(days=30)
db = SQLAlchemy(app)

# ---------- MODELS ----------
class Admin(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    email = db.Column(db.String(100))
    phone = db.Column(db.String(20))
    is_super_admin = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True)
    referral_code = db.Column(db.String(20), unique=True, nullable=False, default='')
    referral_count = db.Column(db.Integer, default=0)

class Event(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    token = db.Column(db.String(100), unique=True, nullable=False)
    admin_id = db.Column(db.Integer, db.ForeignKey('admin.id'))
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    target_amount = db.Column(db.Float, nullable=False)
    deadline = db.Column(db.DateTime, nullable=False)
    event_date = db.Column(db.DateTime, nullable=False)
    account_name = db.Column(db.String(150), nullable=True)
    paybill = db.Column(db.String(50))
    mpesa_number = db.Column(db.String(20))
    till_number = db.Column(db.String(50))
    bank_name = db.Column(db.String(100))
    bank_account_name = db.Column(db.String(100))
    bank_account_number = db.Column(db.String(50))
    payment_instructions = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)
    first_contribution_date = db.Column(db.DateTime, nullable=True)
    fee_paid = db.Column(db.Boolean, default=False)
    disabled = db.Column(db.Boolean, default=False)

class Contributor(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey('event.id'))
    token = db.Column(db.String(100), unique=True, nullable=False)
    name = db.Column(db.String(150), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    pledge_amount = db.Column(db.Float, nullable=False)
    fee_amount = db.Column(db.Float, default=0.0)
    paid_amount = db.Column(db.Float, default=0.0)
    status = db.Column(db.String(20), default='pending')
    sender_name = db.Column(db.String(150), nullable=True)
    auto_verified = db.Column(db.Boolean, default=False)
    payment_proof_screenshot = db.Column(db.String(500))
    payment_proof_text = db.Column(db.Text)
    completed_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Payment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    contributor_id = db.Column(db.Integer, db.ForeignKey('contributor.id'))
    amount = db.Column(db.Float, nullable=False)
    date_paid = db.Column(db.DateTime, default=datetime.utcnow)

# ---------- HELPERS ----------
def hash_password(plain):
    return bcrypt.hashpw(plain.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def check_password(plain, hashed):
    return bcrypt.checkpw(plain.encode('utf-8'), hashed.encode('utf-8'))

def generate_unique_token():
    return str(uuid.uuid4())[:12]

def generate_referral_code():
    return f"GV-{''.join(random.choices(string.ascii_uppercase + string.digits, k=6))}"

def is_admin_logged_in():
    return session.get('admin_id') is not None

def get_admin():
    if not is_admin_logged_in():
        return None
    return Admin.query.get(session['admin_id'])

def is_super_admin():
    admin = get_admin()
    return admin and admin.is_super_admin

# ---------- ROUTES WITH INLINE HTML ----------
LOGIN_HTML = """
<!DOCTYPE html>
<html>
<head><title>GoldenVow - Login</title>
<style>
body { background: #0b1120; color: #e2e8f0; font-family: Arial; display: flex; justify-content: center; align-items: center; height: 100vh; }
.card { background: rgba(255,255,255,0.04); backdrop-filter: blur(12px); border-radius: 24px; padding: 40px; width: 400px; box-shadow: 0 20px 40px rgba(0,0,0,0.4); }
h1 { color: #D4AF37; text-align: center; }
input { width: 100%; padding: 12px; margin: 10px 0; border-radius: 8px; border: none; background: #1a2332; color: white; }
button { width: 100%; padding: 12px; background: linear-gradient(135deg, #D4AF37, #f5d06b); border: none; border-radius: 50px; font-weight: bold; color: #0b1120; }
a { color: #D4AF37; }
</style>
</head>
<body>
<div class="card">
<h1>✦ GoldenVow</h1>
<h2>Admin Login</h2>
<form method="POST">
<input type="text" name="username" placeholder="Username" required>
<input type="password" name="password" placeholder="Password" required>
<button type="submit">Login</button>
</form>
<p style="text-align:center; margin-top:20px;"><a href="/register">Register</a> | <a href="/contributor/login">Contributor Login</a></p>
</div>
</body>
</html>
"""

REGISTER_HTML = """
<!DOCTYPE html>
<html>
<head><title>GoldenVow - Register</title>
<style>
body { background: #0b1120; color: #e2e8f0; font-family: Arial; display: flex; justify-content: center; align-items: center; height: 100vh; }
.card { background: rgba(255,255,255,0.04); backdrop-filter: blur(12px); border-radius: 24px; padding: 40px; width: 400px; box-shadow: 0 20px 40px rgba(0,0,0,0.4); }
h1 { color: #D4AF37; text-align: center; }
input { width: 100%; padding: 12px; margin: 10px 0; border-radius: 8px; border: none; background: #1a2332; color: white; }
button { width: 100%; padding: 12px; background: linear-gradient(135deg, #D4AF37, #f5d06b); border: none; border-radius: 50px; font-weight: bold; color: #0b1120; }
a { color: #D4AF37; }
</style>
</head>
<body>
<div class="card">
<h1>✦ GoldenVow</h1>
<h2>Register Admin</h2>
<form method="POST">
<input type="text" name="username" placeholder="Username" required>
<input type="email" name="email" placeholder="Email" required>
<input type="tel" name="phone" placeholder="Phone">
<input type="password" name="password" placeholder="Password" required>
<input type="text" name="super_secret" placeholder="Super Admin Secret (if applicable)">
<button type="submit">Register</button>
</form>
<p style="text-align:center; margin-top:20px;"><a href="/login">Already have an account?</a></p>
</div>
</body>
</html>
"""

DASHBOARD_HTML = """
<!DOCTYPE html>
<html>
<head><title>GoldenVow - Dashboard</title>
<style>
body { background: #0b1120; color: #e2e8f0; font-family: Arial; padding: 20px; }
.golden { color: #D4AF37; }
.card { background: rgba(255,255,255,0.04); backdrop-filter: blur(12px); border-radius: 24px; padding: 20px; margin: 10px 0; box-shadow: 0 20px 40px rgba(0,0,0,0.4); }
a { color: #D4AF37; text-decoration: none; }
</style>
</head>
<body>
<h1 class="golden">👋 Welcome, {{ admin.username }}</h1>
<div class="card">
<h3 class="golden">Your Events</h3>
<ul>
{% for event in events %}
<li><a href="/events/{{ event.token }}">{{ event.title }}</a> - Raised: KES {{ event.total_raised|round(2) }} / {{ event.target_amount|round(2) }}</li>
{% endfor %}
</ul>
<a href="/events/create">+ Create New Event</a>
</div>
<p><a href="/logout">Logout</a></p>
</body>
</html>
"""

@app.route('/')
def index():
    if is_admin_logged_in():
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        admin = Admin.query.filter_by(username=username, is_active=True).first()
        if admin and check_password(password, admin.password_hash):
            session['admin_id'] = admin.id
            flash('Logged in.', 'success')
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
        if not username or not password:
            flash('Username and password required.', 'error')
            return render_template_string(REGISTER_HTML)
        if Admin.query.filter_by(username=username).first():
            flash('Username taken.', 'error')
            return render_template_string(REGISTER_HTML)
        referral_code = generate_referral_code()
        while Admin.query.filter_by(referral_code=referral_code).first():
            referral_code = generate_referral_code()
        admin = Admin(username=username, password_hash=hash_password(password), email=email, phone=phone,
                      referral_code=referral_code)
        # Check super admin secret
        SUPER_ADMIN_SECRET = os.environ.get('SUPER_ADMIN_SECRET', 'changeme')
        if super_secret == SUPER_ADMIN_SECRET or Admin.query.count() == 0:
            admin.is_super_admin = True
            flash('You are the Super Admin!', 'success')
        db.session.add(admin)
        db.session.commit()
        flash('Registration successful! Login.', 'success')
        return redirect(url_for('login'))
    return render_template_string(REGISTER_HTML)

@app.route('/dashboard')
def dashboard():
    if not is_admin_logged_in():
        return redirect(url_for('login'))
    admin = get_admin()
    events = Event.query.filter_by(admin_id=admin.id).all()
    # Add total raised for each event
    for ev in events:
        ev.total_raised = db.session.query(func.sum(Contributor.paid_amount)).filter_by(event_id=ev.id, status='approved').scalar() or 0
    return render_template_string(DASHBOARD_HTML, admin=admin, events=events)

@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out.', 'info')
    return redirect(url_for('login'))

@app.route('/events/create', methods=['GET', 'POST'])
def create_event():
    if not is_admin_logged_in():
        return redirect(url_for('login'))
    admin = get_admin()
    if admin.is_super_admin:
        flash('Super admins cannot create events. Use a normal admin account.', 'error')
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        # Basic creation (simplified)
        token = generate_unique_token()
        while Event.query.filter_by(token=token).first():
            token = generate_unique_token()
        event = Event(
            token=token,
            admin_id=admin.id,
            title=request.form.get('title'),
            description=request.form.get('description'),
            target_amount=float(request.form.get('target_amount', 0)),
            deadline=datetime.strptime(request.form.get('deadline'), '%Y-%m-%dT%H:%M'),
            event_date=datetime.strptime(request.form.get('event_date'), '%Y-%m-%dT%H:%M'),
            account_name=request.form.get('account_name'),
            paybill=request.form.get('paybill'),
            mpesa_number=request.form.get('mpesa_number'),
            till_number=request.form.get('till_number'),
            bank_name=request.form.get('bank_name'),
            bank_account_name=request.form.get('bank_account_name'),
            bank_account_number=request.form.get('bank_account_number'),
            payment_instructions=request.form.get('payment_instructions')
        )
        db.session.add(event)
        db.session.commit()
        flash('Event created!', 'success')
        return redirect(url_for('dashboard'))
    # Simple HTML form for create event
    return '''
    <!DOCTYPE html>
    <html>
    <head><title>Create Event</title>
    <style>
    body { background: #0b1120; color: #e2e8f0; font-family: Arial; padding: 20px; }
    .card { background: rgba(255,255,255,0.04); backdrop-filter: blur(12px); border-radius: 24px; padding: 20px; margin: 10px 0; }
    input, textarea { width: 100%; padding: 10px; margin: 5px 0; border-radius: 8px; border: none; background: #1a2332; color: white; }
    button { background: linear-gradient(135deg, #D4AF37, #f5d06b); border: none; border-radius: 50px; padding: 10px 20px; font-weight: bold; }
    </style>
    </head>
    <body>
    <h1 class="golden">Create Event</h1>
    <div class="card">
    <form method="POST">
    <input type="text" name="title" placeholder="Event Title" required>
    <textarea name="description" placeholder="Description"></textarea>
    <input type="number" name="target_amount" placeholder="Target Amount" step="0.01" required>
    <input type="datetime-local" name="event_date" required>
    <input type="datetime-local" name="deadline" required>
    <input type="text" name="account_name" placeholder="Account Name (e.g. Alex Kiprop)" required>
    <input type="text" name="paybill" placeholder="Paybill">
    <input type="text" name="mpesa_number" placeholder="M-Pesa Number">
    <input type="text" name="till_number" placeholder="Till Number">
    <input type="text" name="bank_name" placeholder="Bank Name">
    <input type="text" name="bank_account_name" placeholder="Bank Account Name">
    <input type="text" name="bank_account_number" placeholder="Bank Account Number">
    <textarea name="payment_instructions" placeholder="Payment Instructions"></textarea>
    <button type="submit">Create Event</button>
    </form>
    </div>
    <a href="/dashboard">Back to Dashboard</a>
    </body>
    </html>
    '''

@app.route('/events/<token>')
def event_landing(token):
    event = Event.query.filter_by(token=token).first_or_404()
    return f"<h1>{event.title}</h1><p>{event.description}</p><p>Account: {event.account_name}</p>"

# ---------- MAIN ----------
if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
