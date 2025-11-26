#!/usr/bin/env python3
"""
Script para verificar se todas as variáveis de ambiente necessárias estão configuradas.
"""

import os
from dotenv import load_dotenv

load_dotenv()

print("🔍 Verificando configuração...")
print("=" * 70)

erros = []
avisos = []

# Variáveis obrigatórias para API da clínica
if not os.getenv("API_BASE"):
    erros.append("❌ API_BASE não configurado")
if not os.getenv("API_USER"):
    erros.append("❌ API_USER não configurado")
if not os.getenv("API_PASS"):
    erros.append("❌ API_PASS não configurado")
if not os.getenv("CLINICA_CID"):
    erros.append("❌ CLINICA_CID não configurado")

# Variáveis obrigatórias para banco de dados
if not os.getenv("DATABASE_URL"):
    erros.append("❌ DATABASE_URL não configurado")

# Variáveis para Aspa API
sender_provider = os.getenv("SENDER_PROVIDER", "generic").lower()
if sender_provider == "aspa":
    if not os.getenv("SENDER_API_URL"):
        erros.append("❌ SENDER_API_URL não configurado")
    else:
        api_url = os.getenv("SENDER_API_URL")
        if api_url != "https://api.aspa.app/v2.0":
            avisos.append(f"⚠️  SENDER_API_URL está como '{api_url}', deveria ser 'https://api.aspa.app/v2.0'?")
    
    if not os.getenv("ASPA_TOKEN"):
        erros.append("❌ ASPA_TOKEN não configurado (obrigatório para autenticação)")
    
    if not os.getenv("ASPA_CHANNEL"):
        erros.append("❌ ASPA_CHANNEL não configurado")
    
    if not os.getenv("ASPA_KEY"):
        erros.append("❌ ASPA_KEY não configurado (usado na URL após /template/)")
    
    if not os.getenv("AGENDAMENTO_MODEL_NAME"):
        erros.append("❌ AGENDAMENTO_MODEL_NAME não configurado")
    else:
        template_key = os.getenv("AGENDAMENTO_MODEL_NAME")
        print(f"✅ AGENDAMENTO_MODEL_NAME: {template_key[:20]}...")
    
    if not os.getenv("AGENDAMENTO_EXC_CONS_MODEL_NAME"):
        avisos.append("⚠️  AGENDAMENTO_EXC_CONS_MODEL_NAME não configurado (usado para agendamentos que não são consulta)")
    else:
        exc_cons_key = os.getenv("AGENDAMENTO_EXC_CONS_MODEL_NAME")
        print(f"✅ AGENDAMENTO_EXC_CONS_MODEL_NAME: {exc_cons_key[:20]}...")
    
    if not os.getenv("REAGENDAMENTO_MODEL_NAME"):
        avisos.append("⚠️  REAGENDAMENTO_MODEL_NAME não configurado")
    
    if not os.getenv("CANCELAMENTO_MODEL_NAME"):
        erros.append("❌ CANCELAMENTO_MODEL_NAME não configurado")
    else:
        cancel_key = os.getenv("CANCELAMENTO_MODEL_NAME")
        print(f"✅ CANCELAMENTO_MODEL_NAME: {cancel_key}")
else:
    avisos.append(f"ℹ️  SENDER_PROVIDER está como '{sender_provider}' (não é 'aspa')")

print()
print("📋 Resultado da Verificação:")
print("=" * 70)

if erros:
    print("\n🚫 ERROS (impedem o funcionamento):")
    for erro in erros:
        print(f"  {erro}")
else:
    print("\n✅ Todas as variáveis obrigatórias estão configuradas!")

if avisos:
    print("\n⚠️  AVISOS:")
    for aviso in avisos:
        print(f"  {aviso}")

print()
print("=" * 70)

if erros:
    print("\n❌ Corrija os erros acima antes de executar o projeto.")
    exit(1)
else:
    print("\n✅ Configuração OK! Você pode executar o projeto.")
    print("\nPara rodar:")
    print("  python3 scheduler.py")
    print("  ou")
    print("  ./run.sh")
    exit(0)

