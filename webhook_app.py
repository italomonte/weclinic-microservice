import os
from flask import Flask, request, jsonify
from dotenv import load_dotenv
import logging

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Token de verificação (configure via variável de ambiente ou defina aqui)
VERIFY_TOKEN = os.getenv("WEBHOOK_VERIFY_TOKEN", "SEU_TOKEN_DE_VERIFICACAO")


@app.route("/webhook", methods=["GET"])
def webhook_challenge():
    """
    Verificação de webhook (usado por provedores como WhatsApp Cloud API).
    
    Alguns provedores enviam um GET com hub.verify_token e hub.challenge
    para verificar que o endpoint está ativo e controlado por você.
    """
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")
    
    logger.info(f"Webhook challenge recebido: token={token is not None}, challenge={challenge is not None}")
    
    if token == VERIFY_TOKEN:
        logger.info("Token de verificação válido, retornando challenge")
        return challenge, 200
    
    logger.warning("Token de verificação inválido")
    return "Forbidden", 403


@app.route("/webhook", methods=["POST"])
def webhook_receive():
    """
    Recebe eventos/callbacks do provedor de mensagens.
    
    Processa eventos recebidos e pode disparar ações como:
    - Respostas automáticas
    - Atualizações de status
    - Processamento de mensagens recebidas
    """
    try:
        data = request.get_json()
        logger.info(f"Webhook POST recebido: {data}")
        
        # Aqui você pode processar eventos recebidos e fazer ações
        # Exemplos:
        # - Guardar em DB
        # - Disparar handlers específicos
        # - Responder mensagens automaticamente
        
        # Retorna resposta de sucesso
        return jsonify({"status": "ok"}), 200
    
    except Exception as e:
        logger.error(f"Erro ao processar webhook: {e}", exc_info=True)
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/health", methods=["GET"])
def health():
    """Endpoint de health check simples."""
    return jsonify({"status": "healthy"}), 200


if __name__ == "__main__":
    # Em produção, use Gunicorn ou similar
    # Não use app.run() em produção
    port = int(os.getenv("WEBHOOK_PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=False)

