"""Exceções próprias do assistente.

Em vez de deixar escapar os erros técnicos da biblioteca `anthropic` para o resto
da aplicação, convertemo-los nestas exceções. Assim, quem usa o assistente (por
exemplo, a interface de terminal) só precisa de conhecer estas classes, e a
mensagem de cada uma já está escrita de forma compreensível para o utilizador.
"""


class AssistantError(Exception):
    """Classe-base: todos os erros do assistente herdam desta."""


class ConfigurationError(AssistantError):
    """Problema de configuração (chave em falta ou inválida, modelo errado...).

    Não adianta tentar outra vez: é preciso corrigir o ficheiro .env.
    """


class InvalidQuestionError(AssistantError):
    """A pergunta do cliente não é válida (vazia ou demasiado longa)."""


class TemporaryServiceError(AssistantError):
    """Falha temporária (sem internet, demasiados pedidos, servidor em baixo).

    Faz sentido o utilizador tentar novamente daqui a pouco.
    """


class AssistantAPIError(AssistantError):
    """Outro erro devolvido pela API que não se resolve só com nova tentativa."""
