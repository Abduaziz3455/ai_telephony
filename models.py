import datetime
import logging

import requests
from dotenv import load_dotenv
from environs import Env
from langchain.output_parsers import ResponseSchema, StructuredOutputParser
from langchain_core.prompts import PromptTemplate
from langchain_openai import ChatOpenAI
import speech_recognition as sr

load_dotenv()

env = Env()
env.read_env()


def send_stt_request(path):
    url = 'https://uzbekvoice.ai/api/v1/stt'
    headers = {"Authorization": env.str("MOHIRAI_TOKEN")}
    data = {"return_offsets": "false", "run_diarization": "false", "blocking": "true", "language": "ru-uz"}
    print(path)
    files = {"file": ("audio.wav", open(path, "rb"))}

    try:
        response = requests.post(url, headers=headers, files=files, data=data)
        if response.status_code == 200:
            print(response.json())
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


def rus_stt(path):
    r = sr.Recognizer()
    with sr.AudioFile(path) as source:
        audio = r.record(source)
        try:
            text = r.recognize_google(audio, language='ru-RU')
            text = text.lower()
            # Explicitly encode and decode text to handle potential encoding issues
            text = text.encode('utf-8')
            return text
        except sr.RequestError as e:
            print(f"Request error: {e}")
            return None
        except sr.UnknownValueError:
            print("Unknown value error")
            return None


# Define a single function that handles both response ID extraction and payment date extraction
def process_user_query(text: str, responses: list, today_date: str = "2024-08-25", week_day: str = "sunday"):
    # Define a schema for extracting both response ID and payment date
    schemas = [
        ResponseSchema(name="ID", description="The ID of the exact matching response. Options: from 0 to 8", type='number'),
        ResponseSchema(name="Payment_Date", description="The exact date when the user intends to make a payment, in dd-mm format", type="string"),
        ResponseSchema(name="Reason", description="The reason provided by the user for not paying the debt", type="string")
    ]

    # Create an output parser with the combined schema
    output_parser = StructuredOutputParser.from_response_schemas(schemas)
    format_instructions = output_parser.get_format_instructions()
    # Create a formatted string for responses context
    responses_context = "\n".join([f"ID: {resp[0]}, Response: {resp[1]}" for resp in responses])

    # Define a combined prompt template
    prompt = PromptTemplate(template=(
        "As a debt collection expert, analyze the following Uzbek(Russian) text. Perform these tasks:\n"
        "1. Identify the most appropriate response ID from the list based on the user's debt payment query.\n"
        "2. Extract the exact payment date mentioned by the user. Convert relative dates (e.g., 'bugun' for today, 'ertaga' for tomorrow) "
        "into 'dd-mm' format, based on today's date ({today_date}) and the day of the week ({week_day}).\n"
        "3. Extract the reason why the user may not intend to pay the debt, if mentioned.\n"
        "If no date or reason is provided, return an empty string.\n"
        "Responses:\n{responses_context}\n"
        "{format_instructions}\nQuery: {text}"
    ), input_variables=["text", "today_date", "week_day"], 
    partial_variables={"format_instructions": format_instructions, "responses_context": responses_context})

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


def get_today_date_and_weekday():
    # Get today's date
    today = datetime.date.today()
    # Format the date as YYYY-MM-DD
    d = today.strftime("%Y-%m-%d")
    # Get the weekday name (e.g., "Monday")
    w = today.strftime("%A")
    return d, w


def main_func(audio_path, scripts, lang):
    # Load the CSV data
    if lang == 'uz':
        transcription = send_stt_request(audio_path)
    else:
        transcription = rus_stt(audio_path)
    print(transcription)
    if transcription:
        date, weekday = get_today_date_and_weekday()
        user_response = process_user_query(transcription, scripts, today_date=date, week_day=weekday)
        if "error" not in user_response:
            return user_response
        else:
            return None
    else:
        return None
