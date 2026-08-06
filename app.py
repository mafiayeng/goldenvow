# ==================== GoldenVow – WORKING FINAL VERSION ====================
import os, uuid, random, string
from datetime import datetime, timedelta  # ✅ FIXED: timedelta imported
from flask import Flask, render_template_string, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func
import bcrypt

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'pL3x9QmW8vN2kR5yTzH7bJ4dF6sA1cX0')
database_url = os.environ.get('DATABASE_URL')
app.config['SQLALCHEMY_DATABASE_URI'] = database_url if database_url else 'sqlite:///database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.permanent_session_lifetime = timedelta(days=30)  # ✅ Now works
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
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)

class Contributor(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey('event.id'))
    token = db.Column(db.String(100), unique=True, nullable=False)
    name = db.Column(db.String(150), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    pledge_amount = db.Column(db.Float, nullable=False)
    paid_amount = db.Column(db.Float, default=0.0)
    status = db.Column(db.String(20), default='pending')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# ---------- CREATE TABLES ----------
with app.app_context():
    db.create_all()

# ---------- HELPERS ----------
def hash_password(plain):
    return bcrypt.hashpw(plain.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def check_password(plain, hashed):
    return bcrypt.checkpw(plain.encode('utf-8'), hashed.encode('utf-8'))

def generate_unique_token():
    return str(uuid.uuid4())[:12]

def is_admin_logged_in():
    return session.get('admin_id') is not None

def get_admin():
    if not is_admin_logged_in():
        return None
    return Admin.query.get(session['admin_id'])

# ---------- HTML PAGES ----------
LOGIN_PAGE = """
<!DOCTYPE html>
<html>
<head><title>GoldenVow - Login</title>
<style>
body { background: #0b1120; color: #e2e8f0; font-family: Arial; display: flex; justify-content: center; align-items: center; height: 100vh; margin:0; }
.card { background: rgba(255,255,255,0.04); backdrop-filter: blur(12px); border-radius: 24px; padding: 40px; width: 380px; box-shadow: 0 20px 40px rgba(0,0,0,0.4); }
h1 { color: #D4AF37; text-align: center; font-size: 28px; }
input { width: 100%; padding: 12px; margin: 8px 0; border-radius: 8px; border: none; background: #1a2332; color: white; box-sizing: border-box; }
button { width: 100%; padding: 12px; background: linear-gradient(135deg, #D4AF37, #f5d06b); border: none; border-radius: 50px; font-weight: bold; color: #0b1120; font-size: 16px; cursor: pointer; }
a { color: #D4AF37; text-decoration: none; }
.alert { padding: 10px; border-radius: 8px; margin: 10px 0; }
.alert-success { background: #1a3a2a; color: #7ddfa0; }
.alert-error { background: #3a1a1a; color: #ff6b6b; }
</style>
</head>
<body>
<div class="card">
<h1>✦ GoldenVow</h1>
<h2 style="text-align:center;">Admin Login</h2>
{% with messages = get_flashed_messages(with_categories=true) %}
  {% if messages %}
    {% for category, message in messages %}
      <div class="alert alert-{{ category }}">{{ message }}</div>
    {% endfor %}
  {% endif %}
{% endwith %}
<form method="POST">
<input type="text" name="username" placeholder="Username" required>
<input type="password" name="password" placeholder="Password" required>
<button type="submit">Login</button>
</form>
<p style="text-align:center; margin-top:15px;"><a href="/register">Register</a></p>
</div>
</body>
</html>
"""

REGISTER_PAGE = """
<!DOCTYPE html>
<html>
<head><title>GoldenVow - Register</title>
<style>
body { background: #0b1120; color: #e2e8f0; font-family: Arial; display: flex; justify-content: center; align-items: center; height: 100vh; margin:0; }
.card { background: rgba(255,255,255,0.04); backdrop-filter: blur(12px); border-radius: 24px; padding: 40px; width: 380px; box-shadow: 0 20px 40px rgba(0,0,0,0.4); }
h1 { color: #D4AF37; text-align: center; font-size: 28px; }
input { width: 100%; padding: 12px; margin: 8px 0; border-radius: 8px; border: none; background: #1a2332; color: white; box-sizing: border-box; }
button { width: 100%; padding: 12px; background: linear-gradient(135deg, #D4AF37, #f5d06b); border: none; border-radius: 50px; font-weight: bold; color: #0b1120; font-size: 16px; cursor: pointer; }
a { color: #D4AF37; text-decoration: none; }
</style>
</head>
<body>
<div class="card">
<h1>✦ GoldenVow</h1>
<h2 style="text-align:center;">Register Admin</h2>
{% with messages = get_flashed_messages(with_categories=true) %}
  {% if messages %}
    {% for category, message in messages %}
      <div class="alert alert-{{ category }}">{{ message }}</div>
    {% endfor %}
  {% endif %}
{% endwith %}
<form method="POST">
<input type="text" name="username" placeholder="Username" required>
<input type="email" name="email" placeholder="Email" required>
<input type="tel" name="phone" placeholder="Phone">
<input type="password" name="password" placeholder="Password" required>
<input type="text" name="super_secret" placeholder="Super Admin Secret (if applicable)">
<button type="submit">Register</button>
</form>
<p style="text-align:center; margin-top:15px;"><a href="/login">Already have an account?</a></p>
</div>
</body>
</html>
"""

DASHBOARD_PAGE = """
<!DOCTYPE html>
<html>
<head><title>GoldenVow - Dashboard</title>
<style>
body { background: #0b1120; color: #e2e8f0; font-family: Arial; padding: 20px; }
.golden { color: #D4AF37; }
.card { background: rgba(255,255,255,0.04); backdrop-filter: blur(12px); border-radius: 24px; padding: 20px; margin: 10px 0; }
a { color: #D4AF37; text-decoration: none; }
button { background: linear-gradient(135deg, #D4AF37, #f5d06b); border: none; border-radius: 50px; padding: 10px 20px; font-weight: bold; cursor: pointer; }
</style>
</head>
<body>
<h1 class="golden">👋 Welcome, {{ admin.username }}</h1>
<div class="card">
<h3 class="golden">📋 Your Events</h3>
{% if events %}
  {% for event in events %}
  <div style="border-bottom:1px solid #222; padding:10px 0;">
  <a href="/events/{{ event.token }}"><strong>{{ event.title }}</strong></a>
  <br>Raised: KES {{ event.total_raised|round(2) }} / {{ event.target_amount|round(2) }}
  </div>
  {% endfor %}
{% else %}
<p>No events yet. Create your first event below!</p>
{% endif %}
</div>
<div class="card">
<a href="/events/create"><button>➕ Create New Event</button></a>
</div>
<p><a href="/logout">Logout</a></p>
</body>
</html>
"""

CREATE_EVENT_PAGE = """
<!DOCTYPE html>
<html>
<head><title>Create Event</title>
<style>
body { background: #0b1120; color: #e2e8f0; font-family: Arial; padding: 20px; }
.golden { color: #D4AF37; }
.card { background: rgba(255,255,255,0.04); backdrop-filter: blur(12px); border-radius: 24px; padding: 20px; margin: 10px 0; }
input, textarea { width: 100%; padding: 10px; margin: 5px 0; border-radius: 8px; border: none; background: #1a2332; color: white; box-sizing: border-box; }
button { background: linear-gradient(135deg, #D4AF37, #f5d06b); border: none; border-radius: 50px; padding: 10px 20px; font-weight: bold; cursor: pointer; }
a { color: #D4AF37; text-decoration: none; }
</style>
</head>
<body>
<h1 class="golden">✨ Create New Event</h1>
<div class="card">
<form method="POST">
<input type="text" name="title" placeholder="Event Title" required>
<textarea name="description" placeholder="Description" rows="3"></textarea>
<input type="number" name="target_amount" placeholder="Target Amount (KES)" step="0.01" required>
<input type="datetime-local" name="event_date" required>
<input type="datetime-local" name="deadline" required>
<input type="text" name="account_name" placeholder="Account Name (e.g. Alex Kiprop)" required>
<button type="submit">Create Event</button>
</form>
</div>
<a href="/dashboard">← Back to Dashboard</a>
</body>
</html>
"""

EVENT_PAGE = """
<!DOCTYPE html>
<html>
<head><title>{{ event.title }}</title>
<style>
body { background: #0b1120; color: #e2e8f0; font-family: Arial; padding: 20px; }
.golden { color: #D4AF37; }
.card { background: rgba(255,255,255,0.04); backdrop-filter: blur(12px); border-radius: 24px; padding: 20px; margin: 10px 0; }
a { color: #D4AF37; text-decoration: none; }
</style>
</head>
<body>
<h1 class="golden">{{ event.title }}</h1>
<div class="card">
<p><strong>Description:</strong> {{ event.description or 'No description' }}</p>
<p><strong>Target:</strong> KES {{ event.target_amount|round(2) }}</p>
<p><strong>Account Name:</strong> {{ event.account_name or 'Not set' }}</p>
<p><strong>Event Date:</strong> {{ event.event_date.strftime('%Y-%m-%d %H:%M') }}</p>
<p><strong>Deadline:</strong> {{ event.deadline.strftime('%Y-%m-%d %H:%M') }}</p>
<p><strong>Status:</strong> {{ 'Active' if event.is_active else 'Inactive' }}</p>
</div>
<a href="/dashboard">← Back to Dashboard</a>
</body>
</html>
"""

# ---------- ROUTES ----------
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
            flash('Logged in successfully!', 'success')
            return redirect(url_for('dashboard'))
        flash('Invalid credentials.', 'error')
    return render_template_string(LOGIN_PAGE)

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
            return render_template_string(REGISTER_PAGE)
        if Admin.query.filter_by(username=username).first():
            flash('Username taken.', 'error')
            return render_template_string(REGISTER_PAGE)
        admin = Admin(username=username, password_hash=hash_password(password), email=email, phone=phone)
        SUPER_ADMIN_SECRET = os.environ.get('SUPER_ADMIN_SECRET', 'super.mfy')
        if super_secret == SUPER_ADMIN_SECRET or Admin.query.count() == 0:
            admin.is_super_admin = True
            flash('You are the Super Admin!', 'success')
        db.session.add(admin)
        db.session.commit()
        flash('Registration successful! Please login.', 'success')
        return redirect(url_for('login'))
    return render_template_string(REGISTER_PAGE)

@app.route('/dashboard')
def dashboard():
    if not is_admin_logged_in():
        return redirect(url_for('login'))
    admin = get_admin()
    if not admin:
        return redirect(url_for('logout'))
    events = Event.query.filter_by(admin_id=admin.id).all()
    for ev in events:
        ev.total_raised = db.session.query(func.sum(Contributor.paid_amount)).filter_by(event_id=ev.id, status='approved').scalar() or 0
    return render_template_string(DASHBOARD_PAGE, admin=admin, events=events)

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
            account_name=request.form.get('account_name')
        )
        db.session.add(event)
        db.session.commit()
        flash('Event created successfully!', 'success')
        return redirect(url_for('dashboard'))
    return render_template_string(CREATE_EVENT_PAGE)

@app.route('/events/<token>')
def event_landing(token):
    event = Event.query.filter_by(token=token).first_or_404()
    return render_template_string(EVENT_PAGE, event=event)

# ---------- MAIN ----------
if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
