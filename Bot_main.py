import os
import requests

token = os.getenv("TELEGRAM_BOT_TOKEN")
chat_id = os.getenv("TELEGRAM_CHAT_ID")

message = "🎯 Opportunity Radar funktioniert!"

url = f"https://api.telegram.org/bot{token}/sendMessage"

response = requests.post(url, data={
    "chat_id": chat_id,
    "text": message
})

print(response.text)
