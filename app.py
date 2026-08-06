import os, uuid, bcrypt
from datetime import datetime
from flask import Flask, render_template_string, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///database.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# ---------- MODELS ----------
class Admin(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    is_super_admin = db.Column(db.Boolean, default=False)

class Event(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    token = db.Column(db.String(100), unique=True, nullable=False)
    admin_id = db.Column(db.Integer, db.ForeignKey('admin.id'))
    title = db.Column(db.String(200), nullable=False)
    target_amount = db.Column(db.Float, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# ---------- HELPERS ----------
def hash_password(pw): return bcrypt.hashpw(pw.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
def check_password(pw, hashed): return bcrypt.checkpw(pw.encode('utf-8'), hashed.encode('utf-8'))
def generate_token(): return str(uuid.uuid4())[:12]

# ---------- TEMPLATES ----------
LANDING = """
<!DOCTYPE html>
<html><head><title>GoldenVow</title></head>
<body><h1>GoldenVow</h1><p>Welcome</p>
<a href="/login">Login</a> | <a href="/register">Register</a>
</body></html>
"""
LOGIN_PAGE = """
<!DOCTYPE html>
<html><head><title>Login</title></head>
<body>
<form method="POST">
<input type="text" name="username" placeholder="Username" required>
<input type="password" name="password" placeholder="Password" required>
<button type="submit">Login</button>
</form>
<a href="/register">Register</a>
</body></html>
"""
REGISTER_PAGE = """
<!DOCTYPE html>
<html><head><title>Register</title></head>
<body>
<form method="POST">
<input type="text" name="username" placeholder="Username" required>
<input type="password" name="password" placeholder="Password" required>
<button type="submit">Register</button>
</form>
</body></html>
"""
DASHBOARD_PAGE = """
<h1>Dashboard</h1>
<p>Welcome {{ admin.username }}</p>
<a href="/events/create">Create Event</a> | <a href="/logout">Logout</a>
"""
SUPER_DASHBOARD = """
<h1>Super Admin</h1>
<p>Welcome {{ admin.username }}</p>
<a href="/logout">Logout</a>
"""
CREATE_EVENT_PAGE = """
<form method="POST">
<input type="text" name="title" placeholder="Event Title" required>
<input type="number" name="target_amount" placeholder="Target Amount" required>
<button type="submit">Create</button>
</form>
"""

# ---------- ROUTES ----------
with app.app_context():
    db.create_all()

@app.route('/')
def index():
    if 'admin_id' in session:
        admin = Admin.query.get(session['admin_id'])
        if admin:
            if admin.is_super_admin:
                return redirect(url_for('super_dashboard'))
            return redirect(url_for('dashboard'))
    return render_template_string(LANDING)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password'].strip()
        if not username or not password:
            flash('Username/password required')
            return render_template_string(REGISTER_PAGE)
        if Admin.query.filter_by(username=username).first():
            flash('Username taken')
            return render_template_string(REGISTER_PAGE)
        is_super = Admin.query.count() == 0  # First user becomes super
        admin = Admin(username=username, password_hash=hash_password(password), is_super_admin=is_super)
        db.session.add(admin)
        db.session.commit()
        flash('Registered! Please login.')
        return redirect(url_for('login'))
    return render_template_string(REGISTER_PAGE)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password'].strip()
        admin = Admin.query.filter_by(username=username).first()
        if admin and check_password(password, admin.password_hash):
            session['admin_id'] = admin.id
            flash('Logged in')
            return redirect(url_for('index'))
        flash('Invalid credentials')
    return render_template_string(LOGIN_PAGE)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

@app.route('/dashboard')
def dashboard():
    if 'admin_id' not in session:
        return redirect(url_for('login'))
    admin = Admin.query.get(session['admin_id'])
    if not admin:
        session.clear()
        return redirect(url_for('login'))
    if admin.is_super_admin:
        return redirect(url_for('super_dashboard'))
    return render_template_string(DASHBOARD_PAGE, admin=admin)

@app.route('/super-dashboard')
def super_dashboard():
    if 'admin_id' not in session:
        return redirect(url_for('login'))
    admin = Admin.query.get(session['admin_id'])
    if not admin or not admin.is_super_admin:
        return redirect(url_for('login'))
    return render_template_string(SUPER_DASHBOARD, admin=admin)

@app.route('/events/create', methods=['GET', 'POST'])
def create_event():
    if 'admin_id' not in session:
        return redirect(url_for('login'))
    admin = Admin.query.get(session['admin_id'])
    if not admin:
        return redirect(url_for('login'))
    if request.method == 'POST':
        token = generate_token()
        event = Event(token=token, admin_id=admin.id, title=request.form['title'], target_amount=float(request.form['target_amount']))
        db.session.add(event)
        db.session.commit()
        flash('Event created')
        return redirect(url_for('dashboard'))
    return render_template_string(CREATE_EVENT_PAGE)

if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
