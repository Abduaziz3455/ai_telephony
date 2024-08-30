import sys

import psycopg2
from psycopg2 import sql
from models import main_func


def analyze_audio(uuid):
    try:
        # Connect to your postgres DB
        conn = psycopg2.connect(dbname="robot_call", user="postgres", password="abdu3421", host="127.0.0.1",
                                port="5432")
        # Create a cursor object
        cur = conn.cursor()
        # Retrieve columns of the table using the UUID
        cur.execute(sql.SQL("SELECT voice FROM voicehistory WHERE uuid = %s"), [uuid])

        audio_path = cur.fetchone()[0]
        all_scripts = cur.execute(sql.SQL("SELECT ID, Response FROM scripts"))

        user_resp = main_func(audio_path, all_scripts)
        script_id = user_resp['ID']
        date = user_resp['Payment_Date']

        cur.execute(sql.SQL("SELECT audio_path FROM scripts WHERE ID = %s"), [script_id])
        script_path = cur.fetchone()[0]
        # Update a column in the table based on the UUID
        update_query = sql.SQL("UPDATE voicehistory SET resVoice = %s, payDate = %s, scriptId = %s WHERE uuid = %s")
        cur.execute(update_query, (script_path, date, scriptId, uuid))
        # Commit the transaction
        conn.commit()
        # Close the cursor and connection
        cur.close()
        conn.close()

        print("Update successful")

    except Exception as e:
        print(f"An error occurred: {e}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 analyze_audio.py uuid")
        sys.exit(1)

    uuid = sys.argv[1]
    try:
        analyze_audio(uuid)
    except Exception as e:
        print("Error analyzing audio:", e)
        sys.exit(1)
