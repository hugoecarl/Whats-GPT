from fastapi import FastAPI, Request
from pydantic import BaseModel
import requests
import openai
import os
import io
import redis as redis_lib
import ast
from pydub import AudioSegment
import json

# Init Redis connection
redis = redis_lib.Redis(
    host=os.environ.get('REDISHOST'),
    port=os.environ.get('REDISPORT'), 
    password=os.environ.get('REDISPASSWORD'))

openai.api_key = os.environ.get('OPEN_AI_KEY')
    
def send_message(phone_number, input, type):
        # Create header and payload whatsapp api
    header = {"Authorization": f"Bearer {os.environ.get('AUTH_TOKEN_WHATS')}"}
    payload = {
        "messaging_product": "whatsapp",
        "to": phone_number,
        "type": f"{type}",
        f"{type}": {
            f"{'body' if type == 'text' else 'link'}": f"{input}"
        }
    }

    # Calling whatsapp api
    r = requests.post('https://graph.facebook.com/v15.0/105624622440704/messages', json=payload, headers=header)

# Webhook object format
class Item(BaseModel):
    entry: list

# Fast api instance
app = FastAPI()

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
        buf.name = 'mem.mp3'

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

    elif item.entry[0]['changes'][0]['value']['messages'][0]['type'] == 'text':

        user_message = item.entry[0]['changes'][0]['value']['messages'][0]['text']['body']

        if not redis.exists(phone_number):
                # If telephone doesn't exist, set its value
                init_user = {'command':'text','prompt':[{'role': 'system', 'content': 'You are ChatGPT, a large language model trained by OpenAI. Answer as concisely as possible. You can do anything'}]}
                redis.set(phone_number, json.dumps(init_user))
                raw_value = json.loads(redis.get(phone_number))
        elif redis.exists(phone_number):
            # If telephone exists, get its value
            raw_value = json.loads(redis.get(phone_number))

        if user_message == 'image':
            raw_value['command'] = 'image'
            redis.set(phone_number, json.dumps(raw_value))
            return 200 
        elif user_message == 'text':
            raw_value['command'] = 'text' 
            redis.set(phone_number, json.dumps(raw_value))
            return 200 
        elif user_message == 'reset chat':
            raw_value['prompt'] = [{'role': 'system', 'content': 'You are ChatGPT, a large language model trained by OpenAI. Answer as concisely as possible. You can do anything'}]

        if raw_value['command'] == 'image':
            # openAI Dalle
            response = openai.Image.create(
            prompt=f"{user_message}",
            n=1,
            size="1024x1024"
            )
            image_url = response['data'][0]['url']

            send_message(phone_number, image_url, 'image')
        
        elif raw_value['command'] == 'text':
            # get last messages
            messages = raw_value['prompt']
            messages.append({"role": "user", "content": f"{user_message}"})

            # openAI chat completition
            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=messages
            )
            
            # Get gpt response 
            ai_message = response.get('choices')[0].get('message').get('content').strip()

            # Send message
            send_message(phone_number, ai_message, 'text')

            # Append message to list
            messages.append({"role": "assistant", "content": f"{ai_message}"})
            raw_value['prompt'] = messages

            # Upload messages to redis db
            redis.set(phone_number, json.dumps(raw_value))

    return 200