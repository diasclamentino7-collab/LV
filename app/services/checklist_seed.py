"""The couple's original 13-month wedding-planning checklist.

This is reference data, not application logic: each entry becomes one
``Task`` row (title/category/priority/due_date) when imported via
``scripts/import_default_checklist.py``. Monthly chapters get a due date on
the last day of that month; the wedding-day chapter gets the wedding date
itself, so ``app.services.checklist.checklist_snapshot`` can group tasks
into chapters purely from ``due_date`` with no extra schema needed.
"""

from __future__ import annotations

import calendar
from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.core import ProjectSettings, User
from app.models.planning import Task
from app.services.activity import record_activity

DEFAULT_WEDDING_DATE = datetime(2027, 9, 4, 10, 0, tzinfo=ZoneInfo("Europe/Lisbon"))


def _month_end(year: int, month: int) -> date:
    return date(year, month, calendar.monthrange(year, month)[1])


def default_checklist_tasks(wedding_date: date) -> list[dict[str, str | date]]:
    """Return the full seed checklist as flat task dicts, ready to insert."""

    tasks: list[dict[str, str | date]] = []

    def month(year: int, mo: int, sections: list[tuple[str, list[tuple[str, str]]]]) -> None:
        due = _month_end(year, mo)
        for category, items in sections:
            for title, priority in items:
                tasks.append(
                    {"title": title, "category": category, "priority": priority, "due_date": due}
                )

    def wedding_day(sections: list[tuple[str, list[tuple[str, str]]]]) -> None:
        for category, items in sections:
            for title, priority in items:
                tasks.append(
                    {
                        "title": title,
                        "category": category,
                        "priority": priority,
                        "due_date": wedding_date,
                    }
                )

    # Agosto de 2026 — Bases do casamento
    month(
        2026,
        8,
        [
            (
                "Convidados",
                [
                    ("Fazer a lista inicial de convidados do Vítor", "Alta"),
                    ("Fazer a lista inicial de convidados da Leonor", "Alta"),
                    ("Juntar as duas listas e remover duplicados", "Alta"),
                    ("Separar convidados indispensáveis, desejados e opcionais", "Alta"),
                    ("Identificar adultos, crianças e acompanhantes", "Alta"),
                    ("Definir o número máximo de convidados", "Alta"),
                    ("Criar uma pequena lista de suplentes", "Média"),
                    ("Identificar convidados com mobilidade reduzida", "Média"),
                    ("Identificar familiares que poderão precisar de transporte", "Média"),
                ],
            ),
            (
                "Orçamento",
                [
                    ("Definir o orçamento máximo do casamento", "Alta"),
                    ("Definir quanto podem gastar sem recorrer a dívidas", "Alta"),
                    ("Reservar 10% a 15% para imprevistos", "Alta"),
                    ("Definir o valor máximo por convidado na quinta", "Alta"),
                    ("Dividir o orçamento por categorias", "Alta"),
                    ("Criar uma tabela de despesas, sinais e valores em falta", "Alta"),
                    ("Definir quem contribui para cada despesa", "Média"),
                    ("Definir o orçamento aproximado da lua de mel", "Média"),
                ],
            ),
            (
                "Visão geral",
                [
                    ("Confirmar a data de 4 de setembro de 2027", "Alta"),
                    ("Confirmar que a cerimónia será de manhã", "Alta"),
                    ("Confirmar que o casamento termina até às 22h00", "Alta"),
                    ("Definir a região onde procurar quintas", "Alta"),
                    ("Definir a distância máxima entre o Salão e a quinta", "Média"),
                    ("Definir as três maiores prioridades do casamento", "Alta"),
                    ("Definir os elementos em que podem poupar", "Média"),
                    ("Criar uma pasta digital para propostas, contratos e recibos", "Média"),
                ],
            ),
        ],
    )

    # Setembro de 2026 — Salão do Reino e pesquisa de quintas
    month(
        2026,
        9,
        [
            (
                "Cerimónia",
                [
                    ("Falar com os anciãos sobre a realização do casamento no Salão", "Alta"),
                    ("Confirmar a disponibilidade do Salão para a data", "Alta"),
                    ("Confirmar a hora aproximada disponível para a cerimónia", "Alta"),
                    ("Informar-se sobre as orientações aplicáveis à cerimónia", "Alta"),
                    ("Confirmar o que é permitido em termos de decoração", "Média"),
                    ("Confirmar as condições para fotografia e vídeo", "Média"),
                    ("Confirmar a utilização do equipamento de som", "Média"),
                    ("Fazer uma lista de irmãos que poderiam realizar o discurso", "Alta"),
                ],
            ),
            (
                "Pesquisa de quintas",
                [
                    ("Criar uma lista de 10 a 15 quintas", "Alta"),
                    ("Confirmar disponibilidade para 4 de setembro de 2027", "Alta"),
                    ("Pedir brochuras, menus e preços", "Alta"),
                    ("Confirmar preço por adulto", "Alta"),
                    ("Confirmar preço por criança", "Alta"),
                    ("Perguntar se existe número mínimo de convidados", "Alta"),
                    ("Confirmar se o IVA está incluído", "Alta"),
                    ("Confirmar o que está incluído no preço por pessoa", "Alta"),
                    ("Perguntar se o cocktail está incluído", "Alta"),
                    ("Perguntar se o bolo está incluído", "Média"),
                    ("Perguntar se a ceia está incluída ou é cobrada à parte", "Alta"),
                    ("Confirmar o horário de encerramento", "Alta"),
                    ("Perguntar se existem custos por horas adicionais", "Alta"),
                    ("Confirmar estacionamento", "Média"),
                    ("Confirmar acessibilidade", "Média"),
                    ("Confirmar o plano alternativo para chuva", "Alta"),
                    ("Selecionar três a cinco quintas finalistas", "Alta"),
                    ("Marcar as visitas", "Alta"),
                ],
            ),
        ],
    )

    # Outubro de 2026 — Visitar e reservar a quinta
    month(
        2026,
        10,
        [
            (
                "Durante as visitas",
                [
                    ("Ver a sala principal", "Alta"),
                    ("Ver a zona do cocktail", "Alta"),
                    ("Ver o espaço exterior", "Média"),
                    ("Ver o local previsto para o corte do bolo", "Média"),
                    ("Ver pessoalmente o plano alternativo para chuva", "Alta"),
                    ("Avaliar estacionamento e acessos", "Média"),
                    ("Avaliar casas de banho e condições de limpeza", "Média"),
                    ("Confirmar se o espaço é exclusivo", "Média"),
                    ("Confirmar se aceitam fornecedores externos", "Média"),
                    ("Confirmar quem faz a montagem e desmontagem", "Média"),
                    ("Perguntar onde ficam guardados os objetos dos noivos", "Média"),
                    ("Avaliar a organização e disponibilidade da equipa", "Alta"),
                    ("Registar vantagens e desvantagens de cada espaço", "Alta"),
                    ("Fotografar os espaços para comparação", "Baixa"),
                ],
            ),
            (
                "Escolha e contrato",
                [
                    ("Comparar o custo total de cada proposta", "Alta"),
                    ("Comparar menus e serviços incluídos", "Alta"),
                    ("Escolher a quinta", "Alta"),
                    ("Pedir o contrato completo", "Alta"),
                    ("Ler todas as cláusulas", "Alta"),
                    ("Confirmar os preços por escrito", "Alta"),
                    ("Confirmar o horário de encerramento às 22h00", "Alta"),
                    ("Confirmar a política de cancelamento", "Alta"),
                    ("Confirmar as condições de alteração da data", "Alta"),
                    ("Confirmar os prazos de pagamento", "Alta"),
                    ("Confirmar quando deve ser entregue o número final", "Alta"),
                    ("Confirmar as condições do plano de chuva", "Alta"),
                    ("Assinar o contrato", "Alta"),
                    ("Pagar o sinal", "Alta"),
                    ("Guardar contrato e comprovativo", "Alta"),
                ],
            ),
        ],
    )

    # Novembro de 2026 — Fotografia, vídeo e discurso
    month(
        2026,
        11,
        [
            (
                "Fotografia e vídeo",
                [
                    ("Pesquisar fotógrafos e videógrafos", "Alta"),
                    ("Pedir pelo menos três propostas", "Alta"),
                    ("Ver galerias de casamentos completos", "Alta"),
                    ("Ver vídeos completos, além dos pequenos teasers", "Alta"),
                    ("Confirmar o estilo de fotografia e edição", "Média"),
                    ("Confirmar as horas de cobertura", "Alta"),
                    ("Confirmar o número de profissionais presentes", "Média"),
                    ("Confirmar os custos de deslocação", "Alta"),
                    ("Confirmar se o álbum está incluído", "Média"),
                    ("Confirmar se existe vídeo completo e vídeo curto", "Média"),
                    ("Confirmar os prazos de entrega", "Média"),
                    ("Escolher o fornecedor", "Alta"),
                    ("Ler e assinar o contrato", "Alta"),
                    ("Pagar o sinal", "Alta"),
                ],
            ),
            (
                "Cerimónia e família",
                [
                    ("Escolher o irmão que gostariam que realizasse o discurso", "Alta"),
                    ("Falar com o irmão e confirmar a disponibilidade", "Alta"),
                    ("Confirmar os teus pais como padrinhos", "Média"),
                    ("Conversar com a mãe da Leonor sobre a entrada", "Média"),
                    ("Definir provisoriamente a entrada do Vítor", "Média"),
                    ("Definir provisoriamente a entrada da Leonor", "Média"),
                    ("Escolher uma pessoa de confiança para coordenar o dia", "Média"),
                ],
            ),
        ],
    )

    # Dezembro de 2026 — Estilo e comunicação inicial
    month(
        2026,
        12,
        [
            (
                "Estilo",
                [
                    ("Definir o estilo geral do casamento", "Média"),
                    ("Definir a paleta de cores", "Média"),
                    ("Definir o nível de formalidade", "Média"),
                    ("Criar um moodboard", "Baixa"),
                    ("Definir o estilo das flores", "Média"),
                    ("Definir o estilo da decoração", "Média"),
                    ("Verificar o que a quinta já inclui", "Alta"),
                ],
            ),
            (
                "Convidados",
                [
                    ("Rever a lista provisória", "Alta"),
                    ("Atualizar o número estimado de convidados", "Alta"),
                    ("Recolher contactos e moradas", "Média"),
                    ("Criar uma ficha por família ou convite", "Média"),
                    ("Registar crianças e possíveis acompanhantes", "Média"),
                ],
            ),
            (
                "Save the Date",
                [
                    ("Definir se será digital, impresso ou misto", "Média"),
                    ("Criar o Save the Date", "Média"),
                    ("Rever nomes, data e informação", "Alta"),
                    ("Enviar o Save the Date", "Média"),
                ],
            ),
            (
                "Revisão financeira",
                [
                    ("Rever todas as despesas realizadas", "Alta"),
                    ("Confirmar sinais pagos", "Alta"),
                    ("Atualizar o orçamento restante", "Alta"),
                    ("Ajustar categorias que estejam acima do orçamento", "Alta"),
                ],
            ),
        ],
    )

    # Janeiro de 2027 — Vestido, música e beleza
    month(
        2027,
        1,
        [
            (
                "Vestido da Leonor",
                [
                    ("Definir o orçamento do vestido", "Alta"),
                    ("Selecionar lojas e ateliers", "Alta"),
                    ("Marcar provas", "Alta"),
                    ("Experimentar diferentes estilos", "Alta"),
                    ("Escolher ou encomendar o vestido", "Alta"),
                    ("Confirmar o prazo de entrega", "Alta"),
                    ("Marcar as provas e ajustes", "Alta"),
                    ("Guardar contrato, fatura e comprovativos", "Média"),
                ],
            ),
            (
                "Música",
                [
                    ("Definir o formato musical da receção", "Média"),
                    ("Pesquisar DJ ou responsável pela música", "Média"),
                    ("Pedir propostas", "Média"),
                    ("Confirmar equipamento incluído", "Alta"),
                    ("Confirmar microfones para discursos", "Alta"),
                    ("Confirmar os limites de som da quinta", "Alta"),
                    ("Confirmar o horário máximo da música", "Alta"),
                    ("Escolher e reservar o fornecedor", "Média"),
                ],
            ),
            (
                "Beleza",
                [
                    ("Pesquisar maquilhadoras", "Alta"),
                    ("Pesquisar cabeleireiras", "Alta"),
                    ("Ver trabalhos anteriores", "Média"),
                    ("Pedir orçamentos", "Média"),
                    ("Reservar maquilhadora", "Alta"),
                    ("Reservar cabeleireira", "Alta"),
                    ("Confirmar se se deslocam ao local da preparação", "Alta"),
                ],
            ),
        ],
    )

    # Fevereiro de 2027 — Fato, flores, convites e lua de mel
    month(
        2027,
        2,
        [
            (
                "Fato do Vítor",
                [
                    ("Definir o orçamento", "Média"),
                    ("Escolher o estilo e a cor", "Média"),
                    ("Visitar lojas ou alfaiates", "Alta"),
                    ("Escolher ou encomendar o fato", "Alta"),
                    ("Confirmar os prazos de ajustes", "Alta"),
                    ("Escolher camisa e acessórios principais", "Média"),
                ],
            ),
            (
                "Flores e decoração",
                [
                    ("Pesquisar floristas", "Média"),
                    ("Pedir propostas detalhadas", "Média"),
                    ("Confirmar flores disponíveis em setembro", "Média"),
                    ("Definir bouquet", "Média"),
                    ("Definir lapelas", "Média"),
                    ("Definir centros de mesa", "Média"),
                    ("Definir decoração da mesa dos noivos", "Média"),
                    ("Definir decoração do bolo", "Baixa"),
                    ("Escolher e reservar florista", "Média"),
                ],
            ),
            (
                "Convites",
                [
                    ("Definir o estilo dos convites", "Média"),
                    ("Definir convite digital, impresso ou misto", "Média"),
                    ("Escrever o texto", "Alta"),
                    ("Incluir data, hora e locais", "Alta"),
                    ("Incluir prazo de confirmação", "Alta"),
                    ("Incluir contacto para respostas", "Alta"),
                    ("Começar o site do casamento", "Média"),
                ],
            ),
            (
                "Lua de mel",
                [
                    ("Definir o orçamento definitivo", "Alta"),
                    ("Escolher o destino", "Alta"),
                    ("Comparar voos e alojamentos", "Alta"),
                    ("Verificar validade dos documentos", "Alta"),
                    ("Verificar bagagem incluída", "Média"),
                    ("Fazer as reservas principais", "Alta"),
                ],
            ),
        ],
    )

    # Março de 2027 — Processo civil, alianças e logística
    month(
        2027,
        3,
        [
            (
                "Processo civil",
                [
                    ("Contactar a Conservatória", "Alta"),
                    ("Confirmar os documentos necessários", "Alta"),
                    ("Confirmar os prazos aplicáveis ao processo", "Alta"),
                    ("Confirmar onde será realizado o ato civil", "Alta"),
                    ("Informar-se sobre o regime de bens", "Alta"),
                    ("Confirmar se são necessárias testemunhas", "Alta"),
                    ("Reunir a documentação pedida", "Alta"),
                    ("Planear a abertura do processo para o período indicado", "Alta"),
                ],
            ),
            (
                "Alianças",
                [
                    ("Definir o orçamento", "Média"),
                    ("Pesquisar modelos e materiais", "Média"),
                    ("Experimentar tamanhos", "Alta"),
                    ("Escolher as alianças", "Alta"),
                    ("Escolher a gravação", "Média"),
                    ("Encomendar as alianças", "Alta"),
                    ("Guardar fatura e garantia", "Média"),
                ],
            ),
            (
                "Transportes",
                [
                    ("Calcular o percurso entre o Salão e a quinta", "Alta"),
                    ("Definir o transporte dos noivos", "Média"),
                    ("Definir o transporte dos pais e padrinhos", "Média"),
                    ("Identificar convidados sem transporte", "Média"),
                    ("Avaliar a necessidade de transporte coletivo", "Média"),
                    ("Preparar indicações para os convidados", "Média"),
                ],
            ),
        ],
    )

    # Abril de 2027 — Convites, menu e cerimónia
    month(
        2027,
        4,
        [
            (
                "Convites",
                [
                    ("Finalizar o design", "Média"),
                    ("Rever todos os nomes e informações", "Alta"),
                    ("Finalizar o site do casamento", "Média"),
                    ("Preparar a lista de distribuição", "Alta"),
                    ("Enviar os convites oficiais", "Alta"),
                    ("Definir o prazo de resposta para junho ou julho", "Alta"),
                    ("Criar um sistema para registar confirmações", "Alta"),
                ],
            ),
            (
                "Menu e quinta",
                [
                    ("Marcar a prova do menu", "Alta"),
                    ("Escolher o cocktail", "Média"),
                    ("Escolher as entradas", "Média"),
                    ("Escolher o prato principal", "Alta"),
                    ("Escolher a opção vegetariana", "Alta"),
                    ("Escolher o menu infantil", "Média"),
                    ("Definir opções para alergias e intolerâncias", "Alta"),
                    ("Escolher sobremesas", "Média"),
                    ("Confirmar bebidas incluídas", "Alta"),
                    ("Escolher a ceia", "Média"),
                    ("Confirmar o custo da ceia", "Alta"),
                ],
            ),
            (
                "Cerimónia",
                [
                    ("Definir a ordem provisória das entradas", "Média"),
                    ("Definir a entrada dos pais do Vítor", "Média"),
                    ("Definir a entrada do Vítor", "Média"),
                    ("Definir a entrada da Leonor", "Média"),
                    ("Definir quem transporta as alianças", "Média"),
                    ("Definir os lugares reservados", "Média"),
                    ("Confirmar quem recebe e orienta os convidados", "Média"),
                ],
            ),
        ],
    )

    # Maio de 2027 — Vestuário, bolo e personalização
    month(
        2027,
        5,
        [
            (
                "Vestuário",
                [
                    ("Fazer uma prova do vestido", "Alta"),
                    ("Confirmar os ajustes necessários", "Alta"),
                    ("Escolher sapatos da Leonor", "Média"),
                    ("Escolher acessórios da Leonor", "Média"),
                    ("Escolher roupa interior adequada ao vestido", "Média"),
                    ("Fazer uma prova do fato", "Alta"),
                    ("Escolher sapatos do Vítor", "Média"),
                    ("Escolher gravata e acessórios", "Média"),
                    ("Experimentar o conjunto completo do Vítor", "Alta"),
                ],
            ),
            (
                "Bolo",
                [
                    ("Pesquisar ou confirmar o fornecedor", "Média"),
                    ("Escolher o estilo", "Média"),
                    ("Escolher o sabor e o recheio", "Média"),
                    ("Confirmar o número de doses", "Alta"),
                    ("Confirmar transporte e conservação", "Alta"),
                    ("Confirmar quem serve o bolo", "Alta"),
                    ("Definir o horário aproximado do corte", "Média"),
                ],
            ),
            (
                "Personalização",
                [
                    ("Definir se haverá livro de honra", "Baixa"),
                    ("Definir se haverá photobooth", "Baixa"),
                    ("Definir se haverá slideshow ou vídeo", "Baixa"),
                    ("Definir se haverá discursos na quinta", "Média"),
                    ("Definir quem poderá discursar", "Média"),
                    ("Definir uma duração máxima para os discursos", "Média"),
                    ("Preparar agradecimento aos pais", "Média"),
                    ("Planear atividades simples para crianças", "Média"),
                    ("Evitar colocar demasiados momentos no programa", "Alta"),
                ],
            ),
        ],
    )

    # Junho de 2027 — Confirmações e escolhas finais
    month(
        2027,
        6,
        [
            (
                "Convidados",
                [
                    ("Acompanhar as respostas aos convites", "Alta"),
                    ("Contactar convidados que ainda não responderam", "Alta"),
                    ("Registar adultos e crianças confirmados", "Alta"),
                    ("Registar restrições alimentares", "Alta"),
                    ("Registar mobilidade reduzida", "Alta"),
                    ("Registar necessidades de transporte", "Média"),
                    ("Atualizar o número estimado para a quinta", "Alta"),
                ],
            ),
            (
                "Música",
                [
                    ("Escolher a música da entrada dos padrinhos", "Média"),
                    ("Escolher a música da entrada do Vítor", "Média"),
                    ("Escolher a música da entrada da Leonor", "Alta"),
                    ("Escolher a música da saída", "Média"),
                    ("Escolher música para o cocktail", "Média"),
                    ("Escolher música ambiente para o almoço", "Média"),
                    ("Escolher a música do corte do bolo", "Média"),
                    ("Criar uma lista de músicas a evitar", "Média"),
                    ("Confirmar quem controla a música em cada momento", "Média"),
                ],
            ),
            (
                "Decoração",
                [
                    ("Aprovar os centros de mesa", "Média"),
                    ("Aprovar o bouquet", "Média"),
                    ("Aprovar as lapelas", "Média"),
                    ("Aprovar a decoração da mesa dos noivos", "Média"),
                    ("Aprovar a decoração do bolo", "Baixa"),
                    ("Confirmar montagem e desmontagem", "Alta"),
                    ("Confirmar quem transporta elementos decorativos", "Média"),
                    ("Rever o plano alternativo para chuva", "Alta"),
                ],
            ),
            (
                "Cronograma",
                [
                    ("Criar a primeira versão do horário do dia", "Alta"),
                    ("Definir a hora da cerimónia", "Alta"),
                    ("Definir a hora de chegada dos convidados", "Alta"),
                    ("Calcular o tempo de deslocação para a quinta", "Alta"),
                    ("Definir a hora do cocktail", "Alta"),
                    ("Definir a hora do almoço", "Alta"),
                    ("Definir a hora do corte do bolo", "Média"),
                    ("Definir a hora da ceia", "Alta"),
                    ("Confirmar o encerramento às 22h00", "Alta"),
                ],
            ),
        ],
    )

    # Julho de 2027 — Plano de mesas e organização detalhada
    month(
        2027,
        7,
        [
            (
                "Lista final provisória",
                [
                    ("Fechar as confirmações pendentes", "Alta"),
                    ("Confirmar novamente convidados essenciais", "Média"),
                    ("Preparar a lista provisória final", "Alta"),
                    ("Confirmar alergias e intolerâncias", "Alta"),
                    ("Confirmar cadeiras de bebé", "Média"),
                    ("Confirmar convidados com mobilidade reduzida", "Alta"),
                ],
            ),
            (
                "Plano de mesas",
                [
                    ("Obter a planta da sala", "Alta"),
                    ("Confirmar o formato e a capacidade das mesas", "Alta"),
                    ("Definir a mesa dos noivos", "Média"),
                    ("Definir os lugares dos pais e padrinhos", "Alta"),
                    ("Agrupar familiares e amigos", "Média"),
                    ("Evitar conflitos familiares", "Alta"),
                    ("Colocar idosos em lugares acessíveis", "Média"),
                    ("Considerar as necessidades das crianças", "Média"),
                    ("Criar a primeira versão do plano", "Alta"),
                    ("Preparar alterações para desistências", "Média"),
                ],
            ),
            (
                "Fotografia e vídeo",
                [
                    ("Criar a lista de fotografias familiares obrigatórias", "Média"),
                    ("Incluir fotografias com os pais do Vítor", "Média"),
                    ("Incluir fotografias com a mãe da Leonor", "Média"),
                    ("Incluir fotografias com padrinhos e familiares idosos", "Média"),
                    ("Escolher alguém para reunir as pessoas", "Média"),
                    ("Definir os locais das fotografias do casal", "Média"),
                    ("Definir o horário aproximado da golden hour", "Média"),
                    ("Confirmar até que momento o fotógrafo permanece", "Alta"),
                ],
            ),
            (
                "Beleza e provas",
                [
                    ("Fazer a prova de maquilhagem", "Média"),
                    ("Fazer a prova de penteado", "Média"),
                    ("Fotografar o resultado das provas", "Baixa"),
                    ("Confirmar o horário de preparação", "Alta"),
                    ("Definir quem estará com a Leonor durante a preparação", "Média"),
                    ("Definir quem estará com o Vítor durante a preparação", "Média"),
                ],
            ),
        ],
    )

    # Agosto de 2027 — Confirmações finais
    month(
        2027,
        8,
        [
            (
                "Quinta e convidados",
                [
                    ("Comunicar o número final dentro do prazo do contrato", "Alta"),
                    ("Entregar a lista de restrições alimentares", "Alta"),
                    ("Finalizar o plano de mesas", "Alta"),
                    ("Enviar o plano definitivo à quinta", "Alta"),
                    ("Criar o painel de distribuição das mesas", "Média"),
                    ("Preparar marcadores dos lugares", "Média"),
                    ("Confirmar o menu e a ceia", "Alta"),
                    ("Confirmar o horário de todos os serviços", "Alta"),
                ],
            ),
            (
                "Fornecedores",
                [
                    ("Confirmar novamente todos os fornecedores", "Alta"),
                    ("Confirmar horários de chegada", "Alta"),
                    ("Confirmar moradas e acessos", "Alta"),
                    ("Confirmar contactos de emergência", "Alta"),
                    ("Rever todos os contratos", "Alta"),
                    ("Confirmar pagamentos realizados", "Alta"),
                    ("Preparar pagamentos ainda pendentes", "Alta"),
                    ("Enviar o cronograma do dia aos fornecedores", "Alta"),
                ],
            ),
            (
                "Cerimónia",
                [
                    ("Confirmar definitivamente o irmão do discurso", "Alta"),
                    ("Confirmar a ordem das entradas", "Alta"),
                    ("Confirmar os lugares reservados", "Alta"),
                    ("Confirmar quem transporta as alianças", "Alta"),
                    ("Confirmar quem abre e prepara o Salão", "Alta"),
                    ("Confirmar o equipamento de som", "Alta"),
                    ("Confirmar as orientações relativas a fotografia", "Média"),
                    ("Fazer um pequeno ensaio, quando possível", "Média"),
                ],
            ),
            (
                "Vestuário e alianças",
                [
                    ("Fazer a prova final do vestido", "Alta"),
                    ("Fazer os últimos ajustes", "Alta"),
                    ("Levantar o vestido", "Alta"),
                    ("Fazer a prova final do fato", "Alta"),
                    ("Levantar o fato", "Alta"),
                    ("Experimentar os conjuntos completos", "Alta"),
                    ("Adaptar os sapatos antes do casamento", "Média"),
                    ("Levantar e verificar as alianças", "Alta"),
                    ("Confirmar medidas e gravações", "Alta"),
                    ("Definir quem guarda as alianças", "Alta"),
                ],
            ),
            (
                "Processo civil",
                [
                    ("Confirmar que o processo está concluído ou devidamente marcado", "Alta"),
                    ("Confirmar todos os documentos necessários", "Alta"),
                    ("Confirmar eventuais testemunhas pedidas pela Conservatória", "Alta"),
                    ("Guardar documentos numa pasta segura", "Alta"),
                    ("Entregar a pasta à pessoa responsável", "Alta"),
                ],
            ),
            (
                "Preparação final",
                [
                    ("Finalizar os discursos e agradecimentos", "Média"),
                    ("Preparar o kit de emergência", "Média"),
                    ("Preparar mala da noite de núpcias", "Média"),
                    ("Preparar malas da lua de mel", "Média"),
                    ("Confirmar documentos de viagem", "Alta"),
                    ("Confirmar transporte para a lua de mel", "Média"),
                    ("Distribuir responsabilidades por pessoas de confiança", "Alta"),
                    ("Rever o plano de chuva", "Alta"),
                    ("Reduzir compromissos desnecessários", "Média"),
                ],
            ),
            (
                "Semana do casamento",
                [
                    ("Confirmar quinta, fotógrafo, música, transporte e beleza", "Alta"),
                    ("Confirmar o irmão responsável pelo discurso", "Alta"),
                    ("Confirmar as alianças e documentos", "Alta"),
                    ("Entregar decoração e materiais aos responsáveis", "Alta"),
                    ("Confirmar quem transporta cada objeto", "Alta"),
                    ("Preparar roupa, sapatos e acessórios completos", "Alta"),
                    ("Passar ou vaporizar as roupas", "Média"),
                    ("Carregar telemóveis e baterias externas", "Média"),
                    ("Preparar água e pequenos snacks", "Média"),
                    ("Confirmar a previsão meteorológica", "Média"),
                    ("Ativar o plano de chuva, caso seja necessário", "Alta"),
                    ("Evitar alterações de última hora", "Alta"),
                    ("Dormir e descansar adequadamente", "Alta"),
                ],
            ),
            (
                "Dia anterior",
                [
                    ("Confirmar que todos receberam o cronograma", "Alta"),
                    ("Separar alianças e documentos", "Alta"),
                    ("Entregar os objetos à pessoa responsável", "Alta"),
                    ("Confirmar o transporte", "Alta"),
                    ("Preparar o pequeno-almoço do dia seguinte", "Média"),
                    ("Preparar água para os dois", "Média"),
                    ("Organizar as roupas em local seguro", "Alta"),
                    ("Desligar-se da organização a uma hora definida", "Média"),
                    ("Evitar resolver detalhes não essenciais", "Alta"),
                    ("Dormir cedo", "Alta"),
                ],
            ),
        ],
    )

    # Dia do casamento — 4 de setembro de 2027
    wedding_day(
        [
            (
                "Preparação",
                [
                    ("Acordar com tempo", "Alta"),
                    ("Tomar o pequeno-almoço", "Alta"),
                    ("Beber água", "Alta"),
                    ("Iniciar cabelo e maquilhagem no horário previsto", "Alta"),
                    ("Iniciar a preparação do Vítor no horário previsto", "Alta"),
                    ("Fazer fotografias da preparação", "Média"),
                    ("Confirmar alianças e documentos", "Alta"),
                    ("Confirmar o transporte para o Salão", "Alta"),
                ],
            ),
            (
                "Cerimónia",
                [
                    ("Confirmar a chegada do irmão do discurso", "Alta"),
                    ("Confirmar som e microfones", "Alta"),
                    ("Reservar os lugares dos pais e padrinhos", "Alta"),
                    ("Receber e orientar os convidados", "Média"),
                    ("Entrada dos pais do Vítor", "Média"),
                    ("Entrada do Vítor", "Alta"),
                    ("Entrada da Leonor", "Alta"),
                    ("Realizar a cerimónia", "Alta"),
                    ("Fazer fotografias com a família", "Média"),
                    ("Organizar a saída para a quinta", "Média"),
                ],
            ),
            (
                "Quinta",
                [
                    ("Receber os convidados", "Alta"),
                    ("Servir o cocktail", "Alta"),
                    ("Fazer algumas fotografias do casal", "Média"),
                    ("Fazer a entrada na sala", "Alta"),
                    ("Servir o almoço", "Alta"),
                    ("Realizar discursos e agradecimentos", "Média"),
                    ("Cortar o bolo durante a tarde", "Alta"),
                    ("Fazer fotografias na golden hour", "Média"),
                    ("Servir a ceia perto das 19h30", "Alta"),
                    ("Fazer os agradecimentos finais perto das 21h15", "Média"),
                    ("Começar as despedidas por volta das 21h30", "Alta"),
                    ("Encerrar até às 22h00", "Alta"),
                    ("Confirmar a recolha dos objetos pessoais", "Alta"),
                ],
            ),
            (
                "Depois do casamento",
                [
                    ("Confirmar que todos os pagamentos ficaram concluídos", "Alta"),
                    ("Devolver materiais alugados", "Alta"),
                    ("Recolher decoração e objetos pessoais", "Alta"),
                    ("Guardar contratos e comprovativos", "Média"),
                    ("Limpar e conservar o vestido e o fato", "Média"),
                    ("Enviar agradecimentos aos convidados", "Média"),
                    ("Agradecer pessoalmente aos pais, padrinhos e ajudantes", "Média"),
                    ("Selecionar fotografias para o álbum", "Baixa"),
                    ("Guardar cópias das fotografias e vídeos", "Média"),
                    ("Atualizar documentos pessoais, quando aplicável", "Alta"),
                    ("Fazer o balanço final do orçamento", "Média"),
                ],
            ),
        ]
    )

    return tasks


def import_default_checklist(db: Session, current_user: User | None) -> int:
    """Insert the seed checklist into ``db``, skipping anything already there.

    Safe to call more than once (e.g. clicking the button twice): tasks are
    matched on (title, category, due_date), so nothing is duplicated. Also
    sets the wedding date in the project settings if it isn't configured
    yet, since the whole plan — and the checklist page's milestone chapter
    — is built around it.
    """

    settings = db.scalar(select(ProjectSettings))
    if settings is None:
        settings = ProjectSettings()
        db.add(settings)
    if settings.wedding_date is None:
        settings.wedding_date = DEFAULT_WEDDING_DATE

    existing = {(t.title, t.category, t.due_date) for t in db.scalars(select(Task)).all()}
    seed = default_checklist_tasks(DEFAULT_WEDDING_DATE.date())
    user_id = current_user.id if current_user else None

    created = 0
    for item in seed:
        key = (item["title"], item["category"], item["due_date"])
        if key in existing:
            continue
        db.add(
            Task(
                title=item["title"],
                category=item["category"],
                priority=item["priority"],
                due_date=item["due_date"],
                status="Pendente",
                created_by_id=user_id,
                updated_by_id=user_id,
            )
        )
        created += 1

    if created:
        record_activity(
            db,
            user_id,
            "criou",
            f"importou a checklist completa do casamento ({created} tarefas)",
            "checklist",
        )
    db.commit()
    return created
