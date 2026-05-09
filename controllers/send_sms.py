import requests
import os

url = "https://api.mozesms.com/sms/send"

def send_sms(phone: str, message: str, sender_id: str = "AGVIAGEM") -> dict:
    """
    Envia um SMS usando a API do MozeSMS.

    Args:
        phone: Número de telefone (com código do país, ex: 258868888656)
        message: Texto da mensagem
        sender_id: ID do remetente (padrão: AGVIAGEM)

    Returns:
        dict: Resposta da API com status e dados do SMS
    """
    headers = {
        "X-API-Key": os.getenv("X-API-KEY"),
        "X-API-Secret": os.getenv("X-API-SECRET"),
        "Content-Type": "application/json"
    }

    payload = {
        "phone": phone,
        "message": message,
        "sender_id": sender_id
    }

    try:
        response = requests.post(url, json=payload, headers=headers)

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
            return data
        else:
            print("Erro:", response.status_code)
            print(response.text)
            return {"error": response.status_code, "message": response.text}

    except requests.exceptions.RequestException as e:
        print("Erro na requisição:", e)
        return {"error": str(e)}