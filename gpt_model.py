import pandas as pd
from dotenv import load_dotenv
from langchain.output_parsers import ResponseSchema, StructuredOutputParser
from langchain_core.prompts import PromptTemplate
from langchain_openai import ChatOpenAI

load_dotenv()


# Define a single function that handles both response ID extraction and payment date extraction
def process_user_query(text: str, responses: list, today_date: str = "2024-08-25", week_day: str = "sunday"):
    # Define a schema for extracting both response ID and payment date
    schemas = [ResponseSchema(name="ID", description="The ID of the exact matching response. Options: from 0 to 8",
                              type='number'),
               ResponseSchema(name="Payment_Date",
                              description="The exact date when the user intends to make a payment, in dd-mm format",
                              type="string")]

    # Create an output parser with the combined schema
    output_parser = StructuredOutputParser.from_response_schemas(schemas)
    format_instructions = output_parser.get_format_instructions()

    # Create a formatted string for responses context
    responses_context = "\n".join([
        f"ID: {resp['ID']}, Response: {resp['Response']}, Description: {resp['Description']}, Synonyms: {resp['Synonyms']}"
        for resp in responses])

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


# Load the CSV data
data = pd.read_csv('scenarios.csv')
responses = data.to_dict(orient='records')

# Example usage
while True:
    user_input = input("Enter a query: ")
    result = process_user_query(user_input, responses)
    print(f"Main Extracted Response: {result}")
    if 'ID' in result:
        matching_response = data[data['ID'] == result['ID']].values.tolist()[0]
        print(f"Matched Response: {matching_response}")
