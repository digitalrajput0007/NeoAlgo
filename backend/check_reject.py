import sqlite3

def check():
    conn = sqlite3.connect('algo_trader.db')
    cur = conn.cursor()
    cur.execute("SELECT metadata_json FROM trade_events WHERE trade_id=10 AND event_type='TRADE_REJECTED'")
    print(cur.fetchone())

check()
