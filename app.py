from flask import Flask, render_template, request, redirect, session, url_for, jsonify, current_app
from flask_session import Session
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func, desc
from flask_login import UserMixin, LoginManager, login_user, login_required, logout_user, current_user
from datetime import datetime, timedelta
import pytz
from flask_bcrypt import Bcrypt
import requests
from collections import defaultdict
from bokeh.embed import components
from bokeh.plotting import figure
from random import choice
import math

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

POLAND_TZ = pytz.timezone('Europe/Warsaw')

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(user_id)


###################################################################################################################################
#   Database - data schema classes
###################################################################################################################################

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), nullable=False, unique=True)
    password = db.Column(db.String(100), nullable=False)
    role_id = db.Column(db.Integer, db.ForeignKey('role.id'))
    notifications = db.relationship('NotificationToUser', backref='user')

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
    upvoted = db.Column(db.Integer, nullable=False, default=1)

class History(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    flag = db.Column(db.String(3), db.ForeignKey('flags.name'))
    date = db.Column(db.DateTime, default=datetime.utcnow)
    title = db.Column(db.String(5000), nullable=False)
    description = db.Column(db.String(5000), nullable=True)
    user = db.Column(db.String(50), nullable=False)

class Flags(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(3), nullable=False)
    description = db.Column(db.String(5000), nullable=False)
    events = db.relationship('History', backref='flags')

class NotificationToUser(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    notifications_ids = db.Column(db.String(5000), nullable=True)

class Notifications(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(5000), nullable=False)
    description = db.Column(db.String(5000), nullable=True)
    back_reference = db.Column(db.String(5000), nullable=True)

###################################################################################################################################
#   Validators
###################################################################################################################################

# validate occupation of username
def validate_username(username):
        existing_user_username = User.query.filter_by(username=username).first()
        if existing_user_username:
            return True


# validate if such proposition exists in database Word or Proposal columns
def validate_word_content(content):
        existing_word_content = Word.query.filter_by(content=content).first()
        if existing_word_content:
            return True


# validate if such proposition exists in database Word or Proposal columns
def validate_proposal_content(content):
    existing_proposal_content = Proposal.query.filter_by(name=content).first()
    if existing_proposal_content:
        return True
        

###################################################################################################################################
#   Error handling
###################################################################################################################################


# function to log errors in History table
@app.route('/log_event', methods=['POST'])
def log_event():
    try:
        data = request.get_json()

        flag = data.get('flag')
        title = data.get('title')
        description = data.get('description')
        username = data.get('username', 'unknown')
        timestamp = data.get('timestamp', datetime.now(POLAND_TZ).isoformat())

        new_event = History(
            flag=flag,
            title=title,
            description=description,
            user=username,
            date=datetime.fromisoformat(timestamp)
        )

        db.session.add(new_event)
        db.session.commit()

        return jsonify({"message": "Error logged successfully"}), 201

    except Exception as e:
        db.session.rollback()
        log_events(flag='ER?', title='Unknown error while logging events', description=e)
        return jsonify({"error": f"Failed to log error: {str(e)}"}), 500


def log_events(flag, title, description):
    payload = {
            "flag": flag,
            "title": title,
            "description": str(description) if description else None,
            "username": session.get('username', 'unknown'),
            "timestamp": datetime.now(POLAND_TZ).isoformat()
        }
    try:
        response = requests.post("http://127.0.0.1:80/log_event", json=payload)
        response.raise_for_status()
    except requests.exceptions.RequestException as req_e:
        current_app.logger.error(f"Failed to make a call to logging endpoint: {req_e}")


###################################################################################################################################
#   Word of the day
###################################################################################################################################

@app.route('/see_word_of_the_day', methods=['GET'])
@login_required
def see_word_of_the_day():
    try:
        call_for_word_of_the_day()
        today = datetime.now(POLAND_TZ).date()
        word_to_show = db.session.query(Word).filter(Word.last_as_word_of_the_day != None).order_by(Word.last_as_word_of_the_day.desc()).first()
        
        if today != word_to_show.last_as_word_of_the_day.date():
            title = 'There was an issue while looking for word of the day'
            log_events(flag='ER?', title=title, description=e)
            return render_template('error_page.html', message=title)
        else:
            todays_last_as_word_of_literally = False
            previous_page = 'word_of_the_day'
            title = 'Word of the day!'
            word_to_show.searched += 1
            try:
                db.session.commit()
                log_events(flag='SRC', title=f'Searched for word with {word_to_show.content}', description=None)
                return render_template('show_word.html', word=word_to_show, previous_page=previous_page, todays_last_as_word_of_literally=todays_last_as_word_of_literally, title=title)
            except Exception as e:
                db.session.rollback()
                title = f'There was an issue looking up for word: {word_to_show.content}'
                log_events(flag='ER?', title=title, description=e)
                return render_template('error_page.html', message=title)
    except Exception as e:
        title = 'There was an issue while looking for word of the day'
        log_events(flag='ER?', title=title, description=e)
        return render_template('error_page.html', message=title)


@app.route('/set_word_of_the_day', methods=['GET', 'POST'])
def set_word_of_the_day():
    today = datetime.now(POLAND_TZ).date()
    yesterday = today - timedelta(days=1)

    recent_word = db.session.query(Word).filter(Word.last_as_word_of_the_day != None).order_by(Word.last_as_word_of_the_day.desc()).first()

    if recent_word and recent_word.last_as_word_of_the_day.date() == today:
        return jsonify({"message": "Today's word of the day is already set."}), 200

    if recent_word and recent_word.last_as_word_of_the_day.date() == yesterday:
        available_words = db.session.query(Word).filter(Word.last_as_word_of_the_day == None).all()
        if available_words:
            random_word = choice(available_words)
            random_word.last_as_word_of_the_day = today
            db.session.commit()
            return jsonify({"message": "Word for today has been set."}), 200

    if recent_word and recent_word.last_as_word_of_the_day.date() < yesterday:
        date_to_assign = recent_word.last_as_word_of_the_day.date() + timedelta(days=1)
        available_words = db.session.query(Word).filter(Word.last_as_word_of_the_day == None).all()

        while available_words:
            random_word = choice(available_words)
            random_word.last_as_word_of_the_day = date_to_assign
            db.session.commit()

            if date_to_assign == today:
                break

            date_to_assign += timedelta(days=1)

            available_words = db.session.query(Word).filter(Word.last_as_word_of_the_day == None).all()

        return jsonify({"message": f"Word of the day has been set from {recent_word.last_as_word_of_the_day.date()} to today."}), 200

    available_words = db.session.query(Word).filter(Word.last_as_word_of_the_day == None).all()
    if available_words:
        random_word = choice(available_words)
        random_word.last_as_word_of_the_day = today
        db.session.commit()
        return jsonify({"message": f"Word of the day has been set to {random_word.content}."}), 200
    else:
        return jsonify({"error": "No words available for setting as word of the day."}), 404


# Funkcja, która wywołuje /set_word_of_the_day
def call_for_word_of_the_day():
    word_today = Word.query.filter(func.date(Word.last_as_word_of_the_day) == datetime.now(POLAND_TZ).date()).all()
    if word_today:
        return None
    try:
        response = requests.post("http://127.0.0.1:80/set_word_of_the_day")
        response.raise_for_status()
    except Exception as e:
        title = 'There was an issue with choosing word of the day'
        log_events(flag='ER?', title=title, description=e)
        return render_template('error_page.html', message=title)


###################################################################################################################################
#   Main pages
###################################################################################################################################


# home page
@app.route('/', methods=['POST', 'GET'])
def home():
    return render_template('home.html')


# menu page
@app.route('/menu', methods=['GET'])
@login_required
def menu():
    return render_template('menu.html')


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
                login_user(user)
                log_events(flag='ENT', title='User log in', description=None)
                try:
                    call_for_word_of_the_day()
                    session['username_used']=False
                    return redirect('/menu')
                except Exception as e:
                    db.session.rollback()
                    title = "There was an issue logging in"
                    log_events(flag='ER?', title=title, description=e)
                    return render_template('error_page.html', message=title)
            else:
                return render_template('login.html', y=True, x=False)
        else:
            return render_template('login.html', x=True, y=False)
    else:
        return render_template('login.html', x=False, y=False)


@app.route('/logout', methods=['GET'])
@login_required
def logout():
    try:
        log_events("ENT", 'User log out', None)
        session['username_used']=False
        logout_user()
        session.clear()
        return redirect('/')
    except Exception as e:
        title = 'There was an issue logging out'
        log_events(flag='ER?', title=title, description=e)
        return render_template('error_page.html', message=title)


###################################################################################################################################
#   Users module
###################################################################################################################################


# register page
@app.route('/admin_register', methods=['POST', 'GET'])
@login_required
def admin_register():
    if 1 == current_user.role_id:
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
                log_events(flag='CRU', title=f'Create new user', description=f'Created user is named: {new_user.username}')
                try:
                    db.session.add(new_user)
                    db.session.commit()
                    session['username_used']=False
                    return redirect('/menu')
                except Exception as e:
                    db.session.rollback()
                    title = 'There was an issue adding new user'
                    log_events(flag='ER?', title=title, description=e)
                    return render_template('error_page.html', message=title)
        else:
            return render_template('admin_register.html', show_hidden=False)
    else:
        title = 'permission to add new users'
        log_events(flag='ER!', title=f'No {title}', description=None)
        return render_template('error_page.html', message=f'You dont have {title}')


# page to show list of all users
@app.route('/all_users', methods=['POST','GET'])
@login_required
def all_users():
    if 1 == current_user.role_id:
        users = User.query.order_by(User.username).all()
        return render_template('all_users.html', users=users, id=current_user.id)
    else:
        title = 'permission to see the list of users'
        log_events(flag='ER!', title=f'No {title}', description=None)
        return render_template('error_page.html', message=f'You dont have {title}')


@app.route('/update/user_<int:id>', methods=['GET', 'POST'])
@login_required
def update_user(id):
    if 1 == current_user.role_id:
        user_to_update = User.query.get_or_404(id)
        message = f'Updating user named: {user_to_update.username}.'
        if request.method == 'POST':
            role_id = int(request.form['role'].strip())

            if role_id != user_to_update.role_id:
                role = Role.query.get_or_404(role_id)
                message += f' Role changed to {role.name}.'

            user_to_update.role_id = role_id

            log_events(flag='ETU', title='Edit user', description=message)
            try:
                db.session.commit()
                session['repited_user'] = False
                return redirect('/all_users')
            except Exception as e:
                db.session.rollback()
                title = 'There was an issues updating user'
                log_events(flag='ER?', title=title, description=e)
                return render_template('error_page.html', message=title)
        else:
            return render_template('update_user.html', user=user_to_update)
    else:
        title = 'permission to edit users'
        log_events(flag='ER!', title=f'No {title}', description=None)
        return render_template('error_page.html', message=f'You dont have {title}')


# page where we delete user from database
@app.route('/delete/user_<int:id>')
@login_required
def delete_user(id):
    if current_user.id != id:
        if 1 == current_user.role_id:
            user_to_delete = User.query.get_or_404(id)
            try:
                db.session.delete(user_to_delete)
                db.session.commit()
                users = User.query.all()
                log_events(flag='DEL', title='Delete user', description=f'Deleted user named: {user_to_delete.username}')
                if len(users) > 0:
                    return redirect('/all_users')
                else:
                    return redirect('/menu')
            except Exception as e:
                db.session.rollback()
                title = 'There was an issue deleting that user'
                log_events(flag='ER?', title=title, description=e)
                return render_template('error_page.html', message=title)
        else:
            title = 'permission to delete users'
            log_events(flag='ER!', title=f'No {title}', description=None)
            return render_template('error_page.html', message=f'You do not have {title}')
    else:
        title = 'annot delete own user'
        log_events(flag='ER!', title=f'C{title}', description=None)
        return render_template('error_page.html', message=f'You c{title}')


@app.route('/edit_account', methods=['GET', 'POST'])
@login_required
def edit_account():
        user_to_update = User.query.get_or_404(current_user.id)
        message = f'Updating user named: {user_to_update.username}.'
        if request.method == 'POST':
            username = request.form['username'].strip()
            new_password = request.form['password'].strip()

            if username != user_to_update.username:
                validate_name = validate_username(username)
                if validate_name:
                    session['repited_user'] = True
                    message += f' Changed name to {username}.'
                    return render_template('edit_account.html', user=user_to_update, message='[!] This username is already taken.')

            user_to_update.username = username
            if new_password:
                new_password_hashed = bcrypt.generate_password_hash(new_password)
                user_to_update.password = new_password_hashed
                message += f' Changed password.'

            log_events(flag='ETU', title='Edit user', description=message)
            try:
                db.session.commit()
                session['repited_user'] = False
                return redirect('/menu')
            except Exception as e:
                db.session.rollback()
                title = 'There was an issues updating user'
                log_events(flag='ER?', title=title, description=e)
                return render_template('error_page.html', message=title)
        else:
            return render_template('edit_account.html', user=user_to_update)


###################################################################################################################################
#   Words module
###################################################################################################################################

# WORDS

# page to show list of all words
@app.route('/all_words', methods=['POST','GET'])
@login_required
def all_words():
    try:
        return render_template('all_words.html')
    except Exception as e:
        title = 'Unknown error while showing list of words'
        log_events(flag='ER?', title=title, description=e)
        return render_template('error_page.html', message=title)


# get data for all_words page
@app.route('/api/words_data')
@login_required
def words_data():
    return {'data': [word.to_dict() for word in Word.query]}


# page to add new word to database
@app.route('/add_word', methods=['POST','GET'])
@login_required
def add_word():
    if request.method == 'POST':
        content = request.form['content'].strip()
        searched = 0
        definition = 'brak' if len(request.form['definition'].strip()) == 0 else request.form['definition'].strip()
        source = "Added by user"
        added_by = session['username']
        if validate_word_content(content):
            session['word_already_exists']=True
            return render_template('add_word.html')
        else:
            if 1 == current_user.role_id:
                x = True
                new_record = Word(content=content, searched=searched, definition=definition, source=source, added_by=added_by)
            else:
                if validate_proposal_content(content):
                    x = None
                    existing_proposal = Proposal.query.filter_by(name=content).first()
                    new_reasoning = f"[{existing_proposal.user}]:\n{existing_proposal.reasoning}\n[{session['username']}]: \n{definition}"
                    if not (len(new_reasoning) > 5000):
                        existing_proposal.reasoning = new_reasoning
                    existing_proposal.user = session['username']
                    existing_proposal.upvoted += 1
                else:
                    x = False
                    new_record = Proposal(name=content, reasoning=definition, user=added_by)
            try:
                if True == x:
                    db.session.add(new_record)
                    log_events(flag='CRW', title=f'Added new word: {content}', description=None)
                elif False == x:
                    db.session.add(new_record)
                    log_events(flag='CRP', title=f'Added new proposal for: {content}', description=None)
                else:
                    log_events(flag='CRP', title=f'Upvoted proposal for: {content}', description=None)
                db.session.commit()
                session['word_already_exists']=False
                return redirect('/menu')
            except Exception as e:
                db.session.rollback()
                title = f'There was an issue adding word/proposal: {content}'
                log_events(flag='ER?', title=title, description=e)
                return render_template('error_page.html', message=title)
    else:
        session['word_already_exists']=False
        return render_template('add_word.html')


@app.route('/edit_word_<int:id>', methods=['GET', 'POST'])
@login_required
def edit_word(id):
    if 1 == current_user.role_id:
        word_to_edit = Word.query.get_or_404(id)
        if request.method == 'POST':
            try:
                word_to_edit.searched = request.form.get('searched', word_to_edit.searched)
                word_to_edit.definition = request.form.get('definition', word_to_edit.definition)
                word_to_edit.source += f" Also changed by {session['username']}"

                if 'clear_last_as_word' in request.form:
                    word_to_edit.last_as_word_of_literally = None

                log_events(flag='ETW', title=f'Edited word: {word_to_edit.content}', description=None)
                db.session.commit()

                return redirect(url_for('big_search'))

            except Exception as e:
                db.session.rollback()
                title = f'There was an issue updating this word: {word_to_edit.content}'
                log_events(flag='ER?', title=title, description=e)
                return render_template('error_page.html', message=title)
        else:
            return render_template('edit_word.html', word=word_to_edit)
    else:
        title = "permission to edit words"
        log_events(flag='ER!', title=f'No {title}', description=None)
        return render_template('error_page.html', message=f'You dont have {e}')



@app.route('/word_of_literally/<int:id>')
@login_required
def word_of_literally(id):
    if current_user.role_id != 3:
        word_to_edit = Word.query.get_or_404(id)
        word_today = Word.query.filter(func.date(Word.last_as_word_of_literally) == datetime.now(POLAND_TZ).date()).first()
        if word_today:
            description = f"Word of the literally has been found for today and it is {word_today.content}"
            log_events(flag='LG!', title='Logic error', description=description)
            return render_template('error_page.html', message=description)
        else:
            if word_to_edit:
                word_to_edit.last_as_word_of_literally = datetime.now(POLAND_TZ)
                try:
                    db.session.commit()
                    log_events(flag='ETW', title='Logic error', description=f'Word {word_to_edit.content} has been marked as word of literally')
                    return render_template('loading_page.html')
                except Exception as e:
                    db.session.rollback()
                    title = "There was an issue adding word as word of literally"
                    log_events(flag='ER?', title=title, description=None)
                    return render_template('error_page.html', message=title)
            else:
                titlee = "There is something wrong with this word"
                log_events(flag='ER?', title=title, description=None)
                return render_template('error_page.html', message=title)
    else:
        title = 'permission to mark word'
        log_events(flag='ER?', title=f'No {title}', description=None)
        return render_template('error_page.html', message=f'You dont have {title}')


# PROPOSALS

@app.route('/all_proposals')
@login_required
def proposals():
    if 1 == current_user.role_id:
        try:
            proposals = Proposal.query.order_by(Proposal.date).all()
            return render_template('all_proposals.html', proposals=proposals)
        except Exception as e:
            title = 'Unknown error while displaying proposals'
            log_events(flag='ER?', title=title, description=e)
            return render_template('error_page.html', message=title)
    else:
        title = "permission to see list of proposals"
        log_events(flag='ER!', title=f'No {title}', description=None)
        return render_template('error_page.html', message=f'You dont have {title}')


@app.route('/delete/proposal_<int:id>')
@login_required
def delete_proposal(id):
    if 1 == current_user.role_id:
        proposal_to_delete = Proposal.query.get_or_404(id)
        try:
            db.session.delete(proposal_to_delete)
            db.session.commit()
            proposals = Proposal.query.all()
            log_events(flag='DEL', title=f'Deleted proposal : {proposal_to_delete.name}', description=None)
            if len(proposals) > 0:
                return redirect('/all_proposals')
            else:
                return redirect('/menu')
        except Exception as e:
            db.session.rollback()
            title = "There was an issue deleting proposal"
            log_events(flag='ER?', title=title, description=e)
            return render_template('error_page.html', message=title)
    else:
        title = 'permission to delete proposals'
        log_events(flag='ER!', title=f'No {title}', description=None)
        return render_template('error_page.html', message=f'You dont have {title}')


@app.route('/show/proposal_<int:id>')
@login_required
def show_proposal(id):
    if 1 == current_user.role_id:
        try:
            proposal_to_show = Proposal.query.get_or_404(id)
            return render_template('show_proposal.html', proposal=proposal_to_show)
        except Exception as e:
            title = "There was a problem looking for this proposal"
            log_events(flag='ER?', title=title, description=e)
            return render_template('error_page.html', message=title)
    else:
        title = "permission to look into proposals"
        log_events(flag='ER!', title=f'No {title}', description=None)
        return render_template('error_page.html', message=f'You dont have {title}')


@app.route('/accept_proposal_<int:id>', methods=['POST','GET'])
@login_required
def accept_proposal(id):
    if 1 == current_user.role_id:
        proposal_to_delete = Proposal.query.get_or_404(id)
        content = proposal_to_delete.name
        searched = 0
        definition = proposal_to_delete.reasoning
        source = "Added by user, accepted by one of admins"
        added_by = proposal_to_delete.user
        new_word = Word(content=content, searched=searched, definition=definition, source=source, added_by=added_by)
        try:
            db.session.delete(proposal_to_delete)
            db.session.add(new_word)
            db.session.commit()
            log_events(flag='ACP', title=f'Accept proposal : {content}', description=None)
            proposals = Proposal.query.all()
            if len(proposals) > 0:
                return redirect('/all_proposals')
            else:
                return redirect('/menu')
        except Exception as e:
            db.session.rollback()
            title = "There was an issue accepting that proposal"
            log_events(flag='ER?', title=title, description=None)
            return render_template('error_page.html', message=title)
    else:
        title = 'permission to accept proposals'
        log_events(flag='ER!', title=f'No {title}', description=None)
        return render_template('error_page.html', message=f'You dont have {title}')


# WORD SEARCH


@app.route('/big_search', methods=['POST', 'GET'])
@login_required
def big_search():
    if request.method == 'POST':
        include_filter = request.form.get('includeFilter', '').lower()
        not_in_word_filter = request.form.get('notInWordFilter', '').lower()
        exact_place_filters = [
            request.form.get('exactPlaceFilter1', '').lower(),
            request.form.get('exactPlaceFilter2', '').lower(),
            request.form.get('exactPlaceFilter3', '').lower(),
            request.form.get('exactPlaceFilter4', '').lower(),
            request.form.get('exactPlaceFilter5', '').lower()
        ]

        if not include_filter and not not_in_word_filter and all(not filter for filter in exact_place_filters):
            return render_template('big_search.html', x=True)
        else:
            exact_place_str = ",".join(exact_place_filters)
            return redirect(url_for('found_words', 
                                    includeFilter=include_filter, 
                                    notInWordFilter=not_in_word_filter,
                                    exactPlaceFilters=exact_place_str))
    return render_template('big_search.html')


@app.route('/found_words', methods=['GET'])
@login_required
def found_words():
    include_filter = request.args.get('includeFilter', '').lower()
    not_in_word_filter = request.args.get('notInWordFilter', '').lower()
    exact_place_str = request.args.get('exactPlaceFilters', '').lower()

    exact_place_filters = exact_place_str.split(',')
    filters = ''
    query = Word.query

    if include_filter:
        filters += '[Letters word include filter]'
        for letter in include_filter.split('-'):
            if letter:
                query = query.filter(Word.content.ilike(f'%{letter}%'))

    if not_in_word_filter:
        filters += '[Letters not in word filter]'
        for letter in not_in_word_filter.split('-'):
            if letter:
                query = query.filter(~Word.content.ilike(f'%{letter}%'))

    if exact_place_filters:
        filters += '[Letters exactly on place word filter]'
        pattern = ''
        for letter in exact_place_filters:
            if letter == '-':
                pattern += '_'
            else:
                pattern += letter

        if pattern:
            query = query.filter(Word.content.like(pattern))

    matching_words = query.all()
    
    try:
        log_events(flag='SRC', title=f'Searched for word with {filters}', description=None)
        return render_template('found_words.html', words=matching_words, previous_page='finder')
    except Exception as e:
        title = "There was an issue while looking for words"
        log_events(flag='ER?', title=title, description=None)
        render_template('error_page.html', message=title)


@app.route('/show/word_<int:id>/<string:previous_page>', methods=['GET', 'POST'])
@login_required
def show_word(id, previous_page):
    word_to_show = Word.query.get_or_404(id)
    word_to_show.searched += 1
    word_to_show.last_search = datetime.now(POLAND_TZ)
    todays_last_as_word_of_literally = True
    title = 'Selected word to show'
    if word_to_show.last_as_word_of_literally == datetime.now(POLAND_TZ).date():
        todays_last_as_word_of_literally = False
    try:
        db.session.commit()
        log_events(flag='SRC', title=f'Searched for word with {word_to_show.content}', description=None)
        return render_template('show_word.html', word=word_to_show, previous_page=previous_page, todays_last_as_word_of_literally=todays_last_as_word_of_literally, title=title)
    except Exception as e:
        db.session.rollback()
        title = f'There was an issue looking up for word: {word_to_show.content}'
        log_events(flag='ER?', title=title, description=e)
        return render_template('error_page.html', message=title)


###################################################################################################################################
#   Extra module
###################################################################################################################################


@app.route('/history', methods=['GET'])
@login_required
def history():
    if 1 == current_user.role_id:
        try:
            flags = Flags.query.order_by(Flags.name).all()
            events = History.query.order_by(History.date.desc()).all()
            return render_template('history.html', events=events, flags=flags)
        except Exception as e:
            title = 'There was an issue getting events'
            log_events(flag='ER?', title=title, description=e)
            return render_template('error_page.html', message=title)
    else:
        title = 'permission to look into history'
        log_events(flag='ER!', title=f'No {title}', description=None)
        return render_template('error_page.html', message=f'You dont have {title}')


@app.route('/delete/events')
@login_required
def deleting():
    if 1 == current_user.role_id:
        events = History.query.order_by(History.date).all()
        if events:
            try:
                History.query.delete()
                db.session.commit()
                log_events(flag='ER?', title='History cleared', description=None)
                return render_template('loading_page.html')
            except Exception as e:
                db.session.rollback()
                title = 'There was an issue deleting history'
                log_events(flag='ER?', title=title, description=e)
                return render_template('error_page.html', message=title)
        else:
            title = "There is no history in database"
            log_events(flag='LG!', title=title, description=None)
            return render_template('error_page.html', message=title)
    else:
        title = 'permission to delete history'
        log_events(flag='ER!', title=f'No {title}', description=None)
        return render_template('error_page.html', message=f'You dont have {title}')


@app.route('/delete/event_<int:id>')
@login_required
def delete_event(id):
    if 1 == current_user.role_id:
        event_to_delete = History.query.get_or_404(id)
        try:
            db.session.delete(event_to_delete)
            db.session.commit()
            history = History.query.all()
            if len(history) > 0:
                return redirect('/history')
            else:
                return redirect('/menu')
        except Exception as e:
            db.session.rollback()
            title = 'There was an issue deleting this event'
            log_events(flag='ER?', title=title, description=e)
            return render_template('error_page.html', message=title)
    else:
        title = 'permission to delete history'
        log_events(flag='ER!', title=f'No {title}', description=None)
        return render_template('error_page.html', message=f'You dont have {title}')


@app.route('/show/event_<int:id>')
@login_required
def show_event(id):
    if 1 == current_user.role_id:
        try:
            event_to_show = History.query.get_or_404(id)
            flag = Flags.query.filter(Flags.name == event_to_show.flag).first()
            return render_template('show_event.html', event=event_to_show, flag=flag)
        except Exception as e:
            title = 'There was an issue deleting this event'
            log_events(flag='ER?', title=title, description=e)
            return render_template('error_page.html', message=title)
    else:
        title = 'permission to look into history events'
        log_events(flag='ER!', title=f'No {title}', description=None)
        return render_template('error_page.html', message=f'You dont have {title}')


# Analysis

# history's plots menu page
@app.route('/history_plots_menu', methods=['GET'])
@login_required
def history_plots_menu():
    if current_user.role_id == 1:
        try:
            return render_template('history_plots_menu.html')
        except Exception as e:
            title = 'There was an issue dispaying menu'
            log_events(flag='ER?', title=title, description=e)
            return render_template('error_page.html', message=title)
    else:
        title = 'permission to see history module'
        log_events(flag='ER!', title=f'No {title}', description=None)
        return render_template('error_page.html', message=f'You dont have {title}')


def get_user_event_count():
    results = defaultdict(int)
    events = db.session.query(History.user).all()
    for event in events:
        results[event.user] += 1
    return dict(results)


def get_event_count_by_flag():
    results = defaultdict(int)
    events = db.session.query(History.flag).all()
    for event in events:
        results[event.flag] += 1
    return dict(results)


def get_event_count_by_specific_flag(flags):
    results = defaultdict(int)
    events = db.session.query(History.flag).filter(History.flag.in_(flags)).all()
    for event in events:
        results[event.flag] += 1
    return results


@app.route('/events_per_user')
@login_required
def events_per_user():
    if current_user.role_id == 1:
        try:
            title = 'User Event Counts'
            user_event_counts = get_user_event_count()

            if not user_event_counts:
                return render_template('error_page.html', message="No events found for any user.")

            users_sorted = sorted(user_event_counts.keys())
            event_counts_sorted = [user_event_counts[user] for user in users_sorted]

            plot_sorted_by_name = figure(
                x_range=users_sorted, 
                title="Events per User (Alphabetically)",
                height=400,
                sizing_mode="stretch_width"
            )
            plot_sorted_by_name.vbar(x=users_sorted, top=event_counts_sorted, width=0.5, color="blue", alpha=0.7)
            plot_sorted_by_name.xaxis.major_label_orientation = math.pi/4
            plot_sorted_by_name.xaxis.axis_label = "Users"
            plot_sorted_by_name.yaxis.axis_label = "Event Count"

            script1, div1 = components(plot_sorted_by_name)
            plot = [script1, div1]

            return render_template('history_charts.html', plot=plot, title=title)
        except Exception as e:
            title = 'There was an issue displaying plot'
            log_events(flag='ER?', title=title, description=e)
            return render_template('error_page.html', message=title)
    else:
        title = 'permission to see analysis module'
        log_events(flag='ER!', title=f'No {title}', description=None)
        return render_template('error_page.html', message=f'You dont have {title}')


@app.route('/events_per_flag')
@login_required
def events_per_flag():
    if current_user.role_id == 1:
        try:
            flag_event_counts = get_event_count_by_flag()

            if not flag_event_counts:
                return render_template('error_page.html', message="No events found for any flag.")

            sorted_flags = sorted(flag_event_counts.keys())
            event_counts_sorted = [flag_event_counts[flag] for flag in sorted_flags]

            plot_sorted_by_flag = figure(
                x_range=sorted_flags, 
                title="Events per Flag (Alphabetically)",
                height=400,
                sizing_mode="stretch_width"
            )
            plot_sorted_by_flag.vbar(x=sorted_flags, top=event_counts_sorted, width=0.5, color="blue", alpha=0.7)
            plot_sorted_by_flag.xaxis.major_label_orientation = math.pi/4
            plot_sorted_by_flag.xaxis.axis_label = "Flags"
            plot_sorted_by_flag.yaxis.axis_label = "Event Count"

            script, div = components(plot_sorted_by_flag)
            plot = [script, div]

            return render_template('history_charts.html', plot=plot, title="Events per Flag")

        except Exception as e:
                title = 'There was an issue displaying plot'
                log_events(flag='ER?', title=title, description=e)
                return render_template('error_page.html', message=title)
    else:
        title = 'permission to see analysis module'
        log_events(flag='ER!', title=f'No {title}', description=None)
        return render_template('error_page.html', message=f'You dont have {title}')


@app.route('/er_flags_bar_chart')
@login_required
def er_flags_bar_chart():
    if current_user.role_id == 1:
        try:
            title = 'Event Flags Distribution (ER? and ER!)'
            er_flags_count = get_event_count_by_specific_flag(['ER?', 'ER!'])

            if not er_flags_count:
                return render_template('error_page.html', message="No events found with the specified flags.")

            flags = list(er_flags_count.keys())
            counts = list(er_flags_count.values())
            
            colors = ['orange', 'red']

            plot = figure(x_range=flags, title=title, height=400,
                          sizing_mode="stretch_width")

            plot.vbar(x=flags, top=counts, width=0.5, color=colors, alpha=0.7)

            plot.xaxis.axis_label = "Event Flags"
            plot.yaxis.axis_label = "Event Count"
            plot.xaxis.major_label_orientation = math.pi/4

            script, div = components(plot)

            return render_template('history_charts.html', plot=[script, div], title=title)

        except Exception as e:
            title = 'There was an issue displaying the bar chart'
            log_events(flag='ER?', title=title, description=str(e))
            return render_template('error_page.html', message=title)

    else:
        title = 'permission to see analysis module'
        log_events(flag='ER!', title=f'No {title}', description=None)
        return render_template('error_page.html', message=f'You don’t have {title}')


@app.route('/cr_flags_bar_chart')
@login_required
def cr_flags_bar_chart():
    if current_user.role_id == 1:
        try:
            title = 'Event Flags Distribution (CRP, CRW and CRU)'
            er_flags_count = get_event_count_by_specific_flag(['CRP', 'CRW', 'CRU'])

            if not er_flags_count:
                return render_template('error_page.html', message="No events found with the specified flags.")

            flags = list(er_flags_count.keys())
            counts = list(er_flags_count.values())
            
            colors = ['#000000', '#ff0000', '#ffe100']

            plot = figure(x_range=flags, title=title, height=400,
                          sizing_mode="stretch_width")

            plot.vbar(x=flags, top=counts, width=0.5, color=colors, alpha=0.7)

            plot.xaxis.axis_label = "Event Flags"
            plot.yaxis.axis_label = "Event Count"
            plot.xaxis.major_label_orientation = math.pi/4

            script, div = components(plot)

            return render_template('history_charts.html', plot=[script, div], title=title)

        except Exception as e:
            title = 'There was an issue displaying the bar chart'
            log_events(flag='ER?', title=title, description=str(e))
            return render_template('error_page.html', message=title)

    else:
        title = 'permission to see analysis module'
        log_events(flag='ER!', title=f'No {title}', description=None)
        return render_template('error_page.html', message=f'You don’t have {title}')


@app.route('/all_edits_by_type')
@login_required
def all_edits_by_type():
    if current_user.role_id == 1:
        try:
            title = 'Edition Events Distribution (ETU and ETW)'
            er_flags_count = get_event_count_by_specific_flag(['ETU', 'ETW'])

            if not er_flags_count:
                return render_template('error_page.html', message="No events found with the specified flags.")

            flags = list(er_flags_count.keys())
            counts = list(er_flags_count.values())
            
            colors = ['#00f59b', '#7014f2']

            plot = figure(x_range=flags, title=title, height=400,
                          sizing_mode="stretch_width")

            plot.vbar(x=flags, top=counts, width=0.5, color=colors, alpha=0.7)

            plot.xaxis.axis_label = "Event Flags"
            plot.yaxis.axis_label = "Event Count"
            plot.xaxis.major_label_orientation = math.pi/4

            script, div = components(plot)

            return render_template('history_charts.html', plot=[script, div], title=title)

        except Exception as e:
            title = 'There was an issue displaying the bar chart'
            log_events(flag='ER?', title=title, description=str(e))
            return render_template('error_page.html', message=title)

    else:
        title = 'permission to see analysis module'
        log_events(flag='ER!', title=f'No {title}', description=None)
        return render_template('error_page.html', message=f'You don’t have {title}')

###################################################################################################################################
#   Analysis module
###################################################################################################################################


def get_content_starts_with_count():
    results = defaultdict(int)  # Domyślny słownik z zerami
    polski_alfabet = 'aąbcćdeęfghijklłmnńoópqrsśtuvwxyzźż'
    for letter in polski_alfabet:
        count = db.session.query(func.count()).filter(Word.content.like(f'{letter}%')).scalar()
        if count > 0:
            results[letter] = count
    return dict(results)


def get_unique_added_by_count():
    query_result = db.session.query(Word.added_by, func.count(Word.added_by)).group_by(Word.added_by).all()
    result = {added_by: count for added_by, count in query_result}
    return result


def get_top_10_most_searched():
    query_result = db.session.query(Word).order_by(desc(Word.searched)).limit(10).all()
    
    if all(word.searched == 0 for word in query_result):
        return False
    
    result = [
        {
            'id': word.id,
            'content': word.content,
            'searched': word.searched,
            'definition': word.definition,
            'source': word.source,
            'added_by': word.added_by
        }
        for word in query_result
    ]
    return result


def get_latest(column):
    if column == 'LWD':
        query_result = db.session.query(Word)\
            .filter(Word.last_as_word_of_the_day.isnot(None))\
            .order_by(desc(Word.last_as_word_of_the_day))\
            .limit(10).all()
    elif column == 'LWL':
        query_result = db.session.query(Word)\
            .filter(Word.last_as_word_of_literally.isnot(None))\
            .order_by(desc(Word.last_as_word_of_literally))\
            .limit(10).all()
    elif column == 'LS':
        query_result = db.session.query(Word)\
            .filter(Word.last_search.isnot(None))\
            .order_by(desc(Word.last_search))\
            .limit(10).all()
    
    if not query_result:
        return False

    result = [
        {
            'id': word.id,
            'content': word.content,
            'last_as_word_of_the_day': word.last_as_word_of_the_day,
            'last_as_word_of_literally': word.last_as_word_of_literally,
            'last_search': word.last_search,
            'definition': word.definition,
            'source': word.source,
            'added_by': word.added_by
        }
        for word in query_result
    ]
    return result


# menu page
@app.route('/analysis_bar_plots_menu', methods=['GET'])
@login_required
def analysis_bar_plots_menu():
    if current_user.role_id != 3:
        try:
            return render_template('analysis_bar_plots_menu.html')
        except Exception as e:
            title = 'There was an issue dispaying menu'
            log_events(flag='ER?', title=title, description=e)
            return render_template('error_page.html', message=title)
    else:
        title = 'permission to see analysis module'
        log_events(flag='ER!', title=f'No {title}', description=None)
        return render_template('error_page.html', message=f'You dont have {title}')


# CHARTS


@app.route('/word_starting_with')
@login_required
def word_starting_with():
    if current_user.role_id != 3:
        try:
            title = request.args.get('title', 'Number of words starting with each letter')

            result = get_content_starts_with_count()
            letters = list(result.keys())
            values = list(result.values())

            not_sorted_plot = figure(
                x_range=letters,
                height=500,
                sizing_mode="stretch_width",
                title="Number of Words Starting with Each Letter",
                toolbar_location=None, tools=""
            )
            
            not_sorted_plot.vbar(x=letters, top=values, width=0.8, color="navy", alpha=0.7)

            not_sorted_plot.xgrid.grid_line_color = None
            not_sorted_plot.y_range.start = 0
            not_sorted_plot.xaxis.axis_label = "Letters"
            not_sorted_plot.yaxis.axis_label = "Count"
            not_sorted_plot.xaxis.major_label_orientation = "horizontal"
        
            script, div = components(not_sorted_plot)
            p_not_sorted = [script, div]

            sorted_result = dict(sorted(result.items(), key=lambda x:x[1]))

            sorted_letters = list(sorted_result.keys())
            sorted_values = list(sorted_result.values())

            sorted_plot = figure(
                x_range=sorted_letters,
                height=500,
                sizing_mode="stretch_width",
                title="Number of Words Starting with Each Letter",
                toolbar_location=None, tools=""
            )
            
            sorted_plot.vbar(x=sorted_letters, top=sorted_values, width=0.8, color="navy", alpha=0.7)

            sorted_plot.xgrid.grid_line_color = None
            sorted_plot.y_range.start = 0
            sorted_plot.xaxis.axis_label = "Letters"
            sorted_plot.yaxis.axis_label = "Count"
            sorted_plot.xaxis.major_label_orientation = "horizontal"
        
            script, div = components(sorted_plot)
            p_sorted = [script, div]

            return render_template('charts.html', p_not_sorted=p_not_sorted, p_sorted=p_sorted, title=title)
        except Exception as e:
            title = 'There was an issue dispaying plot'
            log_events(flag='ER?', title=title, description=e)
            return render_template('error_page.html', message=title)
    else:
        title = 'permission to see analysis module'
        log_events(flag='ER!', title=f'No {title}', description=None)
        return render_template('error_page.html', message=f'You dont have {title}')


@app.route('/unique_added_by_count')
@login_required
def unique_added_by_count():
    if current_user.role_id != 3:
        try:
            title = request.args.get('title', 'Number of words added by users')

            result = get_unique_added_by_count()
            users = list(result.keys())
            values = list(result.values())

            not_sorted_plot = figure(
                x_range=users,
                height=500,
                sizing_mode="stretch_width",
                title="Number of words added by users",
                toolbar_location=None, tools=""
            )
            
            not_sorted_plot.vbar(x=users, top=values, width=0.8, color="navy", alpha=0.7)

            not_sorted_plot.xgrid.grid_line_color = None
            not_sorted_plot.y_range.start = 0
            not_sorted_plot.xaxis.axis_label = "Users"
            not_sorted_plot.yaxis.axis_label = "Count"
            not_sorted_plot.xaxis.major_label_orientation = "horizontal"
        
            script, div = components(not_sorted_plot)
            p_not_sorted = [script, div]

            sorted_result = dict(sorted(result.items(), key=lambda x:x[1]))

            sorted_users = list(sorted_result.keys())
            sorted_values = list(sorted_result.values())

            sorted_plot = figure(
                x_range=sorted_users,
                height=500,
                sizing_mode="stretch_width",
                title="Number of words added by users",
                toolbar_location=None, tools=""
            )
            
            sorted_plot.vbar(x=sorted_users, top=sorted_values, width=0.8, color="navy", alpha=0.7)

            sorted_plot.xgrid.grid_line_color = None
            sorted_plot.y_range.start = 0
            sorted_plot.xaxis.axis_label = "Users"
            sorted_plot.yaxis.axis_label = "Count"
            sorted_plot.xaxis.major_label_orientation = "horizontal"
        
            script, div = components(sorted_plot)
            p_sorted = [script, div]

            return render_template('charts.html', p_not_sorted=p_not_sorted, p_sorted=p_sorted,title=title)
        except Exception as e:
            title = 'There was an issue dispaying plot'
            log_events(flag='ER?', title=title, description=e)
            return render_template('error_page.html', message=title)
    else:
        title = 'permission to see analysis module'
        log_events(flag='ER!', title=f'No {title}', description=None)
        return render_template('error_page.html', message=f'You dont have {title}')


@app.route('/top_10_most_searched')
@login_required
def top_10_most_searched():
    if current_user.role_id != 3:
        try:
            title = request.args.get('title', 'Top 10 most searched words')

            result = get_top_10_most_searched()
            if result is False:
                return render_template('error_page.html', message="No words have been searched yet.")

            sorted_by_content = sorted(result, key=lambda x: x['content'])
            content_x = [item['content'] for item in sorted_by_content]
            searched_y = [item['searched'] for item in sorted_by_content]

            p1 = figure(x_range=content_x, title="Words Sorted Alphabetically by 'content'", height=400, sizing_mode="stretch_width")
            p1.vbar(x=content_x, top=searched_y, width=0.5, color="navy", alpha=0.7)
            p1.xaxis.major_label_orientation = "horizontal"
            p1.xaxis.axis_label = "Content"
            p1.yaxis.axis_label = "Searched"

            sorted_by_searched = sorted(result, key=lambda x: x['searched'], reverse=True)
            content_x_sorted = [item['content'] for item in sorted_by_searched]
            searched_y_sorted = [item['searched'] for item in sorted_by_searched]

            p2 = figure(x_range=content_x_sorted, title="Words Sorted by 'searched' (Descending)", height=400, sizing_mode="stretch_width")
            p2.vbar(x=content_x_sorted, top=searched_y_sorted, width=0.5, color="green", alpha=0.7)
            p2.xaxis.major_label_orientation = "horizontal"
            p2.xaxis.axis_label = "Content"
            p2.yaxis.axis_label = "Searched"

            script1, div1 = components(p1)
            script2, div2 = components(p2)

            p_not_sorted = [script1, div1]
            p_sorted = [script2, div2]

            return render_template('charts.html', p_not_sorted=p_not_sorted, p_sorted=p_sorted, title=title)
        except Exception as e:
            title = 'There was an issue dispaying plot'
            log_events(flag='ER?', title=title, description=e)
            return render_template('error_page.html', message=title)
    else:
        title = 'permission to see analysis module'
        log_events(flag='ER!', title=f'No {title}', description=None)
        return render_template('error_page.html', message=f'You dont have {title}')



@app.route('/searched_words_per_day_17', methods=['GET'])
@login_required
def searched_words_per_day_17():
    if current_user.role_id != 3:
        try:
            title = request.args.get('title', 'Searched words per day, last 17 days')

            seventeen_days_ago = datetime.utcnow().date() - timedelta(days=17)

            results_not_sorted = db.session.query(
                func.date(Word.last_search).label('date'),
                func.count(Word.id).label('count')
            ).filter(
                Word.last_search >= seventeen_days_ago
            ).group_by(func.date(Word.last_search)).all()
            
            dates_not_sorted = [str(result.date) for result in results_not_sorted]
            counts_not_sorted = [result.count for result in results_not_sorted]

            p_not_sorted = figure(
                x_range=dates_not_sorted,
                title="Liczba wyszukiwań słów każdego dnia (ostatnie 17 dni)",
                x_axis_label="Data",
                y_axis_label="Liczba wyszukiwań",
                height=500,
                width=1000,
                sizing_mode="stretch_width"
            )

            p_not_sorted.vbar(x=dates_not_sorted, top=counts_not_sorted, width=0.5, color="green", legend_label="Wyszukiwania")

            p_not_sorted.xaxis.major_label_orientation = 0.8
            p_not_sorted.legend.title = "Legenda"
            p_not_sorted.legend.location = "top_left"

            script_not_sorted, div_not_sorted = components(p_not_sorted)

            results_sorted = db.session.query(
                func.date(Word.last_search).label('date'),
                func.count(Word.id).label('count')
            ).filter(
                Word.last_search != None
            ).group_by(func.date(Word.last_search)) \
            .order_by(func.count(Word.id).desc()) \
            .limit(17).all()

            dates_sorted = [str(result.date) for result in results_sorted]
            counts_sorted = [result.count for result in results_sorted]

            p_sorted = figure(
                x_range=dates_sorted,
                title="Top 10 dni z największą liczbą wyszukiwań słów",
                x_axis_label="Data",
                y_axis_label="Liczba wyszukiwań",
                height=500,
                width=1000,
                sizing_mode="stretch_width"
            )

            p_sorted.vbar(x=dates_sorted, top=counts_sorted, width=0.5, color="blue", legend_label="Top dni")

            p_sorted.xaxis.major_label_orientation = 0.8
            p_sorted.legend.title = "Legenda"
            p_sorted.legend.location = "top_left"

            script_sorted, div_sorted = components(p_sorted)

            p_not_sorted = [script_not_sorted, div_not_sorted]
            p_sorted = [script_sorted, div_sorted]

            return render_template('charts.html', p_not_sorted=p_not_sorted, p_sorted=p_sorted, title=title)
        except Exception as e:
            title = 'There was an issue dispaying plot'
            log_events(flag='ER?', title=title, description=e)
            return render_template('error_page.html', message=title)
    else:
        title = 'permission to see analysis module'
        log_events(flag='ER!', title=f'No {title}', description=None)
        return render_template('error_page.html', message=f'You dont have {title}')


# BUBBLES


# menu page
@app.route('/analysis_bubbles_menu', methods=['GET'])
@login_required
def analysis_bubbles_menu():
    if current_user.role_id != 3:
        try:
            return render_template('analysis_bubbles_menu.html')
        except Exception as e:
            title = 'There was an issue dispaying menu'
            log_events(flag='ER?', title=title, description=e)
            return render_template('error_page.html', message=title)
    else:
        title = 'permission to see analysis module'
        log_events(flag='ER!', title=f'No {title}', description=None)
        return render_template('error_page.html', message=f'You dont have {title}')


@app.route('/top_10_latest_words_of_the_day')
@login_required
def top_10_latest_words_of_the_day():
    if current_user.role_id != 3:
        try:
            call_for_word_of_the_day()
            column = request.args.get('column', 'LWD')
            title = request.args.get('title', 'Latest Words of The Day')
            
            result = get_latest(column=column)
            sorted_words = sorted(result, key=lambda x: x['last_as_word_of_the_day'], reverse=True)

            return render_template('bubbles.html', words=sorted_words, title=title, previous_page='bubble', column=column)
        except Exception as e:
            title = 'There was an issue dispaying plot'
            log_events(flag='ER?', title=title, description=e)
            return render_template('error_page.html', message=title)
    else:
        title = 'permission to see analysis module'
        log_events(flag='ER!', title=f'No {title}', description=None)
        return render_template('error_page.html', message=f'You dont have {title}')


@app.route('/top_10_latest_words_of_literally')
@login_required
def top_10_latest_words_of_literally():
    if current_user.role_id != 3:
        try:
            column = request.args.get('column', 'LWL')
            title = request.args.get('title', 'Latest Words of Literally')
            
            result = get_latest(column=column)
            sorted_words = sorted(result, key=lambda x: x['last_as_word_of_literally'], reverse=True)

            return render_template('bubbles.html', words=sorted_words, title=title, previous_page='bubble', column=column)
        except Exception as e:
            title = 'There was an issue dispaying plot'
            log_events(flag='ER?', title=title, description=e)
            return render_template('error_page.html', message=title)
    else:
        title = 'permission to see analysis module'
        log_events(flag='ER!', title=f'No {title}', description=None)
        return render_template('error_page.html', message=f'You dont have {title}')


@app.route('/top_10_latest_searched')
@login_required
def top_10_latest_searched():
    if current_user.role_id != 3:
        try:
            column = request.args.get('column', 'LS')
            title = request.args.get('title', 'Latest Searched Words')
            
            result = get_latest(column=column)
            sorted_words = sorted(result, key=lambda x: x['last_search'], reverse=True)

            return render_template('bubbles.html', words=sorted_words, title=title, previous_page='bubble', column=column)
        except Exception as e:
            title = 'There was an issue dispaying plot'
            log_events(flag='ER?', title=title, description=e)
            return render_template('error_page.html', message=title)
    else:
        title = 'permission to see analysis module'
        log_events(flag='ER!', title=f'No {title}', description=None)
        return render_template('error_page.html', message=f'You dont have {title}')


if __name__ == "__main__":
    app.run('0.0.0.0', port=80, debug=True)