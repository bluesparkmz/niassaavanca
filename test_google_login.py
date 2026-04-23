#!/usr/bin/env python3
"""
Script para testar o fluxo de login Google
Uso: python test_google_login.py <id_token>
"""

import os
import sys
import requests
from datetime import datetime

# Configurações
GOOGLE_TOKENINFO_URL = "https://oauth2.googleapis.com/tokeninfo"
GOOGLE_DEFAULT_CLIENT_ID = "690521786732-am1r9nqeg1qdtr1b52esq8kq8panhdi1.apps.googleusercontent.com"
BACKEND_URL = os.getenv("BACKEND_URL", "https://meuchat-production.up.railway.app")

def test_verify_token(id_token: str):
    """Testa a validação do token Google igual o backend faz"""
    print(f"\n{'='*60}")
    print("TESTE 1: Validar token no Google")
    print(f"{'='*60}")
    
    try:
        response = requests.get(
            GOOGLE_TOKENINFO_URL,
            params={"id_token": id_token},
            timeout=10,
        )
        print(f"✓ Status: {response.status_code}")
        
        if response.status_code >= 400:
            print(f"✗ Erro: {response.status_code}")
            print(f"  Response: {response.text}")
            return None
        
        payload = response.json()
        print(f"✓ Payload recebido:")
        for key, value in payload.items():
            if key not in ["email_verified", "at_hash"]:
                print(f"  {key}: {value}")
        
        # Validações
        print(f"\n{'='*60}")
        print("TESTE 2: Validações")
        print(f"{'='*60}")
        
        sub = payload.get("sub")
        aud = payload.get("aud")
        exp = payload.get("exp")
        
        print(f"sub (user ID): {sub} {'✓' if sub else '✗'}")
        print(f"aud (client ID): {aud} {'✓' if aud else '✗'}")
        print(f"exp (expiration): {exp} {'✓' if exp else '✗'}")
        
        if not sub or not aud or not exp:
            print("\n✗ Token incompleto!")
            return None
        
        # Verificar client ID
        allowed = os.getenv("GOOGLE_CLIENT_IDS", GOOGLE_DEFAULT_CLIENT_ID)
        allowed_client_ids = {item.strip() for item in allowed.split(",") if item.strip()}
        
        print(f"\nClient ID esperado(s): {allowed_client_ids}")
        print(f"Client ID do token: {aud}")
        
        if aud not in allowed_client_ids:
            print(f"✗ Client ID NÃO AUTORIZADO!")
            return None
        print(f"✓ Client ID autorizado")
        
        # Verificar expiração
        expires_at = int(exp)
        now = int(datetime.utcnow().timestamp())
        print(f"\nExpira em: {expires_at}")
        print(f"Agora: {now}")
        print(f"Válido por: {expires_at - now}s {'✓' if expires_at > now else '✗'}")
        
        if expires_at <= now:
            print(f"✗ Token expirado!")
            return None
        
        print(f"\n✓ Token válido!")
        return payload
        
    except Exception as exc:
        print(f"✗ Erro: {exc}")
        return None

def test_backend_login(id_token: str):
    """Testa o endpoint de login no backend"""
    print(f"\n{'='*60}")
    print("TESTE 3: Testar endpoint /auth/login-google")
    print(f"{'='*60}")
    
    try:
        response = requests.post(
            f"{BACKEND_URL}/auth/login-google",
            json={"id_token": id_token},
            timeout=10,
        )
        print(f"✓ Status: {response.status_code}")
        
        if response.status_code >= 400:
            print(f"✗ Erro HTTP {response.status_code}")
            data = response.json()
            print(f"  Error: {data}")
            return None
        
        data = response.json()
        print(f"✓ Login bem-sucedido!")
        print(f"  Token: {data.get('access_token', '').replace(data.get('access_token', '')[-20:], '...[last20]')}")
        return data
        
    except Exception as exc:
        print(f"✗ Erro: {exc}")
        return None

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python test_google_login.py <id_token>")
        print("\nOu copie um token Google real de um teste anterior")
        sys.exit(1)
    
    id_token = sys.argv[1]
    
    print("\n" + "="*60)
    print("TESTE DE LOGIN GOOGLE - Niassa Avanca Backend")
    print("="*60)
    
    # Teste 1: Validar token
    payload = test_verify_token(id_token)
    
    if not payload:
        print("\n✗ Falha na validação do token")
        sys.exit(1)
    
    # Teste 2: Backend
    result = test_backend_login(id_token)
    
    if result:
        print("\n✓✓✓ TODO FUNCIONANDO! ✓✓✓")
    else:
        print("\n✗ Falha no backend")
        sys.exit(1)
