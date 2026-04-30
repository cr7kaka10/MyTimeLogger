import sqlite3
from database import StudyLogger

db = StudyLogger({})
print('is_completed:', db.is_task_completed('69edec26e4b02e10952156de'))
