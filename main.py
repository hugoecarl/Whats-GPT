from fastapi import FastAPI, Request
from pydantic import BaseModel
import requests
import openai
import json

# with open('keys.json', 'r') as f:
#     KEYS = json.loads(f.read())
#     f.close()

class Item(BaseModel):
    entry: list

app = FastAPI()

@app.get("/api")
def read_root(request: Request):
    return int(request.query_params.get('hub.challenge'))

@app.post("/api")
def create_item(item: Item):

    user_message = item.entry[0]['changes'][0]['value']['messages'][0]['text']['body']

    with open('chat.json', 'r') as f:
        messages = json.loads(f.read())
        f.close()
    messages.append({"role": "user", "content": f"{user_message}"})

    openai.api_key = KEYS['OPEN_AI_KEY']
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=messages
    )
    
    ai_message = response.get('choices')[0].get('message').get('content').strip()

    header = {"Authorization": f"Bearer {KEYS['AUTH_TOKEN_WHATS']}"}
    payload = {
        "messaging_product": "whatsapp",
        "to": item.entry[0]['changes'][0]['value']['contacts'][0]['wa_id'],
        "type": "text",
        "text": {
            "body": f"{ai_message}"
        }
    }

    r = requests.post('https://graph.facebook.com/v15.0/105624622440704/messages', json=payload, headers=header)

    messages.append({"role": "assistant", "content": f"{ai_message}"})

    with open('chat.json', 'w') as f:
        json.dump(messages, f, indent=4)

    return item.entry[0]['changes'][0]['value']['contacts'][0]['wa_id']