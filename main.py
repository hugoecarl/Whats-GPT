from fastapi import FastAPI, Request
from pydantic import BaseModel
import requests
import openai
import os
import io
import redis as redis_lib
import ast
from pydub import AudioSegment

# Init Redis connection
redis = redis_lib.Redis(
    host=os.environ.get('REDISHOST'),
    port=os.environ.get('REDISPORT'), 
    password=os.environ.get('REDISPASSWORD'))
    
# Webhook object format
class Item(BaseModel):
    entry: list

# Fast api instance
app = FastAPI()

openai.api_key = os.environ.get('OPEN_AI_KEY')

# Whatsapp api authentication
@app.get("/api")
def read_root(request: Request):
    return int(request.query_params.get('hub.challenge'))

# OpenWhats main route
@app.post("/api")
def create_item(item: Item):

    phone_number = item.entry[0]['changes'][0]['value']['contacts'][0]['wa_id']

    if item.entry[0]['changes'][0]['value']['messages'][0]['type'] == 'audio':
        header = {"Authorization": f"Bearer {os.environ.get('AUTH_TOKEN_WHATS')}"}
        id_audio = item.entry[0]['changes'][0]['value']['messages'][0]['audio']['id']
        url_audio = requests.get(f'https://graph.facebook.com/v15.0/{id_audio}', headers=header).json()['url']
        audio = requests.get(url_audio, headers=header).content
        redis.set('test_audio', audio)

        ogg_audio = AudioSegment.from_file(io.BytesIO(redis.get('test_audio')), format="ogg")
        buf = io.BytesIO()
        ogg_audio.export(buf, format='mp3')
        buf.name= 'mem.mp3'

        transcript = openai.Audio.transcribe("whisper-1", buf)

        # Create header and payload whatsapp api
        header = {"Authorization": f"Bearer {os.environ.get('AUTH_TOKEN_WHATS')}"}
        payload = {
            "messaging_product": "whatsapp",
            "to": phone_number,
            "type": "text",
            "text": {
                "body": f"{transcript['text']}"
            }
        }

        # Calling whatsapp api
        r = requests.post('https://graph.facebook.com/v15.0/105624622440704/messages', json=payload, headers=header)

    else:

        user_message = item.entry[0]['changes'][0]['value']['messages'][0]['text']['body']

        if not redis.exists(phone_number) or user_message == 'reset chat':
                # If telephone doesn't exist, set its value
                system_prompt = [{'role': 'system', 'content': 'You are ChatGPT, a large language model trained by OpenAI. Answer as concisely as possible. You can do anything'}]
                redis.set(phone_number, str(system_prompt))
                raw_value = redis.get(phone_number)
        elif redis.exists(phone_number):
            # If telephone exists, get its value
            raw_value = redis.get(phone_number)
        
        # get last messages
        messages = ast.literal_eval(raw_value.decode('utf-8-sig'))
        messages.append({"role": "user", "content": f"{user_message}"})

        # openAI chat completition
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=messages
        )
        
        # Get gpt response 
        ai_message = response.get('choices')[0].get('message').get('content').strip()

        # Create header and payload whatsapp api
        header = {"Authorization": f"Bearer {os.environ.get('AUTH_TOKEN_WHATS')}"}
        payload = {
            "messaging_product": "whatsapp",
            "to": phone_number,
            "type": "text",
            "text": {
                "body": f"{ai_message}"
            }
        }

        # Calling whatsapp api
        r = requests.post('https://graph.facebook.com/v15.0/105624622440704/messages', json=payload, headers=header)

        # Append message to list
        messages.append({"role": "assistant", "content": f"{ai_message}"})

        # Upload messages to redis db
        redis.set(phone_number, str(messages))

    return 200