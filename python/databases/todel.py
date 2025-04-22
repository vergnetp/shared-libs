import pymysql

config = {
    "host": "localhost",
    "port": 3307,
    "user": "test",
    "password": "test",
    "database": "testdb_mysql",
}

try:
    conn = pymysql.connect(**config)
    with conn.cursor() as cursor:
        cursor.execute("SELECT VERSION();")
        version = cursor.fetchone()
        print("✅ MySQL connected successfully! Version:", version[0])
    conn.close()
except Exception as e:
    print("❌ MySQL connection failed:", e)