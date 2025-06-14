import sqlite3
conn = sqlite3.connect("accounts.db")
cursor = conn.cursor()
cursor.execute("SELECT * FROM accounts")
print(cursor.fetchall())
