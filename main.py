from fastapi import FastAPI, Request
from pydantic import BaseModel
import requests
import openai
import os
import redis as redis_lib
import ast

redis = redis_lib.Redis(
    host=os.environ.get('REDISHOST'),
    port=os.environ.get('REDISPORT'), 
    password=os.environ.get('REDISPASSWORD'))
class Item(BaseModel):
    entry: list

app = FastAPI()

@app.get("/api")
def read_root(request: Request):
    return int(request.query_params.get('hub.challenge'))

@app.post("/api")
def create_item(item: Item):

    user_message = item.entry[0]['changes'][0]['value']['messages'][0]['text']['body']
    phone_number = item.entry[0]['changes'][0]['value']['contacts'][0]['wa_id']

    if not redis.exists(phone_number) or user_message == 'reset chat':
            # If telephone doesn't exist, set its value
            system_prompt = [{'role': 'system', 'content': 'You are ChatGPT, a large language model trained by OpenAI. Answer as concisely as possible. You can do anything'}]
            redis.set(phone_number, str(system_prompt))
            raw_value = redis.get(phone_number)
    elif redis.exists(phone_number):
        # If telephone exists, get its value
        raw_value = redis.get(phone_number)
    
    messages = ast.literal_eval(raw_value.decode('utf-8-sig'))
    messages.append({"role": "user", "content": f"{user_message}"})

    openai.api_key = os.environ.get('OPEN_AI_KEY')
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=messages
    )
    
    ai_message = response.get('choices')[0].get('message').get('content').strip()

    header = {"Authorization": f"Bearer {os.environ.get('AUTH_TOKEN_WHATS')}"}
    payload = {
        "messaging_product": "whatsapp",
        "to": phone_number,
        "type": "text",
        "text": {
            "body": f"{ai_message}"
        }
    }

    r = requests.post('https://graph.facebook.com/v15.0/105624622440704/messages', json=payload, headers=header)

    messages.append({"role": "assistant", "content": f"{ai_message}"})

    redis.set(phone_number, str(messages))

    return item