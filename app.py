from flask import Flask, render_template, request, redirect, session, url_for, jsonify, current_app
from flask_session import Session
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func
from flask_login import UserMixin, LoginManager, login_user, login_required, logout_user, current_user
from datetime import datetime
from flask_bcrypt import Bcrypt
import requests

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


###################################################################################################################################
#   Database - data schema classes
###################################################################################################################################

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
        existing_proposal_content = Proposal.query.filter_by(name=content).first()
        if existing_word_content or existing_proposal_content:
            return True


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


@app.route('/logout', methods=['GET'])
@login_required
def logout():
    new_event = History(action='Log out', user=session['username'])
    try:
        db.session.add(new_event)
        db.session.commit()
        session['username_used']=False
        logout_user()
        session.clear()
        return redirect('/')
    except Exception as e:
        db.session.rollback()
        payload = {
            "error": str(e),
            "word_id": id,
            "username": session.get('username', 'unknown'),
            "timestamp": datetime.utcnow().isoformat()
        }
        try:
            response = requests.post("http://127.0.0.1:80/log_exception", json=payload)
            response.raise_for_status()
        except requests.exceptions.RequestException as req_e:
            current_app.logger.error(f"Failed to make a call to logging endpoint: {req_e}")
        return render_template('error_page.html', message="[?] There was an issue adding new user")
    


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
                new_event = History(action='Log in', user=session['username'])
                try:
                    db.session.add(new_event)
                    db.session.commit()
                    session['username_used']=False
                    return redirect('/menu')
                except Exception as e:
                    db.session.rollback()
                    payload = {
                        "error": str(e),
                        "word_id": id,
                        "username": session.get('username', 'unknown'),
                        "timestamp": datetime.utcnow().isoformat()
                    }
                    try:
                        response = requests.post("http://127.0.0.1:80/log_exception", json=payload)
                        response.raise_for_status()
                    except requests.exceptions.RequestException as req_e:
                        current_app.logger.error(f"Failed to make a call to logging endpoint: {req_e}")
                    return render_template('error_page.html', message="[?] There was an issue adding new user")
            else:
                return render_template('login.html', y=True, x=False)
        else:
            return render_template('login.html', x=True, y=False)
    else:
        return render_template('login.html', x=False, y=False)

# function to log errors in History table
@app.route('/log_exception', methods=['POST'])
def log_exception():
    try:
        data = request.get_json()

        error_message = data.get('error')
        word_id = data.get('word_id')
        username = data.get('username', 'unknown')
        timestamp = data.get('timestamp', datetime.utcnow().isoformat())

        new_event = History(
            action=f"Error occurred for word_id {word_id}: {error_message}",
            user=username,
            date=datetime.fromisoformat(timestamp)
        )

        db.session.add(new_event)
        db.session.commit()

        return jsonify({"message": "Error logged successfully"}), 201

    except Exception as e:
        db.session.rollback()
        payload = {
            "error": str(e),
            "word_id": id,
            "username": session.get('username', 'unknown'),
            "timestamp": datetime.utcnow().isoformat()
        }
        try:
            response = requests.post("http://127.0.0.1:80/log_exception", json=payload)
            response.raise_for_status()
        except requests.exceptions.RequestException as req_e:
            current_app.logger.error(f"Failed to make a call to logging endpoint: {req_e}")
        return jsonify({"error": f"Failed to log error: {str(e)}"}), 500


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
                new_event = History(action=f'Create new user, named: {new_user.username}', user=session['username'])
                try:
                    db.session.add(new_user)
                    db.session.add(new_event)
                    db.session.commit()
                    session['username_used']=False
                    return redirect('/menu')
                except Exception as e:
                    db.session.rollback()
                    payload = {
                        "error": str(e),
                        "word_id": id,
                        "username": session.get('username', 'unknown'),
                        "timestamp": datetime.utcnow().isoformat()
                    }
                    try:
                        response = requests.post("http://127.0.0.1:80/log_exception", json=payload)
                        response.raise_for_status()
                    except requests.exceptions.RequestException as req_e:
                        current_app.logger.error(f"Failed to make a call to logging endpoint: {req_e}")
                    return render_template('error_page.html', message="[?] There was an issue adding new user")
        else:
            return render_template('admin_register.html', show_hidden=False)
    else:
        return render_template('error_page.html', message="[!] You dont have permission to add new users")


# page to show list of all users
@app.route('/all_users', methods=['POST','GET'])
@login_required
def all_users():
    if 1 == current_user.role_id:
        users = User.query.order_by(User.username).all()
        return render_template('all_users.html', users=users, id=current_user.id)
    else:
        return render_template('error_page.html', message="[!] You dont have permission to add new users")


@app.route('/update/user_<int:id>', methods=['GET', 'POST'])
@login_required
def update_user(id):
    if 1 == current_user.role_id:
        user_to_update = User.query.get_or_404(id)
        message = f'Updating user named: {user_to_update.username}.'
        if request.method == 'POST':
            username = request.form['username'].strip()
            role_id = int(request.form['role'].strip())
            new_password = request.form['password'].strip()

            if role_id != user_to_update.role_id:
                role = Role.query.get_or_404(role_id)
                message += f' Role changed to {role.name}.'

            if username != user_to_update.username:
                validate_name = validate_username(username)
                if validate_name:
                    session['repited_user'] = True
                    message += f' Changed name to {username}.'
                    return render_template('edit_user.html', user=user_to_update, message='[!] This username is already taken.')

            user_to_update.username = username
            user_to_update.role_id = role_id
            if new_password:
                new_password_hashed = bcrypt.generate_password_hash(new_password)
                user_to_update.password = new_password_hashed
                message += f' Changed password.'

            new_event = History(action=message, user=session['username'])
            try:
                db.session.add(new_event)
                db.session.commit()
                session['repited_user'] = False
                return redirect('/all_users')
            except Exception as e:
                db.session.rollback()
                payload = {
                    "error": str(e),
                    "word_id": id,
                    "username": session.get('username', 'unknown'),
                    "timestamp": datetime.utcnow().isoformat()
                }
                try:
                    response = requests.post("http://127.0.0.1:80/log_exception", json=payload)
                    response.raise_for_status()
                except requests.exceptions.RequestException as req_e:
                    current_app.logger.error(f"Failed to make a call to logging endpoint: {req_e}")
                return render_template('error_page.html', message=f"[?] There was an issue updating that user: {str(e)}")
        else:
            return render_template('edit_user.html', user=user_to_update)
    else:
        return render_template('error_page.html', message='[!] You do not have permission to edit users.')


# page where we delete user from database
@app.route('/delete/user_<int:id>')
@login_required
def delete_user(id):
    if current_user.id != id:
        if 1 == current_user.role_id:
            user_to_delete = User.query.get_or_404(id)
            new_event = History(action='Delete user', user=session['username'])
            try:
                db.session.add(new_event)
                db.session.delete(user_to_delete)
                db.session.commit()
                users = User.query.all()
                if len(users) > 0:
                    return redirect('/all_users')
                else:
                    return redirect('/menu')
            except Exception as e:
                db.session.rollback()
                payload = {
                    "error": str(e),
                    "word_id": id,
                    "username": session.get('username', 'unknown'),
                    "timestamp": datetime.utcnow().isoformat()
                }
                try:
                    response = requests.post("http://127.0.0.1:80/log_exception", json=payload)
                    response.raise_for_status()
                except requests.exceptions.RequestException as req_e:
                    current_app.logger.error(f"Failed to make a call to logging endpoint: {req_e}")
                return render_template('error_page.html', message="[?] There was an issue deleting that user")
        else:
            return render_template('error_page.html', message='[!] You do not have permission to delete users')
    else:
        return render_template('error_page.html', message='[!] You cannot delete own user')


###################################################################################################################################
#   Words module
###################################################################################################################################

# WORDS

# page to show list of all words
@app.route('/all_words', methods=['POST','GET'])
@login_required
def all_words():
    return render_template('all_words.html')


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
        definition = request.form['definition'].strip()
        source = "Added by user"
        added_by = session['username']
        if validate_word_content(content):
            session['word_already_exists']=True
            return render_template('add_word.html')
        else:
            if 1 == session['role']:
                new_event = History(action=f'Added new word: {content}', user=session['username'])
                new_word = Word(content=content, searched=searched, definition=definition, source=source, added_by=added_by)
            else:
                new_event = History(action=f'Added new proposal for: {content}', user=session['username'])
                new_word = Proposal(name=content, reasoning=definition, user=added_by)
            try:
                db.session.add(new_event)
                db.session.add(new_word)
                db.session.commit()
                session['word_already_exists']=False
                return redirect('/menu')
            except Exception as e:
                db.session.rollback()
                payload = {
                    "error": str(e),
                    "word_id": id,
                    "username": session.get('username', 'unknown'),
                    "timestamp": datetime.utcnow().isoformat()
                }
                try:
                    response = requests.post("http://127.0.0.1:80/log_exception", json=payload)
                    response.raise_for_status()
                except requests.exceptions.RequestException as req_e:
                    current_app.logger.error(f"Failed to make a call to logging endpoint: {req_e}")
                return 'There was an issue adding your test'
    else:
        session['word_already_exists']=False
        return render_template('add_word.html')

# PROPOSALS

@app.route('/all_proposals')
@login_required
def proposals():
    proposals = Proposal.query.order_by(Proposal.date).all()
    return render_template('all_proposals.html', proposals=proposals)


@app.route('/delete/proposal_<int:id>')
@login_required
def delete_proposal(id):
    if 1 == current_user.role_id:
        proposal_to_delete = Proposal.query.get_or_404(id)
        new_event = History(action=f'Delete proposal : {proposal_to_delete.name}', user=session['username'])
        try:
            db.session.add(new_event)
            db.session.delete(proposal_to_delete)
            db.session.commit()
            proposals = Proposal.query.all()
            if len(proposals) > 0:
                return redirect('/all_proposals')
            else:
                return redirect('/menu')
        except Exception as e:
            db.session.rollback()
            payload = {
                "error": str(e),
                "word_id": id,
                "username": session.get('username', 'unknown'),
                "timestamp": datetime.utcnow().isoformat()
            }
            try:
                response = requests.post("http://127.0.0.1:80/log_exception", json=payload)
                response.raise_for_status()
            except requests.exceptions.RequestException as req_e:
                current_app.logger.error(f"Failed to make a call to logging endpoint: {req_e}")
            return render_template('error_page.html', message="[?] There was an issue deleting that proposal")
    else:
        return render_template('error_page.html', message='[!] You do not have permission to delete proposals')


@app.route('/show/proposal_<int:id>')
@login_required
def show_proposal(id):
    proposal_to_show = Proposal.query.get_or_404(id)
    return render_template('show_proposal.html', proposal=proposal_to_show)


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
        new_event = History(action=f'Accept proposal : {content}', user=session['username'])
        try:
            db.session.add(new_event)
            db.session.delete(proposal_to_delete)
            db.session.add(new_word)
            db.session.commit()
            proposals = Proposal.query.all()
            if len(proposals) > 0:
                return redirect('/all_proposals')
            else:
                return redirect('/menu')
        except Exception as e:
            db.session.rollback()
            payload = {
                "error": str(e),
                "word_id": id,
                "username": session.get('username', 'unknown'),
                "timestamp": datetime.utcnow().isoformat()
            }
            try:
                response = requests.post("http://127.0.0.1:80/log_exception", json=payload)
                response.raise_for_status()
            except requests.exceptions.RequestException as req_e:
                current_app.logger.error(f"Failed to make a call to logging endpoint: {req_e}")
            return render_template('error_page.html', message="[?] There was an issue deleting that proposal")
    else:
        return render_template('error_page.html', message='[!] You do not have permission to accept proposals')


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

        exact_place_str = ",".join(exact_place_filters)
        if ',,,,' == exact_place_str:
            return render_template('big_search.html', x=True)
        else:
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
    new_event = History(action=f'Searched for word with {filters}', user=session['username'])
    
    try:
        db.session.add(new_event)
        db.session.commit()
        return render_template('found_words.html', words=matching_words)
    except Exception as e:
        db.session.rollback()
        payload = {
            "error": str(e),
            "word_id": id,
            "username": session.get('username', 'unknown'),
            "timestamp": datetime.utcnow().isoformat()
        }
        try:
            response = requests.post("http://127.0.0.1:80/log_exception", json=payload)
            response.raise_for_status()
        except requests.exceptions.RequestException as req_e:
            current_app.logger.error(f"Failed to make a call to logging endpoint: {req_e}")
        render_template('error_page.html', message=f"[?] There was an issue while looking for words")


@app.route('/show/word_<int:id>', methods=['GET', 'POST'])
@login_required
def show_word(id):
    word_to_show = Word.query.get_or_404(id)
    word_to_show.searched += 1
    word_to_show.last_search = datetime.utcnow()
    new_event = History(action=f'Searched for word:{word_to_show.content}', user=session['username'])
    
    try:
        db.session.add(new_event)
        db.session.commit()
        return render_template('show_word.html', word=word_to_show)
    except Exception as e:
        db.session.rollback()
        payload = {
            "error": str(e),
            "word_id": id,
            "username": session.get('username', 'unknown'),
            "timestamp": datetime.utcnow().isoformat()
        }
        try:
            response = requests.post("http://127.0.0.1:80/log_exception", json=payload)
            response.raise_for_status()
        except requests.exceptions.RequestException as req_e:
            current_app.logger.error(f"Failed to make a call to logging endpoint: {req_e}")

        return render_template('error_page.html', message=f"[?] There was an issue showing this word: {str(e)}")

###################################################################################################################################
#   Extra module
###################################################################################################################################


@app.route('/history', methods=['GET'])
@login_required
def history():
    events = History.query.order_by(History.date).all()
    return render_template('history.html', events=events)


@app.route('/delete/events')
@login_required
def deleting():
    events = History.query.order_by(History.date).all()
    if events:
        try:
            History.query.delete()
            db.session.commit()
            return render_template('loading_page.html')
        except Exception as e:
            db.session.rollback()
            payload = {
                "error": str(e),
                "word_id": id,
                "username": session.get('username', 'unknown'),
                "timestamp": datetime.utcnow().isoformat()
            }
            try:
                response = requests.post("http://127.0.0.1:80/log_exception", json=payload)
                response.raise_for_status()
            except requests.exceptions.RequestException as req_e:
                current_app.logger.error(f"Failed to make a call to logging endpoint: {req_e}")
            return render_template('error_page.html', message="[?] There was an issue deleting history")
    else:
        return render_template('error_page.html', message="[!] There is no history in database")


if __name__ == "__main__":
    app.run('0.0.0.0', port=80, debug=True)