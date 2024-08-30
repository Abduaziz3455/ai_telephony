import logging

import requests
from environs import Env

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
            return response.json()['result']['text']
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


resp = send_stt_request("3.wav")
print(resp)
