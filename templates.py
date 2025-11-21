from string import Template

CONFIRMACAO = Template(
    "Oi, $primeiro_nome! 💚\n"
    "Sua consulta foi confirmada para $data_agenda às $hora_agenda.\n"
    "Procedimento(s): $procedimentos\n\n"
    "Se tiver alguma dúvida, responda essa mensagem."
)

CANCELAMENTO = Template(
    "Olá, $primeiro_nome! 💚\n\n"
    "Seu agendamento para **$tipo_consulta**, marcado para **$data_agenda às $hora_agenda**, foi **cancelado**.\n\n"
    "📞 Em caso de dúvidas ou para reagendar, é só responder essa mensagem.\n\n"
    "Estamos à disposição para te atender da melhor forma! ✨"
)

