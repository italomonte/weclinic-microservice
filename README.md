# Microserviço de Confirmação de Agendamentos - Clínica nas Nuvens

Microserviço Python que consulta automaticamente a API da Clínica nas Nuvens, identifica novos agendamentos e envia mensagens de confirmação via provedor de mensagens configurável.

## 📋 Características

- ✅ Consulta automática da API da Clínica nas Nuvens
- ✅ Paginação automática de resultados
- ✅ Filtro de agendamentos já processados (SQLite)
- ✅ Envio de mensagens via provedor configurável
- ✅ Templates de mensagem personalizáveis
- ✅ Scheduler com intervalo configurável
- ✅ Webhook para receber callbacks
- ✅ Logging estruturado
- ✅ Tratamento robusto de erros

## 🏗️ Estrutura do Projeto

```
weclinic-microservice/
├── .gitignore
├── .env.example              # Template de variáveis de ambiente
├── requirements.txt          # Dependências Python
├── api_client.py            # Cliente para API da Clínica nas Nuvens
├── storage.py               # Gerenciamento de SQLite
├── templates.py             # Templates de mensagem
├── sender.py                # Envio de mensagens (provider-agnostic)
├── main.py                  # Lógica principal de processamento
├── scheduler.py             # Loop de execução contínua
├── webhook_app.py           # Aplicação Flask para webhooks
├── run.sh                   # Script de inicialização
├── test_api_mock.py         # Script de teste com dados simulados
├── README.md                # Este arquivo
└── plan.md                  # Plano de desenvolvimento
```

## 📦 Instalação

### Pré-requisitos

- Python 3.7 ou superior
- pip
- Git (para deploy)

### Instalação Local

1. **Clone o repositório** (ou baixe os arquivos):

```bash
git clone <seu-repositorio>
cd weclinic-microservice
```

2. **Crie e ative o ambiente virtual**:

```bash
python3 -m venv venv
source venv/bin/activate  # No Windows: venv\Scripts\activate
```

3. **Instale as dependências**:

```bash
pip install -r requirements.txt
```

4. **Configure as variáveis de ambiente**:

```bash
cp .env.example .env
# Edite o arquivo .env com suas credenciais reais
```

Edite o arquivo `.env` com suas credenciais:

```env
# API da Clínica nas Nuvens
API_BASE=https://api.clinicanasnuvens.com.br/agenda
API_USER=seu_user_basic_auth
API_PASS=sua_senha_basic_auth
CLINICA_CID=client_secret_aqui

# Banco de Dados PostgreSQL (Neon)
DATABASE_URL=postgresql://usuario:senha@host:porta/database?sslmode=require

# Provedor de Mensagens
SENDER_API_URL=https://meu-provedor.com/send
SENDER_AUTH=Bearer_xxx

# Configuração do Scheduler
INTERVAL_MIN=5

# Webhook (opcional)
WEBHOOK_VERIFY_TOKEN=seu_token_de_verificacao
WEBHOOK_PORT=5000
```

### 📝 Como Preencher o .env

Baseado na tela de configuração da API:

1. **`API_BASE`**: URL base da API

   - Formato: `https://api.clinicanasnuvens.com.br/agenda`
   - Sem `/lista` no final (será adicionado automaticamente)

2. **`API_USER`**: Usuário para Basic Auth

   - Geralmente é o **client_id** mostrado na tela (ex: `apiCnn`)
   - Ou pode ser um usuário específico fornecido pela API

3. **`API_PASS`**: Senha para Basic Auth

   - Geralmente é o **client_secret** mostrado na tela
   - Exemplo: `7eb16006265aak53998j9oinnnolko529d3448091416aba7c7784e5f681`
   - Ou pode ser uma senha específica fornecida pela API

4. **`CLINICA_CID`**: Token/Hash para header `clinicaNasNuvens-cid`

   - Este é o valor do campo **"Token/Hash (clinicaNasNuvens-cid)"** da tela
   - Use o ícone de olho 👁️ para revelar o valor mascarado
   - Ou clique em "Alterar token" para gerar um novo
   - Este valor vai no header da requisição HTTP

5. **`DATABASE_URL`**: URL de conexão PostgreSQL (Neon ou outro)

   - Formato: `postgresql://usuario:senha@host:porta/database?sslmode=require`
   - Copie a connection string completa do seu banco Neon
   - Exemplo: `postgresql://user:pass@ep-xxx.aws.neon.tech/db?sslmode=require`
   - O sistema criará automaticamente a tabela `processed` na primeira execução

6. **`SENDER_PROVIDER`**: Tipo de provedor (opcional, padrão: `generic`)

   - `evolution` - Para Evolution API
   - `whatsapp_cloud` - Para WhatsApp Cloud API
   - `generic` - Para outros provedores genéricos

7. **`SENDER_API_URL`**: URL do seu provedor de mensagens

   - **Evolution API**: `http://seu-servidor:8080/message/sendText/NOME_DA_INSTANCIA`
   - **WhatsApp Cloud API**: `https://graph.facebook.com/v18.0/SEU_PHONE_NUMBER_ID/messages`
   - **Outros**: URL conforme documentação do provedor

8. **`SENDER_AUTH`**: Token de autenticação do provedor

   - **Evolution API**: Sua API Key (ex: `sua_api_key_aqui`) ou `Bearer sua_api_key_aqui`
   - **WhatsApp Cloud API**: `Bearer SEU_ACCESS_TOKEN`
   - **Outros**: Formato conforme documentação

9. **`SENDER_MAX_RETRIES`**: Número de tentativas em caso de erro temporário (opcional, padrão: 3)

   - Sistema tenta novamente automaticamente em caso de erros 500, 502, 503, 504, 429, timeout ou erro de conexão
   - Padrão: `3` tentativas

10. **`SENDER_RETRY_DELAY`**: Segundos de espera entre tentativas (opcional, padrão: 2)

- Tempo de espera antes de tentar novamente após um erro temporário
- Padrão: `2` segundos

11. **`INTERVAL_MIN`**: Intervalo em minutos entre execuções (padrão: 5)

12. **`DAYS_AHEAD`**: Quantos dias à frente buscar agendamentos (padrão: 0 = só hoje)

- `0` = Busca apenas agendamentos de hoje
- `7` = Busca agendamentos de hoje até 7 dias à frente
- `30` = Busca agendamentos de hoje até 30 dias à frente
- Útil para enviar confirmações antecipadas para próximos dias

13. **`WEBHOOK_VERIFY_TOKEN`**: Token secreto para verificação do webhook (OPCIONAL)

- Você inventa esse valor (ex: `minha_chave_secreta_123`)
- Só necessário se for usar webhook (receber callbacks do provedor)
- Se usar Evolution API apenas para enviar: NÃO precisa configurar
- Veja seção "Webhook - Para que serve?" abaixo para mais detalhes

14. **`WEBHOOK_PORT`**: Porta onde o webhook vai rodar (OPCIONAL, padrão: 5000)

    - Só necessário se for usar webhook
    - Padrão: `5000`
    - Se não for usar webhook, pode deixar vazio ou não configurar

**Exemplo prático preenchido (Evolution API):**

```env
# API da Clínica nas Nuvens
API_BASE=https://api.clinicanasnuvens.com.br/agenda
API_USER=apiCnn
API_PASS=7eb16006265aak53998j9oinnnolko529d3448091416aba7c7784e5f681
CLINICA_CID=cole_aqui_o_token_hash_da_tela

# Banco de Dados PostgreSQL (Neon)
DATABASE_URL=postgresql://usuario:senha@host:porta/database?sslmode=require

# Provedor de Mensagens - Evolution API
SENDER_PROVIDER=evolution
SENDER_API_URL=http://seu-servidor-evolution:8080/message/sendText/MinhaInstancia
SENDER_AUTH=sua_api_key_evolution

# Configuração do Scheduler
INTERVAL_MIN=5
DAYS_AHEAD=0  # Quantos dias à frente buscar (0 = só hoje, 7 = próxima semana, etc)

# Webhook (opcional - só necessário se quiser receber callbacks do provedor)
WEBHOOK_VERIFY_TOKEN=meu_token_secreto_123
WEBHOOK_PORT=5000
```

**Exemplo com WhatsApp Cloud API:**

```env
# API da Clínica nas Nuvens
API_BASE=https://api.clinicanasnuvens.com.br/agenda
API_USER=apiCnn
API_PASS=7eb16006265aak53998j9oinnnolko529d3448091416aba7c7784e5f681
CLINICA_CID=cole_aqui_o_token_hash_da_tela

# Provedor de Mensagens - WhatsApp Cloud API
SENDER_PROVIDER=whatsapp_cloud
SENDER_API_URL=https://graph.facebook.com/v18.0/123456789/messages
SENDER_AUTH=Bearer EAAxxxxxxxxxxxxx

# Configuração do Scheduler
INTERVAL_MIN=5
```

## 🚀 Uso

### ⚠️ IMPORTANTE: Inicialização do Banco (Primeira Execução)

Se você está iniciando o sistema em uma clínica que **já tem agendamentos existentes**,
execute PRIMEIRO o script de inicialização para evitar enviar mensagens para agendamentos antigos:

```bash
source venv/bin/activate
python3 init_db.py
```

Este script vai:

- ✅ Buscar TODOS os agendamentos existentes na API
- ✅ Marcar como processados SEM enviar mensagens
- ✅ A partir daí, só enviará mensagens para agendamentos NOVOS

**Opções:**

```bash
# Inicializar últimos 60 dias (padrão)
python3 init_db.py

# Inicializar período específico
python3 init_db.py 2025-01-01 2025-12-31

# Inicializar até uma data específica (60 dias antes dela)
python3 init_db.py 2025-12-31
```

### Visualizar Banco de Dados

Para visualizar o conteúdo do banco `.db`:

```bash
# Usando o script Python
python3 view_db.py

# Ou usando SQLite diretamente no terminal
sqlite3 storage.db
sqlite> SELECT * FROM processed;
sqlite> SELECT COUNT(*) FROM processed;
sqlite> .quit

# Ou usando ferramenta gráfica
# - DB Browser for SQLite (https://sqlitebrowser.org/)
# - Abra o arquivo storage.db na ferramenta
```

### Teste Local

1. **Teste com dados mockados** (não chama API real):

```bash
python3 test_api_mock.py
```

2. **Teste apenas o template de mensagem**:

```bash
python3 test_api_mock.py template
```

3. **Execute processamento único** (requer .env configurado):

```bash
python3 main.py
```

4. **Execute o scheduler** (loop contínuo):

```bash
python3 scheduler.py
```

Ou usando o script de inicialização:

```bash
./run.sh
```

### Webhook

Para iniciar o servidor webhook:

```bash
python3 webhook_app.py
```

O webhook estará disponível em `http://localhost:5000/webhook`

**Teste do webhook**:

```bash
# GET (verificação)
curl "http://localhost:5000/webhook?hub.verify_token=SEU_TOKEN&hub.challenge=test123"

# POST (evento)
curl -X POST http://localhost:5000/webhook \
  -H "Content-Type: application/json" \
  -d '{"teste":123}'
```

## 🖥️ Deploy na VPS (Hostinger)

### 1. Preparação da VPS

Conecte via SSH:

```bash
ssh seu_usuario@IP_DA_VPS
```

Instale dependências básicas:

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install python3 python3-venv python3-pip git -y
```

### 2. Clonagem do Repositório

```bash
cd ~
git clone <seu-repositorio> clinica_bot
cd clinica_bot
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. Configuração

Crie o arquivo `.env` com valores reais:

```bash
cp .env.example .env
nano .env  # Ou use seu editor preferido
```

Configure permissões restritas:

```bash
chmod 600 .env
```

### 4. Configuração do Systemd

Crie o arquivo de serviço:

```bash
sudo nano /etc/systemd/system/clinica_bot.service
```

Cole o seguinte conteúdo (ajuste os caminhos conforme necessário):

```ini
[Unit]
Description=Clinica Bot - Scheduler
After=network.target

[Service]
User=seu_usuario
WorkingDirectory=/home/seu_usuario/clinica_bot
EnvironmentFile=/home/seu_usuario/clinica_bot/.env
ExecStart=/home/seu_usuario/clinica_bot/venv/bin/python /home/seu_usuario/clinica_bot/scheduler.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

**Importante**: Substitua `seu_usuario` pelo seu usuário real na VPS.

Ative e inicie o serviço:

```bash
sudo systemctl daemon-reload
sudo systemctl enable clinica_bot
sudo systemctl start clinica_bot
```

### 5. Monitoramento

Visualize os logs em tempo real:

```bash
sudo journalctl -u clinica_bot -f
```

Comandos úteis:

```bash
# Status do serviço
sudo systemctl status clinica_bot

# Parar o serviço
sudo systemctl stop clinica_bot

# Reiniciar o serviço
sudo systemctl restart clinica_bot

# Ver logs recentes
sudo journalctl -u clinica_bot -n 50
```

### 6. Webhook em Produção (Opcional)

Para rodar o webhook em produção, configure um serviço systemd separado ou use Gunicorn:

```bash
pip install gunicorn
```

Crie um serviço systemd para o webhook:

```ini
[Unit]
Description=Clinica Bot - Webhook
After=network.target

[Service]
User=seu_usuario
WorkingDirectory=/home/seu_usuario/clinica_bot
EnvironmentFile=/home/seu_usuario/clinica_bot/.env
ExecStart=/home/seu_usuario/clinica_bot/venv/bin/gunicorn -w 2 -b 0.0.0.0:5000 webhook_app:app
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

## ⚙️ Configuração

### Variáveis de Ambiente

| Variável               | Descrição                                             | Obrigatório               |
| ---------------------- | ----------------------------------------------------- | ------------------------- |
| `API_BASE`             | URL base da API (sem /lista)                          | Sim                       |
| `API_USER`             | Usuário para Basic Auth                               | Sim                       |
| `API_PASS`             | Senha para Basic Auth                                 | Sim                       |
| `CLINICA_CID`          | Client secret da clínica                              | Sim                       |
| `DATABASE_URL`         | URL de conexão PostgreSQL (Neon ou outro)             | Sim                       |
| `SENDER_PROVIDER`      | Tipo de provedor (evolution, whatsapp_cloud, generic) | Não (padrão: generic)     |
| `SENDER_API_URL`       | URL do provedor de mensagens                          | Sim                       |
| `SENDER_AUTH`          | Token/Bearer de autenticação                          | Sim                       |
| `SENDER_MAX_RETRIES`   | Número de tentativas em caso de erro (opcional)       | Não (padrão: 3)           |
| `SENDER_RETRY_DELAY`   | Segundos entre tentativas (opcional)                  | Não (padrão: 2)           |
| `INTERVAL_MIN`         | Intervalo entre execuções (minutos)                   | Não (padrão: 5)           |
| `DAYS_AHEAD`           | Quantos dias à frente buscar agendamentos             | Não (padrão: 0 = só hoje) |
| `WEBHOOK_VERIFY_TOKEN` | Token de verificação do webhook (opcional)            | Não                       |
| `WEBHOOK_PORT`         | Porta do webhook (opcional)                           | Não (padrão: 5000)        |

### Webhook - Para que serve?

O webhook é opcional e serve para receber callbacks/eventos do seu provedor de mensagens. Você só precisa configurá-lo se:

1. Quiser receber confirmações de entrega de mensagens
2. Quiser responder automaticamente a mensagens recebidas
3. Quiser receber status de leitura das mensagens
4. Usar WhatsApp Cloud API (que exige webhook)

**Se você só vai ENVIAR mensagens (como confirmações de agendamento), NÃO precisa configurar o webhook!**

#### Quando usar:

- ✅ Usando WhatsApp Cloud API (obrigatório configurar webhook)
- ✅ Quer receber respostas de pacientes automaticamente
- ✅ Quer saber se mensagens foram entregues/lidas

- ❌ Usando Evolution API apenas para enviar (não precisa)
- ❌ Enviando mensagens unidirecionais apenas (não precisa)

#### Como configurar:

1. **`WEBHOOK_VERIFY_TOKEN`**:

   - Um token secreto que você inventa (ex: `minha_chave_secreta_123`)
   - Use um valor aleatório e seguro
   - Você vai informar esse mesmo token na configuração do seu provedor
   - Exemplo: `WEBHOOK_VERIFY_TOKEN=abc123xyz_secreto_456`

2. **`WEBHOOK_PORT`**:

   - Porta onde o servidor webhook vai rodar
   - Padrão: `5000`
   - Exemplo: `WEBHOOK_PORT=5000`

3. **URL do Webhook**:
   - Você precisa expor seu servidor publicamente (usar ngrok, domínio próprio, ou IP público)
   - URL será: `http://seu-servidor:5000/webhook` ou `https://seu-dominio.com/webhook`
   - Configure essa URL no painel do seu provedor de mensagens

#### Exemplo com Evolution API:

Evolution API geralmente **não exige** webhook para envio simples. Se você só vai enviar confirmações, pode deixar as variáveis de webhook vazias ou não configurá-las.

#### Exemplo com WhatsApp Cloud API:

WhatsApp Cloud API **exige** webhook configurado. Você precisa:

1. Criar um token secreto: `WEBHOOK_VERIFY_TOKEN=meu_token_super_secreto`
2. Expor seu servidor (usar ngrok ou domínio):
   ```bash
   # Exemplo com ngrok (desenvolvimento)
   ngrok http 5000
   ```
3. Configurar no Meta Business:
   - URL do webhook: `https://seu-dominio.com/webhook`
   - Token de verificação: o mesmo valor de `WEBHOOK_VERIFY_TOKEN`

### Provedores de Mensagens Suportados

O sistema suporta múltiplos provedores de mensagens. Configure a variável `SENDER_PROVIDER` no `.env`:

#### Evolution API

Evolution API é uma solução popular para envio de mensagens via WhatsApp.

**Configuração:**

```env
SENDER_PROVIDER=evolution
SENDER_API_URL=http://seu-servidor:8080/message/sendText/NOME_DA_INSTANCIA
SENDER_AUTH=sua_api_key_evolution
```

**Exemplo de URL:**

- Se seu Evolution está em `http://192.168.1.100:8080` e a instância se chama `clinica_bot`:
  ```
  SENDER_API_URL=http://192.168.1.100:8080/message/sendText/clinica_bot
  ```

**Autenticação:**

- Pode usar apenas a API Key: `SENDER_AUTH=sua_api_key_aqui`
- Ou com Bearer: `SENDER_AUTH=Bearer sua_api_key_aqui`

**Observações:**

- O sistema formata automaticamente o número para incluir código do país (55 para Brasil) se necessário
- Evolution espera números no formato `5511999999999` (sem caracteres especiais)

#### WhatsApp Cloud API

Para usar a WhatsApp Cloud API oficial do Meta:

```env
SENDER_PROVIDER=whatsapp_cloud
SENDER_API_URL=https://graph.facebook.com/v18.0/SEU_PHONE_NUMBER_ID/messages
SENDER_AUTH=Bearer SEU_ACCESS_TOKEN
```

#### Provedor Genérico

Para outros provedores, use o modo genérico (padrão):

```env
SENDER_PROVIDER=generic
SENDER_API_URL=https://seu-provedor.com/send
SENDER_AUTH=Bearer seu_token
```

O payload genérico é:

```json
{
  "to": "numero",
  "text": "mensagem"
}
```

Se precisar adaptar para outro formato, edite `sender.py` e adicione um novo provedor nas funções `_montar_payload_*` e `_montar_headers_*`.

## 📝 Logs

O sistema usa o módulo `logging` do Python com nível INFO por padrão. Os logs incluem:

- Inicialização do sistema
- Processamento de agendamentos
- Erros e exceções
- Envios de mensagens
- Webhooks recebidos

Para ajustar o nível de log, edite `main.py` e `scheduler.py`:

```python
logging.basicConfig(level=logging.DEBUG)  # Mais detalhado
```

## 🔒 Segurança

- ✅ Nunca commite o arquivo `.env` (já está no .gitignore)
- ✅ Use permissões restritas: `chmod 600 .env`
- ✅ Configure firewall (ufw) para limitar portas
- ✅ Limite acesso SSH (prefira chaves SSH)
- ✅ Use tokens seguros para webhook

## 🐛 Troubleshooting

### Erro: "Variáveis de ambiente da API não configuradas"

Verifique se o arquivo `.env` existe e contém todas as variáveis obrigatórias.

### Erro: "SENDER_API_URL não configurado"

Configure `SENDER_API_URL` e `SENDER_AUTH` no arquivo `.env`.

### Serviço não inicia

Verifique os logs:

```bash
sudo journalctl -u clinica_bot -n 100
```

Verifique se o caminho do Python está correto no arquivo `.service`:

```bash
/home/seu_usuario/clinica_bot/venv/bin/python --version
```

### Mensagens não são enviadas

- Verifique se `SENDER_API_URL` e `SENDER_AUTH` estão corretos
- Verifique os logs para erros específicos do provedor
- Teste manualmente o endpoint do provedor com curl

### Banco de dados corrompido ou resetar

Para limpar o banco de dados:

```bash
# Usando o script Python
python3 clear_db.py

# Ou conectar diretamente ao PostgreSQL
psql "DATABASE_URL"
psql> DELETE FROM processed;
psql> \q
```

A tabela será recriada automaticamente na próxima execução se necessário.

## 🔄 Atualizações

Para atualizar o código na VPS:

```bash
cd ~/clinica_bot
git pull
source venv/bin/activate
pip install -r requirements.txt  # Se houver novas dependências
sudo systemctl restart clinica_bot
```

## 📚 Desenvolvimento

### Estrutura de Módulos

- **api_client.py**: Comunicação com API externa
- **storage.py**: Persistência de dados (SQLite)
- **templates.py**: Templates de mensagem
- **sender.py**: Envio de mensagens
- **main.py**: Lógica de negócio principal
- **scheduler.py**: Orquestração e execução periódica
- **webhook_app.py**: API REST para callbacks

### Testes

Execute os testes mockados antes de usar em produção:

```bash
python3 test_api_mock.py
```

## 📄 Licença

Este projeto é privado e de uso interno.

## 🤝 Suporte

Para questões ou problemas, consulte os logs ou entre em contato com a equipe de desenvolvimento.
