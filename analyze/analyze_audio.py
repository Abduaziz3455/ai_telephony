import sys

import psycopg2
from environs import Env
from psycopg2 import sql
from models import main_func

env = Env()
env.read_env()


def analyze_audio(uuid):
    try:
        # Connect to your postgres DB
        conn = psycopg2.connect(dbname="robot_call", user="postgres", password="abdu3421", host="127.0.0.1",
                                port="5432")
        # Create a cursor object
        cur = conn.cursor()
        # Retrieve columns of the table using the UUID
        cur.execute(sql.SQL("SELECT voice, paydate FROM voicehistory WHERE uuid = %s"), [uuid])
        data = cur.fetchone()
        audio_path = f"{env.str('VOICE_LOC')}{data[0]}"
        pay_date = data[1]
        # Execute the query
        cur.execute(sql.SQL("SELECT id, text FROM script"))

        # Fetch all results from the query
        all_scripts = cur.fetchall()

        if pay_date:
            cur.execute(sql.SQL("SELECT voice FROM script WHERE id = %s"), [9])
            script_path = f"{env.str('SCRIPT_PATH')}{cur.fetchone()[0]}"
            # Update a column in the table based on the UUID
            query = "UPDATE voicehistory SET resvoice = %s, finished = %s WHERE uuid = %s"
            update_query = sql.SQL(query)
            cur.execute(update_query, (script_path, True, uuid))
        else:
            user_resp = main_func(audio_path, all_scripts)
            if user_resp:
                query = "UPDATE voicehistory SET resvoice = %s, paydate = %s, scriptid = %s WHERE uuid = %s"
                script_id = user_resp['ID']
                date = user_resp['Payment_Date']
                cur.execute(sql.SQL("SELECT voice FROM script WHERE id = %s"), [script_id])
                script_path = f"{env.str('SCRIPT_PATH')}{cur.fetchone()[0]}"
                # Update a column in the table based on the UUID
                update_query = sql.SQL(query)
                cur.execute(update_query, (script_path, date, script_id, uuid))
            else:
                print("Response qaytmadi!!!")
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
