#!/bin/bash

# Script de inicialização do scheduler
# Ativa o ambiente virtual e executa o scheduler.py

# Define caminhos (ajuste conforme necessário)
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
VENV_PATH="$SCRIPT_DIR/venv"
ENV_FILE="$SCRIPT_DIR/.env"

# Verifica se o ambiente virtual existe
if [ ! -d "$VENV_PATH" ]; then
    echo "Erro: Ambiente virtual não encontrado em $VENV_PATH"
    echo "Execute: python3 -m venv venv"
    exit 1
fi

# Ativa o ambiente virtual
source "$VENV_PATH/bin/activate"

# Carrega variáveis de ambiente do arquivo .env se existir
if [ -f "$ENV_FILE" ]; then
    export $(cat "$ENV_FILE" | grep -v '^#' | xargs)
fi

# Executa o scheduler
python3 "$SCRIPT_DIR/scheduler.py"

