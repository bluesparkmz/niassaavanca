import requests

url = "https://api.mozesms.com/sms/send"

headers = {
    "X-API-Key": "mk_be589bd261cf6109d39af41d213c2df4",
    "X-API-Secret": "sk_056ff4b1be70546f4d2ca7e796235887ebab73197638db0ec84fd96e8de329c2",
    "Content-Type": "application/json"
}

payload = {
    "phone": "258868888656",
    "message": "Ola Jorge Sebastia recebeste uma nova reserva no Niassa Avanca!",
    "sender_id": "AGVIAGEM"
}

try:
    response = requests.post(url, json=payload, headers=headers)

    # Verifica se a requisição foi bem sucedida
    if response.status_code == 200:
        data = response.json()

        print("SMS enviado com sucesso!")
        print("ID:", data["data"]["id"])
        print("Telefone:", data["data"]["phone"])
        print("Status:", data["data"]["status"])
        print("Partes:", data["data"]["parts"])
        print("Custo:", data["data"]["cost"])
        print("Saldo restante:", data["data"]["remaining_balance"])
        print("Resposta gateway:", data["data"]["gateway_response"])

    else:
        print("Erro:", response.status_code)
        print(response.text)

except requests.exceptions.RequestException as e:
    print("Erro na requisição:", e)