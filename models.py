import logging

import requests
from dotenv import load_dotenv
from environs import Env
from langchain.output_parsers import ResponseSchema, StructuredOutputParser
from langchain_core.prompts import PromptTemplate
from langchain_openai import ChatOpenAI

load_dotenv()

env = Env()
env.read_env()


def send_stt_request(path):
    url = 'https://uzbekvoice.ai/api/v1/stt'
    headers = {"Authorization": env.str("MOHIRAI_TOKEN")}
    data = {"return_offsets": "false", "run_diarization": "false", "blocking": "true", "language": "ru-uz"}

    files = {"file": ("audio.wav", open(path, "rb"))}

    try:
        response = requests.post(url, headers=headers, files=files, data=data)
        if response.status_code == 200:
            print("Yuborildii")
            javob = response.json()['result']['text']
            print("Response: {}".format(javob))
            return javob
        else:
            logging.error(response.text)
            logging.error('Mohirai error in initial request')
            return None
    except requests.exceptions.Timeout:
        logging.error('Timeout in initial request')
        return None
    except Exception as e:
        logging.error(f'Error in initial request: {e}')
        return None


# Define a single function that handles both response ID extraction and payment date extraction
def process_user_query(text: str, responses: list, today_date: str = "2024-08-25", week_day: str = "sunday"):
    # Define a schema for extracting both response ID and payment date
    schemas = [ResponseSchema(name="ID", description="The ID of the exact matching response. Options: from 0 to 8",
                              type='number'), ResponseSchema(name="Payment_Date",
                                                             description="The exact date when the user intends to make a payment, in dd-mm format",
                                                             type="string")]

    # Create an output parser with the combined schema
    output_parser = StructuredOutputParser.from_response_schemas(schemas)
    format_instructions = output_parser.get_format_instructions()

    # Create a formatted string for responses context
    responses_context = "\n".join([f"ID: {resp[0]}, Response: {resp[1]}" for resp in responses])

    # Define a combined prompt template
    prompt = PromptTemplate(template=("You are an expert in handling natural language queries for debt collection. "
                                      "Analyze the given Uzbek text to perform the following tasks:\n"
                                      "1. Select the most appropriate response ID from the list below based on the user's query about debt payment.\n"
                                      "2. Extract the specific date when the user intends to make a payment. Convert relative dates like 'bugun' (today), 'ertaga' (tomorrow), 'kecha' (yesterday), "
                                      "'oyning oxiriga qadar' (by the end of the month), 'haftani boshida' (at the beginning of the week), and similar expressions "
                                      "into exact dates using today's date ({today_date}) and week day ({week_day}). Only extract the first relevant date that is directly related to the user's intention to pay a debt, in 'dd-mm' format.\n"
                                      "If no date is found, return an empty string.\n"
                                      "Responses:\n{responses_context}\n"
                                      "{format_instructions}\nQuery: {text}"),
                            input_variables=["text", "today_date", "week_day"],
                            partial_variables={"format_instructions": format_instructions,
                                               "responses_context": responses_context})

    # Initialize the language model
    chat_model = ChatOpenAI(model='gpt-4o-mini', temperature=0.2)

    # Create the LangChain with the prompt and model
    chain = prompt | chat_model | output_parser

    try:
        # Invoke the chain to get the response
        dict_response = chain.invoke({"text": text, "today_date": today_date, "week_day": week_day})
        return dict_response
    except Exception as e:
        print(f"An error occurred: {e}")
        return {"error": str(e)}


def main_func(audio_path, scripts):
    # Load the CSV data
    transcription = send_stt_request(f"C:/Program Files/FreeSWITCH/sounds/en/us/callie/{audio_path}")
    print(transcription)
    if transcription:
        date = "2024-08-30"
        weekday = "friday"
        user_response = process_user_query(transcription, scripts, today_date=date, week_day=weekday)
        if "error" not in user_response:
            return user_response
        else:
            return None
    else:
        return None

import psycopg2
from psycopg2 import sql

conn = psycopg2.connect(dbname="robot_call", user="postgres", password="abdu3421", host="127.0.0.1",
                        port="5432")
# Create a cursor object
cur = conn.cursor()
# Retrieve columns of the table using the UUID
cur.execute(sql.SQL("SELECT voice, paydate FROM voicehistory WHERE uuid = %s"), ['dad7911a-2d9c-4c5e-a3bf-de42ba0495a1'])
data = cur.fetchone()
audio_path = f"C:/Program Files/FreeSWITCH/sounds/en/us/callie/{data[0]}"
pay_date = data[1]
all_scripts = cur.execute(sql.SQL("SELECT id, text FROM script"))


main_func('recordings/dad7911a-2d9c-4c5e-a3bf-de42ba0495a1_response.wav', all_scripts)
