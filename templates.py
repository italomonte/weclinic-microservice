from string import Template

CONFIRMACAO = Template(
    "Oi, $primeiro_nome! 💚\n"
    "Sua consulta foi confirmada para $data_agenda às $hora_agenda.\n"
    "Procedimento(s): $procedimentos\n\n"
    "Se tiver alguma dúvida, responda essa mensagem."
)

