from app import app, db, Word
from sqlalchemy import func, desc
import pytz
from datetime import datetime, timedelta

POLAND_TZ = pytz.timezone('Europe/Warsaw')

def decorator(func):
    def inner1(*args, **kwargs):
        print("\n*** Running " + func.__name__ + " ***")
        func(*args, **kwargs)
    return inner1


@decorator
def change_last_word_of_the_day():
    with app.app_context():
        today = datetime.now(POLAND_TZ).date()
        print(today)
        past = today - timedelta(days=3)
        print(past)
        word_today = Word.query.filter(func.date(Word.last_as_word_of_the_day) == datetime.now(POLAND_TZ).date()).all()
        print(word_today[0].content)
        word_today[0].last_as_word_of_the_day = past
        try:
            db.session.commit()
            return True
        except Exception as e:
            print(str(e))

change_last_word_of_the_day()