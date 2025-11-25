# Exemplo de Requisição cURL - Envio de Mensagem via Aspa API

## Formato Atual da Requisição

```bash
curl -X POST \
  'https://api.aspa.app/v2.0/message/template/{ASPA_KEY}' \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json' \
  -H 'Authorization: Bearer {ASPA_TOKEN}' \
  -d '{
    "contact": {
      "alias": "Italo",
      "phone": "5592984532273",
      "update": true
    },
    "channel": "1760642396999b3d9217008b04475a53deeae",
    "template": "depilacao_a_laser_1761592295687",
    "params": {
      "content": {
        "1": "29/11/2025",
        "2": "10:00"
      }
    }
  }'
```

## Exemplo Completo com Valores Reais

```bash
curl -X POST \
  'https://api.aspa.app/v2.0/message/template/d938ea7f0f984e49e243d7056f2770213e29b0913d9b94a87df44d1686e13b8e' \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json' \
  -H 'Authorization: Bearer wS56L2zOtLjMDkKKur7S8Y723tTmCsOk' \
  -d '{
    "contact": {
      "alias": "Italo",
      "phone": "5592984532273",
      "update": true
    },
    "channel": "1760642396999b3d9217008b04475a53deeae",
    "template": "depilacao_a_laser_1761592295687",
    "params": {
      "content": {
        "1": "29/11/2025",
        "2": "10:00"
      }
    }
  }'
```

## Estrutura da Requisição

### URL

- **Base**: `https://api.aspa.app/v2.0` (SENDER_API_URL)
- **Endpoint**: `/message/template/{ASPA_KEY}`
- **URL Completa**: `https://api.aspa.app/v2.0/message/template/{ASPA_KEY}`

### Headers

- `Content-Type: application/json`
- `Accept: application/json`
- `Authorization: Bearer {ASPA_TOKEN}` ou `Bearer {SENDER_AUTH}`

### Body (JSON)

```json
{
  "contact": {
    "alias": "Italo",           // Sempre "Italo"
    "phone": "5592984532273",   // Número formatado (55 + DDD + número)
    "update": true              // Sempre true
  },
  "channel": "{ASPA_CHANNEL}",  // ID do canal
  "template": "{template_key}", // Nome do template (ex: AGENDAMENTO_MODEL_NAME)
  "params": {
    "content": {
      "1": "valor1",            // Parâmetros do template
      "2": "valor2",
      ...
    }
  }
}
```

## Exemplos por Tipo de Mensagem

### Confirmação de Agendamento

```bash
curl -X POST \
  'https://api.aspa.app/v2.0/message/template/{ASPA_KEY}' \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json' \
  -H 'Authorization: Bearer {ASPA_TOKEN}' \
  -d '{
    "contact": {
      "alias": "Italo",
      "phone": "5592984532273",
      "update": true
    },
    "channel": "{ASPA_CHANNEL}",
    "template": "{AGENDAMENTO_MODEL_NAME}",
    "params": {
      "content": {
        "1": "25/11/2025",
        "2": "16:00",
        "3": "ADICIONAL DE PRODUTO - DIU",
        "4": "—"
      }
    }
  }'
```

### Cancelamento

```bash
curl -X POST \
  'https://api.aspa.app/v2.0/message/template/{ASPA_KEY}' \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json' \
  -H 'Authorization: Bearer {ASPA_TOKEN}' \
  -d '{
    "contact": {
      "alias": "Italo",
      "phone": "5592984532273",
      "update": true
    },
    "channel": "{ASPA_CHANNEL}",
    "template": "{CANCELAMENTO_MODEL_NAME}",
    "params": {
      "content": {
        "1": "ADICIONAL DE PRODUTO - DIU",
        "2": "25/11/2025",
        "3": "16:00"
      }
    }
  }'
```

### Reagendamento

```bash
curl -X POST \
  'https://api.aspa.app/v2.0/message/template/{ASPA_KEY}' \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json' \
  -H 'Authorization: Bearer {ASPA_TOKEN}' \
  -d '{
    "contact": {
      "alias": "Italo",
      "phone": "5592984532273",
      "update": true
    },
    "channel": "{ASPA_CHANNEL}",
    "template": "{REAGENDAMENTO_MODEL_NAME}",
    "params": {
      "content": {
        "1": "ADICIONAL DE PRODUTO - DIU",
        "2": "25/11/2025",
        "3": "16:00",
        "4": "REAGENDADO",
        "5": "5592984532273"
      }
    }
  }'
```

## Variáveis de Ambiente Necessárias

- `SENDER_API_URL`: `https://api.aspa.app/v2.0`
- `ASPA_KEY`: Hash usado na URL após `/template/`
- `ASPA_TOKEN` ou `SENDER_AUTH`: Token de autenticação
- `ASPA_CHANNEL`: ID do canal
- `AGENDAMENTO_MODEL_NAME`: Nome do template de confirmação
- `CANCELAMENTO_MODEL_NAME`: Nome do template de cancelamento
- `REAGENDAMENTO_MODEL_NAME`: Nome do template de reagendamento
