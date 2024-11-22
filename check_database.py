from app import app, db, User, Word, Role, Proposal

# DECORATORS
def decorator(func):
    def inner1(*args, **kwargs):
        print("\n*** Running " + func.__name__ + " ***")
        func(*args, **kwargs)
    return inner1

# FUNCTION TO CHECK ALL USERS IN DB
@decorator
def check_users():
    with app.app_context():
        for user in db.session.query(User):
            print("username: ", user.username)
            print("role: ", user.role_id)
            print("password: ", user.password)
            print("="*20)

# FUNCTION TO CHECK FEW WORDS IN DB
@decorator
def chech_words():
    with app.app_context():
        i = 0
        for word in db.session.query(Word):
            if i < 6:
                print('id: ', word.id)
                print('content: ', word.content)
                print('searched: ', word.searched)
                print('definition: ', word.definition)
                print('last_search: ', word.last_search)
                print('last_as_word_of_the_day: ', word.last_as_word_of_the_day)
                print('last_as_word_of_literally: ', word.last_as_word_of_literally)
                print('source: ', word.source)
                print('added_by: ', word.added_by)
                print("="*20)
                i += 1
            else:
                break

# FUNCTION TO CHECK ALL ROLES IN DB
@decorator
def check_roles():
    with app.app_context():
        for role in db.session.query(Role):
            print("id: ", role.id)
            print("name: ", role.name)
            print("="*20)

# FUNCTION TO CHECK FEW PROPOSALS IN DB
@decorator
def check_proposals():
    with app.app_context():
        for proposal in db.session.query(Proposal):
            print('id: ', proposal.id)
            print('name: ', proposal.name)
            print('reasoning: ', proposal.reasoning)
            print('user: ', proposal.user)
            print('date: ', proposal.date)
            print("="*20)

check_users()
#chech_words()
check_roles()
#check_proposals()