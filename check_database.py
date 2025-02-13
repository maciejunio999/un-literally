from app import app, db, User, Word, Role, Proposal, History, Flags, NotificationToUser, Notifications

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
            print("notifications: ", user.notifications)
            print("="*20)

# FUNCTION TO CHECK FEW WORDS IN DB
@decorator
def check_words():
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

# FUNCTION TO CHECK FEW PROPOSALS IN DB
@decorator
def check_proposals():
    with app.app_context():
        for event in db.session.query(History):
            print('id: ', event.id)
            print('flag: ', event.flag)
            print('title: ', event.title)
            print('description: ', event.description)
            print('user: ', event.user)
            print('date: ', event.date)
            print("="*20)

# FUNCTION TO CHECK EVENT FLAGS IN DB
@decorator
def check_event_flags():
    with app.app_context():
        for event_flag in db.session.query(Flags):
            print('id: ', event_flag.id)
            print('name: ', event_flag.name)
            print('description: ', event_flag.description)
            print("="*20)

# FUNCTION TO CHECK NOTIFICATIONS TO USERS IN DB
@decorator
def check_notification_to_user():
    with app.app_context():
        for notification_to_user in db.session.query(NotificationToUser):
            print('id: ', notification_to_user.id)
            print('user_id: ', notification_to_user.user_id)
            print('notifications_ids: ', notification_to_user.notifications_ids)
            print("="*20)

# FUNCTION TO CHECK NOTIFICATIONS IN DB
@decorator
def check_notifications():
    with app.app_context():
        for notification in db.session.query(Notifications):
            print('id: ', notification.id)
            print('title: ', notification.title)
            print('description: ', notification.description)
            print('back_reference: ', notification.back_reference)
            print("="*20)

check_users()
#check_words()
#check_roles()
#check_proposals()
#check_proposals()
#check_event_flags()
#check_notification_to_user()
#check_notifications()