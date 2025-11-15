# Plano de Desenvolvimento - Microserviço de Confirmação de Agendamentos

## Visão Geral

Microserviço em Python para consultar a API da Clínica nas Nuvens e enviar mensagens de confirmação de consultas automaticamente. O serviço roda continuamente, processa novos agendamentos, envia mensagens via provedor configurável e mantém registro de IDs processados.

## 1. Preparação da VPS (Hostinger)

### Conexão SSH

```bash
ssh seu_usuario@IP_DA_VPS
```

### Instalação de Dependências

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install python3 python3-venv python3-pip git -y
```

## 2. Estrutura do Projeto

```
clinica_bot/
├── requirements.txt
├── .env.example
├── .env                    # Criar na VPS (não commitado)
├── api_client.py
├── storage.py
├── sender.py
├── templates.py
├── main.py
├── scheduler.py
├── webhook_app.py
├── run.sh
├── test_api_mock.py       # Script de teste
└── README.md
```

## 3. Especificações da API

### Endpoint

- **URL**: `https://api.clinicanasnuvens.com.br/agenda/lista`
- **Método**: GET
- **Autenticação**: Basic Auth (usuário e senha)
- **Headers Obrigatórios**:
  - `clinicaNasNuvens-cid`: `<client_secret>`
  - `Accept`: `application/json`

### Query Parameters

- `dataInicial` (YYYY-MM-DD): Data inicial do intervalo
- `dataFinal` (YYYY-MM-DD): Data final do intervalo
- `pagina` (int): Número da página

### Formato de Resposta

- Lista de páginas JSON
- Cada página contém:
  - `lista`: Array de agendamentos
  - `totalPaginas`: Número total de páginas (quando disponível)

### Campos dos Agendamentos

- `id`: Identificador único
- `data`: Data da consulta
- `horaInicio`: Hora de início
- `telefoneCelularPaciente`: Telefone do paciente
- `procedimentos`: Lista de procedimentos
- `nome_profissional`: Nome do profissional
- `observacoes`: Observações adicionais
- `paciente_nome` ou `nomePaciente`: Nome do paciente
- `endereco_clinica` ou `endereco`: Endereço da clínica

## 4. Requisitos Técnicos

### Dependências (requirements.txt)

```
requests
Flask
python-dotenv
apscheduler
```

### Variáveis de Ambiente (.env.example)

```env
# API da Clínica nas Nuvens
API_BASE=https://api.clinicanasnuvens.com.br/agenda
API_USER=seu_user_basic_auth
API_PASS=sua_senha_basic_auth
CLINICA_CID=client_secret_aqui

# Provedor de Mensagens
SENDER_API_URL=https://meu-provedor.com/send
SENDER_AUTH=Bearer_xxx

# Configuração do Scheduler
INTERVAL_MIN=5
```

## 5. Módulos do Sistema

### 5.1. api_client.py

- Função `fetch_agendamentos(data_inicial, data_final, pagina=1)`
- Implementa Basic Auth
- Adiciona headers obrigatórios
- Tratamento de erros HTTP
- Retorna JSON bruto

### 5.2. storage.py

- Gerencia SQLite (`storage.db`)
- Tabela `processed` com campos:
  - `id` (PRIMARY KEY)
  - `tipo` (TEXT)
  - `criado_em` (TIMESTAMP)
- Funções:
  - `init_db()`: Inicializa banco de dados
  - `is_processed(item_id)`: Verifica se ID já foi processado
  - `mark_processed(item_id, tipo='agendamento')`: Marca como processado

### 5.3. templates.py

- Template de mensagem de confirmação usando `string.Template`
- Variáveis: `$primeiro_nome`, `$data_agenda`, `$hora_agenda`, `$nome_profissional`, `$procedimentos`, `$endereco_clinica`

### 5.4. sender.py

- Função `enviar_mensagem(numero, texto)`
- Provider-agnostic (adaptável para WhatsApp Cloud API ou outros)
- Payload e headers configuráveis via variáveis de ambiente
- Retorna `True` se enviado com sucesso, `False` caso contrário

### 5.5. main.py

- Função `processar_intervalo(data_inicial, data_final)`
- Implementa paginação automática
- Filtra agendamentos novos (verifica em `storage`)
- Extrai dados dos agendamentos (com fallbacks para diferentes nomes de campos)
- Formata número de telefone (remove caracteres não numéricos)
- Monta mensagem usando template
- Envia mensagem e marca como processado apenas se envio for bem-sucedido

### 5.6. scheduler.py

- Loop infinito que executa `processar_intervalo` periodicamente
- Intervalo configurável via `INTERVAL_MIN` (em minutos)
- Tratamento de exceções com logs
- Inicializa banco de dados na inicialização

### 5.7. webhook_app.py

- Aplicação Flask simples
- Rota `/webhook` (GET): Verificação de token (webhook challenge)
- Rota `/webhook` (POST): Recebe eventos/callbacks
- Logs de eventos recebidos

### 5.8. run.sh

- Script de inicialização para ambiente virtual
- Carrega variáveis de ambiente do arquivo `.env`
- Executa `scheduler.py`

## 6. Fluxo de Execução

1. **Inicialização**:

   - Carrega variáveis de ambiente
   - Inicializa banco de dados SQLite
   - Configura scheduler com intervalo

2. **Ciclo de Processamento**:

   - Define intervalo de datas (por padrão: dia atual)
   - Faz requisição para API (página 1)
   - Processa cada agendamento da lista:
     - Verifica se ID já foi processado
     - Se novo: extrai dados, monta mensagem, envia, marca como processado
   - Continua paginação até `totalPaginas` ou lista vazia
   - Aguarda intervalo configurado
   - Repete ciclo

3. **Webhook** (executa em paralelo):
   - Recebe requisições GET para verificação
   - Recebe eventos POST para processamento adicional

## 7. Deploy na VPS

### 7.1. Preparação Local (Git)

```bash
cd ~/meu_repositorio_local
git init
git add .
git commit -m "bot clinica"
git remote add origin git@github.com:seuusuario/seurepo.git
git push -u origin main
```

### 7.2. Clonagem na VPS

```bash
cd ~
git clone git@github.com:seuusuario/seurepo.git clinica_bot
cd clinica_bot
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
# Criar .env com valores reais
```

### 7.3. Service Systemd

Arquivo: `/etc/systemd/system/clinica_bot.service`

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

### 7.4. Ativação do Service

```bash
sudo systemctl daemon-reload
sudo systemctl enable clinica_bot
sudo systemctl start clinica_bot
sudo journalctl -u clinica_bot -f
```

## 8. Testes

### 8.1. Teste Local

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
# Criar .env ou exportar variáveis
python3 main.py
```

### 8.2. Teste de Webhook

```bash
curl -X POST http://127.0.0.1:5000/webhook \
  -H "Content-Type: application/json" \
  -d '{"teste":123}'
```

### 8.3. Script de Teste (test_api_mock.py)

- Simula resposta da API sem chamar endpoint real
- Útil para testar processamento, templates e lógica de paginação
- Usa dados de exemplo baseados no formato esperado

## 9. Segurança

- ✅ Nunca commitar `.env` com credenciais
- ✅ Usar `.env.example` como template
- ✅ Configurar permissões restritas: `chmod 600 .env`
- ✅ Usar `EnvironmentFile` no systemd
- ✅ Considerar firewall (ufw) para limitar portas
- ✅ Limitar SSH por chave (desabilitar senha se possível)

## 10. Logs e Monitoramento

- Usar `journalctl -u clinica_bot -f` para logs em tempo real
- Adicionar logging estruturado no código (Python `logging` module)
- Considerar logs em arquivo separado para auditoria

## 11. Expansões Futuras

### 11.1. Reagendamento

- Escutar webhooks do provedor de mensagens
- Criar endpoint para receber pedidos de reagendamento
- Atualizar agendamento via API (se disponível)

### 11.2. Cancelamento

- Detectar cancelamentos na API
- Enviar mensagem de confirmação de cancelamento
- Atualizar registro em `storage.db`

### 11.3. Lembretes 24h Antes

- Adicionar tabela para lembretes agendados
- Calcular data/hora da consulta
- Disparar mensagem 24 horas antes
- Scheduler adicional ou integrado ao principal

### 11.4. Melhorias de Código

- Adicionar type hints
- Testes unitários para cada módulo
- Validação de dados de entrada
- Retry logic para chamadas de API
- Rate limiting para provedor de mensagens

## 12. Checklist de Implementação

- [ ] Criar estrutura de diretórios
- [ ] Implementar `requirements.txt`
- [ ] Implementar `.env.example`
- [ ] Implementar `api_client.py`
- [ ] Implementar `storage.py`
- [ ] Implementar `templates.py`
- [ ] Implementar `sender.py`
- [ ] Implementar `main.py`
- [ ] Implementar `scheduler.py`
- [ ] Implementar `webhook_app.py`
- [ ] Implementar `run.sh`
- [ ] Implementar `test_api_mock.py`
- [ ] Implementar `README.md`
- [ ] Testar localmente
- [ ] Configurar repositório Git
- [ ] Deploy na VPS
- [ ] Configurar systemd service
- [ ] Testar em produção
- [ ] Monitorar logs

## 13. Notas de Implementação

### 13.1. Paginação

- API pode retornar `totalPaginas` ou não
- Implementar fallback: se não houver `totalPaginas`, incrementar página até lista vazia
- Tratar casos onde API retorna lista vazia diretamente

### 13.2. Campos Variáveis

- API pode usar diferentes nomes de campos (ex: `paciente_nome` vs `nomePaciente`)
- Implementar fallbacks com `or` e múltiplos `.get()`
- Ajustar conforme resposta real da API

### 13.3. Formatação de Telefone

- Remover caracteres não numéricos antes de enviar
- Padronizar formato conforme provedor (ex: adicionar country code)
- Validar formato antes de enviar

### 13.4. Tratamento de Erros

- HTTP errors: usar `raise_for_status()` e capturar exceções
- Erros de envio: logar mas não interromper processamento
- Erros de banco: tratar `IntegrityError` (ID duplicado)

### 13.5. Webhook em Produção

- Não usar `app.run()` em produção
- Configurar Gunicorn ou similar
- Criar service systemd separado para webhook
- Configurar reverse proxy (nginx) se necessário

## 14. Estrutura Final Esperada

```
clinica_bot/
├── .env                    # Não commitado
├── .env.example
├── storage.db              # Criado automaticamente
├── requirements.txt
├── api_client.py
├── storage.py
├── sender.py
├── templates.py
├── main.py
├── scheduler.py
├── webhook_app.py
├── run.sh
├── test_api_mock.py
├── README.md
└── plan.md                 # Este arquivo
```
