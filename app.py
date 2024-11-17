from flask import Flask, render_template, request, redirect, session
from flask_session import Session
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin, LoginManager, login_user, login_required, logout_user, current_user
from datetime import datetime
from flask_bcrypt import Bcrypt

app = Flask(__name__)

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///words.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'this_key'
db = SQLAlchemy(app)

app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

bcrypt = Bcrypt(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(user_id)


class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), nullable=False, unique=True)
    password = db.Column(db.String(100), nullable=False)
    role_id = db.Column(db.Integer, db.ForeignKey('role.id'))

class Role(db.Model):
    id = db.Column(db.Integer, autoincrement=True, primary_key=True)
    name = db.Column(db.String(50), nullable=False, unique=True)
    users = db.relationship('User', backref='role')

class Word(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.String(5), nullable=False, unique=True) # the word to be exact
    searched = db.Column(db.Integer, nullable=False)
    definition = db.Column(db.String(50000), nullable=True)
    last_search = db.Column(db.DateTime, nullable=True)
    last_as_word_of_the_day = db.Column(db.DateTime, nullable=True)
    last_as_word_of_literally = db.Column(db.DateTime, nullable=True)
    source = db.Column(db.String(500), nullable=False)
    added_by = db.Column(db.String(500), nullable=False)

    def to_dict(self):
        return {
            'content': self.content,
            'searched': self.searched,
            'definition': self.definition,
            'last_search': self.last_search,
            'last_as_word_of_the_day': self.last_as_word_of_the_day,
            'last_as_word_of_literally': self.last_as_word_of_literally,
            'source': self.source,
            'added_by': self.added_by
        }

class Proposal(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(5), nullable=True, unique=True)
    date = db.Column(db.DateTime, default=datetime.utcnow)
    reasoning = db.Column(db.String(5000), nullable=True)
    user = db.Column(db.String(50), nullable=False)

class History(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.DateTime, default=datetime.utcnow)
    action = db.Column(db.String(5000), nullable=False)
    user = db.Column(db.String(50), nullable=False)

# VALIDATORS
def validate_username(username):
        existing_user_username = User.query.filter_by(username=username).first()
        if existing_user_username:
            return True

def validate_word_content(content):
        existing_word_content = Word.query.filter_by(content=content).first()
        existing_proposal_content = Proposal.query.filter_by(name=content).first()
        if existing_word_content or existing_proposal_content:
            return True

# home page
@app.route('/', methods=['POST', 'GET'])
def home():
    return render_template('home.html')


# menu page
@app.route('/menu', methods=['POST', 'GET'])
@login_required
def menu():
    return render_template('menu.html')


@app.route('/logout', methods=['GET', 'POST'])
@login_required
def logout():
    logout_user()
    session.clear()
    return redirect('/')


# login page
@app.route('/login', methods=['POST', 'GET'])
def login():
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password'].strip()
        user = User.query.filter_by(username=username).first()
        if user:
            if bcrypt.check_password_hash(user.password, password):
                session['show_log_out'] = True
                session['username'] = user.username
                session['role'] = user.role_id
                login_user(user)
                return redirect('/menu')
    else:
        return render_template('login.html')

# register page
@app.route('/admin_register', methods=['POST', 'GET'])
@login_required
def admin_register():
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password'].strip()
        role_name = request.form['role'].strip()
        if validate_username(username):
            session['username_used']=True
            return render_template('admin_register.html')
        else:
            hashed_password = bcrypt.generate_password_hash(password)
            role = Role.query.filter_by(name=role_name).first()
            new_user = User(username=username, password=hashed_password, role=role)
            try:
                db.session.add(new_user)
                db.session.commit()
                session['username_used']=False
                return redirect('/menu')
            except:
                return 'There was an issue adding your test'
    else:
        return render_template('admin_register.html', show_hidden=False)


@app.route('/all_words', methods=['POST','GET'])
@login_required
def all_words():
    return render_template('all_words.html')

@app.route('/api/words_data')
@login_required
def words_data():
    return {'data': [word.to_dict() for word in Word.query]}


@app.route('/add_word', methods=['POST','GET'])
@login_required
def add_word():
    if request.method == 'POST':
        content = request.form['content'].strip()
        searched = 0
        definition = request.form['definition'].strip()
        source = "Added by user"
        added_by = session['username']
        if validate_word_content(content):
            session['word_already_exists']=True
            return render_template('add_word.html')
        else:
            if 1 == session['role']:
                new_word = Word(content=content, searched=searched, definition=definition, source=source, added_by=added_by)
            else:
                new_word = Proposal(name=content, reasoning=definition, user=added_by)
            try:
                db.session.add(new_word)
                db.session.commit()
                session['word_already_exists']=False
                return redirect('/menu')
            except:
                return 'There was an issue adding your test'
    else:
        session['word_already_exists']=False
        return render_template('add_word.html')

@app.route('/all_proposals')
@login_required
def proposals():
    proposals = Proposal.query.order_by(Proposal.date).all()
    return render_template('all_proposals.html', proposals=proposals)

@app.route('/delete/proposal_<int:id>')
@login_required
def delete_proposal(id):
    if current_user.role_id != 2:
        proposal_to_delete = Proposal.query.get_or_404(id)
        try:
            db.session.delete(proposal_to_delete)
            db.session.commit()
            proposals = Proposal.query.all()
            if len(proposals) > 0:
                return redirect('/all_proposals')
            else:
                return redirect('/menu')
        except:
            return render_template('error_page.html', message="[?] There was an issue deleting that proposal")
    else:
        return render_template('error_page.html', message='[!] You do not have permission to delete proposals')

@app.route('/show/proposal_<int:id>')
@login_required
def show_proposal(id):
    proposal_to_show = Proposal.query.get_or_404(id)
    return render_template('show_proposal.html', proposal=proposal_to_show)

@app.route('/big_search', methods=['POST','GET'])
@login_required
def big_search():
    return render_template('big_search.html')

@app.route('/all_users', methods=['POST','GET'])
@login_required
def all_users():
    users = User.query.order_by(User.username).all()
    if current_user.role_id == 1:
        x = current_user.role_id
        return render_template('all_users.html', users=users, id=x)




if __name__ == "__main__":
    app.run('0.0.0.0', port=80, debug=True)