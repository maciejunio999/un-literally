from app import app
from app import db, User, Word, Role, bcrypt
import os
import time
import math
import traceback
import logging


# GLOBAL VARIABLES
DIR_PATH = os.path.dirname(os.path.realpath(__file__))
FILE = 'slowa_piecioliterowe.txt'
NAME = 'whole.db'


# DECORATORS
def decorator(func):
    def inner1(*args, **kwargs):
        print("*** Running " + func.__name__ + " ***")
        begin = time.time()
        
        t = func(*args, **kwargs)

        end = time.time()
        if True == t:
            print("Total time taken in : ", func.__name__, end - begin)
            print("*** Executed with success ***\n")
        else:
            print("[!] Finished unsuccessfully")
        
    return inner1


# HELPING FUNCTIONS
def find_all(file_name, path):
    result = []
    for root, _, files in os.walk(path):
        if file_name in files:
            f = os.path.join(root, file_name).replace('\\', '/')
            result.append(f)
    return result



# MAIN CREATE DATABASE FUNCTION
@decorator
def create_database(database_name=NAME):
    l = find_all(database_name, "web/instance")
    admin = User(id=0, username='admin', password=bcrypt.generate_password_hash('admin'), role_id=1)

    if len(l) == 0:
        try:
            with app.app_context():
                db.create_all()
                session = db.session
                session.add(admin)
                session.commit()
            return True
        except Exception as e:
            logging.error(traceback.format_exc())
            return "Delete old database and run again"
    else:
        return "Delete old database and run again"

# ADD WORDS FROM BACKUPFILE
@decorator
def add_words():
    try:
        with app.app_context():
            session = db.session
            with open(f'{DIR_PATH}\\{FILE}', "r", encoding='utf-8', newline='\n') as file:
                for i in file:
                    slowo, _ = i.split('\r')
                    word = Word(content=slowo, searched=0, source='Default from dictionary', added_by='Admin')
                    session.add(word)
            session.commit()
        return True
    except Exception as e:
        logging.error(traceback.format_exc())
        return False


# ADD USED ROLES
@decorator
def add_roles():
    all_roles = ["Admin", "ProUser", "PlainUser"]
    try:
        with app.app_context():
            session = db.session
            for i in all_roles:
                role = Role(name=i)
                session.add(role)
            session.commit()
        return True
    except Exception as e:
        logging.error(traceback.format_exc())
        return False

create_database()
add_words()
add_roles()