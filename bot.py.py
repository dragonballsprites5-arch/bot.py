import os
import discord
from discord.ext import commands
import json # Importa a biblioteca JSON

# --- Configurações Iniciais ---
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# Nome do arquivo onde as fichas serão salvas
FICHA_FILE = "fichas.json"

# Limites de Rank para cada atributo
rank_limits = {
    "I": 1,
    "II": 2,
    "III": 3,
    "IV": 4,
    "V": 5
}

# Atributos base que o jogador pode distribuir pontos
atributos_validos = ["DMG", "HP", "FOR", "DEF", "RES", "MAG", "INT", "AGI", "VEL"]

# Atributos que podem receber bônus diretos (inclui os atributos base e os calculados)
bonus_validos = atributos_validos + ["LOCOMOCAO", "KRITOS", "PR"]

# Limites de valor para cada atributo por Rank
atributos_com_limite = {
    "DMG": {"I": 20, "II": 45, "III": 99, "IV": 120, "V": 200},
    "HP": {"I": 800, "II": 1800, "III": 2750, "IV": 3200, "V": 4500},
    "FOR": {"I": 35, "II": 80, "III": 150, "IV": 200, "V": 300},
    "DEF": {"I": 10, "II": 25, "III": 30, "IV": 50, "V": 100},
    "RES": {"I": 100, "II": 150, "III": 250, "IV": 325, "V": 400},
    "MAG": {"I": 50, "II": 150, "III": 200, "IV": 350, "V": 500},
    "INT": {"I": 90, "II": 110, "III": 125, "IV": 140, "V": 230},
    "AGI": {"I": 100, "II": 150, "III": 200, "IV": 325, "V": 450},
    "VEL": {"I": 50, "II": 80, "III": 100, "IV": 150, "V": 200}
}

# Dicionário para armazenar os dados dos usuários em memória (será carregado do arquivo)
users = {}

# --- Funções de Salvamento e Carregamento ---
def salvar_dados():
    """Salva o dicionário 'users' em um arquivo JSON."""
    with open(FICHA_FILE, "w") as f:
        json.dump(users, f, indent=4) # indent=4 para formatação legível

def carregar_dados():
    """Carrega o dicionário 'users' de um arquivo JSON. Retorna um dicionário vazio se o arquivo não existir ou houver erro."""
    if os.path.exists(FICHA_FILE):
        try:
            with open(FICHA_FILE, "r") as f:
                return json.load(f)
        except json.JSONDecodeError:
            print(f"Erro ao ler o arquivo {FICHA_FILE}. Criando um novo.")
            return {}
    return {}

# --- Funções de Cálculo e Atualização ---
def calcular_locomocao(vel, bonus_locomocao):
    """
    Calcula o valor da locomoção.
    Locomoção começa com 4 e só é influenciada pela VEL quando VEL >= 50.
    """
    if vel < 50:
        return 4 + bonus_locomocao
    else:
        return (vel // 10) + bonus_locomocao

def calcular_pr(res, bonus_pr):
    """Calcula os Pontos de Resistência (PR)."""
    return (20 + (res // 15)) + bonus_pr

def calcular_kritos(pts_mag, bonus_kritos):
    """Calcula o valor de Kritos."""
    # Kritos agora usa a MAG do status, não os pontos gastos, para refletir bônus etc.
    return (40 + (users[str(list(users.keys())[0])]["status"]["MAG"] * 2)) + bonus_kritos 


def atualizar_status(user):
    """
    Atualiza os atributos calculados do usuário com base nos pontos gastos
    e bônus. Aplica os limites de rank.
    """
    status = user["status"]
    pts_gastos = user["pts_gastos"]
    bonus = user.get("bonus", {attr: 0 for attr in bonus_validos})

    # Zera status e aplica bônus diretos de atributos base
    for key in atributos_validos:
        status[key] = bonus.get(key, 0)

    # Aplica os pontos gastos aos atributos, com cálculos específicos
    for attr, pts in pts_gastos.items():
        if attr == "DEF":
            status["DEF"] += pts * 1
            status["RES"] += pts * 1
        elif attr == "RES":
            status["RES"] += pts * 2
            status["HP"] += pts * 2
        elif attr == "INT":
            status["INT"] += pts * 2
        elif attr == "AGI":
            status["AGI"] += pts * 2
            status["VEL"] += pts * 1
        elif attr == "VEL":
            status["VEL"] += pts * 2
            status["AGI"] += pts * 1
        elif attr == "HP":
            status["HP"] += pts * 5
            status["RES"] += pts * 2
        elif attr == "FOR":
            status["FOR"] += pts * 4
            status["RES"] += pts * 4
            status["DEF"] += (pts // 5) * 1
        elif attr == "MAG":
            status["MAG"] += pts * 2
        elif attr == "DMG":
            status["DMG"] += pts * 2
            status["FOR"] += pts * 2
            status["MAG"] += pts * 1

    # Aplica os limites de rank aos atributos
    for attr in atributos_validos:
        rank = user["ranks"].get(attr, "I")
        limite = atributos_com_limite[attr][rank]
        if status[attr] > limite:
            status[attr] = limite
            
async def enviar_ou_atualizar_ficha(ctx, user_id):
    """
    Envia ou atualiza a mensagem da ficha do usuário no canal.
    Agora inclui a menção do usuário no início da ficha e separa os status.
    """
    user = users[user_id]
    status = user["status"]
    pts_gastos = user["pts_gastos"]
    ranks = user["ranks"]
    bonus = user.get("bonus", {attr: 0 for attr in bonus_validos})

    # Calcula os status derivados (Locomoção, PR, Kritos)
    loc = calcular_locomocao(status["VEL"], bonus.get("LOCOMOCAO", 0))
    pr = calcular_pr(status["RES"], bonus.get("PR", 0))
    kritos = calcular_kritos(status["MAG"], bonus.get("KRITOS", 0)) # Usando status["MAG"] aqui

    # Constrói a seção de Atributos Base
    texto_atributos_base = ""
    # Explicitamente lista apenas os atributos que NÃO são HP, DEF, DMG para esta seção
    atributos_para_listar_base = [attr for attr in atributos_validos if attr not in ["HP", "DEF", "DMG"]]
    for attr in atributos_para_listar_base:
        texto_atributos_base += f"• {attr} ({ranks[attr]}): {status[attr]} [Gastos: {pts_gastos[attr]}]\n"

    # Constrói a seção de Status de Combate (agora incluindo os ranks)
    texto_status_combate = (
        f"• Vitalidade (HP) ({ranks['HP']}): {status['HP']} [Gastos: {pts_gastos['HP']}]\n"
        f"• Defesa (DEF) ({ranks['DEF']}): {status['DEF']} [Gastos: {pts_gastos['DEF']}]\n"
        f"• Dano (DMG) ({ranks['DMG']}): {status['DMG']} [Gastos: {pts_gastos['DMG']}]\n"
    )

    # Constrói a seção de Status Gerais (os que são calculados)
    texto_status_gerais = (
        f"• Kritos: {kritos}\n"
        f"• Pontos de Resistência (PR): {pr}\n"
        f"• Locomoção: {loc} metros\n"
    )

    # Constrói a mensagem da ficha completa
    mensagem_ficha = (
        f"{ctx.author.mention}\n"
        "# :bar_chart: Ficha de Atributos\n\n"
        f"```\nPontos Livres: {user['pontos']}\nPontos Gastos: {sum(pts_gastos.values())}\n```\n"
        
        "## :muscle: Atributos Base\n"
        f"```\n{texto_atributos_base}```\n"
        
        "## :crossed_swords: Status de Combate\n"
        f"```\n{texto_status_combate}```\n"

        "## :brain: Status Derivados\n"
        f"```\n{texto_status_gerais}```\n"
    )

    # Tenta editar a mensagem da ficha existente, se houver
    try:
        if user.get("ficha_channel_id") and user.get("ficha_message_id"):
            channel = bot.get_channel(user["ficha_channel_id"])
            if channel:
                old_message = await channel.fetch_message(user["ficha_message_id"])
                await old_message.edit(content=mensagem_ficha)
                return
            else:
                # Se o canal não foi encontrado (ex: foi apagado), zera as IDs
                user["ficha_channel_id"] = None
                user["ficha_message_id"] = None
    except discord.NotFound:
        # Mensagem não encontrada, então envia uma nova
        user["ficha_channel_id"] = None
        user["ficha_message_id"] = None
        pass
    except discord.Forbidden:
        await ctx.send(f":x: | **{ctx.author.mention}**, **Erro:** O bot não tem permissão para editar a mensagem da ficha. Por favor, verifique as permissões no canal.")
        pass
    except Exception as e:
        print(f"Erro inesperado ao tentar editar a mensagem da ficha: {e}")
        pass

    # Se a mensagem não existe ou não pôde ser editada, envia uma nova
    new_message = await ctx.send(mensagem_ficha)
    user["ficha_message_id"] = new_message.id
    user["ficha_channel_id"] = new_message.channel.id


# --- Eventos do Bot ---
@bot.event
async def on_ready():
    """Confirma que o bot está online e conectado e carrega os dados."""
    print(f"Bot conectado como {bot.user}")
    global users # Declara 'users' como global para poder modificá-lo
    users = carregar_dados()
    print("Fichas carregadas com sucesso!")

# --- Comandos do Bot ---
@bot.command()
async def criar(ctx):
    """
    Cria uma nova ficha para o usuário que usou o comando.
    """
    user_id = str(ctx.author.id)
    if user_id in users:
        await ctx.send(f":information_source: | **{ctx.author.mention}**, você **já tem** uma ficha criada. Use `!ficha` para ver ou `!resetar` para criar uma nova.")
        return
    
    initial_bonus = {attr: 0 for attr in bonus_validos}

    users[user_id] = {
        "pts_gastos": {attr: 0 for attr in atributos_validos},
        "bonus": initial_bonus,
        "status": {attr: 0 for attr in atributos_validos},
        "pontos": 35,
        "ranks": {attr: "I" for attr in atributos_validos},
        "ficha_message_id": None,
        "ficha_channel_id": None,
    }
    atualizar_status(users[user_id])
    salvar_dados() # Salva os dados após criar a ficha
    await ctx.send(f":fire: | **Ficha Gerada para {ctx.author.mention}** com **35 pontos** para distribuir.")

@bot.command()
async def setrank(ctx, atributo: str, rank: str):
    """
    Define o rank de um atributo para o usuário.
    Ex: !setrank FOR V
    """
    atributo = atributo.upper()
    rank = rank.upper()
    user_id = str(ctx.author.id)
    if user_id not in users:
        await ctx.send(f":information_source: | **{ctx.author.mention}**, você precisa criar sua ficha primeiro com `!criar`.")
        return
    if atributo not in atributos_validos:
        await ctx.send(f":x: | **{ctx.author.mention}**, **Atributo inválido**. Use: `{', '.join(atributos_validos)}`.")
        return
    if rank not in rank_limits:
        await ctx.send(f":x: | **{ctx.author.mention}**, **Rank inválido**. Use: `{', '.join(rank_limits.keys())}`.")
        return
    
    # As linhas abaixo foram comentadas/removidas para permitir a diminuição do rank.
    # old_rank = users[user_id]["ranks"].get(atributo, "I")
    # if rank_limits[rank] < rank_limits[old_rank]:
    #     await ctx.send(f":x: | **{ctx.author.mention}**, você **não pode diminuir** o rank de **{atributo}** de **{old_rank}** para **{rank}**.")
    #     return

    users[user_id]["ranks"][atributo] = rank
    atualizar_status(users[user_id])
    salvar_dados() # Salva os dados após alterar o rank
    await ctx.send(f":trophy: | **{ctx.author.mention}**, Rank do atributo **{atributo}** definido para **{rank}**.")
    await enviar_ou_atualizar_ficha(ctx, user_id)

@bot.command()
async def add(ctx, atributo: str, valor: int):
    """
    Adiciona pontos a um atributo do usuário.
    Ex: !add FOR 5
    """
    atributo = atributo.upper()
    user_id = str(ctx.author.id)
    if user_id not in users:
        await ctx.send(f":information_source: | **{ctx.author.mention}**, você precisa criar sua ficha primeiro com `!criar`.")
        return
    if atributo not in atributos_validos:
        await ctx.send(f":x: | **{ctx.author.mention}**, **Atributo inválido** para adicionar pontos. Use: `{', '.join(atributos_validos)}`.")
        return
    if valor <= 0:
        await ctx.send(f":x: | **{ctx.author.mention}**, o valor a ser adicionado deve ser **positivo**.")
        return
    user = users[user_id]
    if valor > user["pontos"]:
        await ctx.send(f":x: | **{ctx.author.mention}**, você não tem pontos suficientes. Pontos disponíveis: **{user['pontos']}**.")
        return

    temp_pts_gastos = user["pts_gastos"].copy()
    temp_pts_gastos[atributo] += valor
    
    temp_status = {attr: 0 for attr in atributos_validos}
    temp_bonus_base = {k: v for k, v in user["bonus"].items() if k in atributos_validos}

    for key in atributos_validos:
        temp_status[key] = temp_bonus_base.get(key, 0)

    for attr_calc, pts_calc in temp_pts_gastos.items():
        if attr_calc == "DEF":
            temp_status["DEF"] += pts_calc * 1
            temp_status["RES"] += pts_calc * 1
        elif attr_calc == "RES":
            temp_status["RES"] += pts_calc * 2
            temp_status["HP"] += pts_calc * 2
        elif attr_calc == "INT":
            temp_status["INT"] += pts_calc * 2
        elif attr_calc == "AGI":
            temp_status["AGI"] += pts_calc * 2
            temp_status["VEL"] += pts_calc * 1
        elif attr_calc == "VEL":
            temp_status["VEL"] += pts_calc * 2
            temp_status["AGI"] += pts_calc * 1
        elif attr_calc == "HP":
            temp_status["HP"] += pts_calc * 5
            temp_status["RES"] += pts_calc * 2
        elif attr_calc == "FOR":
            temp_status["FOR"] += pts_calc * 4
            temp_status["RES"] += pts_calc * 4
            temp_status["DEF"] += (pts_calc // 5) * 1
        elif attr_calc == "MAG":
            temp_status["MAG"] += pts_calc * 2
        elif attr_calc == "DMG":
            temp_status["DMG"] += pts_calc * 2
            temp_status["FOR"] += pts_calc * 2
            temp_status["MAG"] += pts_calc * 1

    rank = user["ranks"].get(atributo, "I")
    limite = atributos_com_limite[atributo][rank]

    if temp_status[atributo] > limite and atributo in atributos_validos:
        await ctx.send(f":x: | **{ctx.author.mention}**, adicionar **{valor}** pontos em **{atributo}** faria você ultrapassar o limite de **{limite}** para o seu rank **{rank}** neste atributo. Tente um valor menor ou aumente seu rank.")
        return

    user["pts_gastos"][atributo] += valor
    user["pontos"] -= valor
    atualizar_status(user)
    salvar_dados() # Salva os dados após adicionar pontos
    await ctx.send(f":sparkles: | **{ctx.author.mention}**, adicionado **{valor}** pontos em **{atributo}**. Pontos restantes: **{user['pontos']}**.")
    await enviar_ou_atualizar_ficha(ctx, user_id)

@bot.command()
async def remover(ctx, atributo: str, valor: int):
    """
    Remove pontos de um atributo do usuário.
    Ex: !remover FOR 2
    """
    atributo = atributo.upper()
    user_id = str(ctx.author.id)
    if user_id not in users:
        await ctx.send(f":information_source: | **{ctx.author.mention}**, você precisa criar sua ficha primeiro com `!criar`.")
        return
    if atributo not in atributos_validos:
        await ctx.send(f":x: | **{ctx.author.mention}**, **Atributo inválido** para remover pontos gastos. Use: `{', '.join(atributos_validos)}`.")
        return
    if valor <= 0:
        await ctx.send(f":x: | **{ctx.author.mention}**, o valor a ser removido deve ser **positivo**.")
        return
    user = users[user_id]
    if valor > user["pts_gastos"][atributo]:
        await ctx.send(f":x: | **{ctx.author.mention}**, você **não pode remover mais** do que gastou em **{atributo}** (atualmente **{user['pts_gastos'][atributo]}**).")
        return
    user["pts_gastos"][atributo] -= valor
    user["pontos"] += valor
    atualizar_status(user)
    salvar_dados() # Salva os dados após remover pontos
    await ctx.send(f":scissors: | **{ctx.author.mention}**, removido **{valor}** pontos de **{atributo}**. Pontos disponíveis: **{user['pontos']}**.")
    await enviar_ou_atualizar_ficha(ctx, user_id)

@bot.command()
async def addbonus(ctx, atributo: str, valor: int):
    """
    Adiciona um bônus direto a um atributo ou status calculado.
    Ex: !addbonus LOCOMOCAO 1
    """
    atributo = atributo.upper()
    user_id = str(ctx.author.id)
    if user_id not in users:
        await ctx.send(f":information_source: | **{ctx.author.mention}**, crie sua ficha primeiro com `!criar`.")
        return
    if atributo not in bonus_validos:
        await ctx.send(f":x: | **{ctx.author.mention}**, **Atributo ou status inválido** para adicionar bônus. Use: `{', '.join(bonus_validos)}`.")
        return
    
    users[user_id]["bonus"][atributo] += valor
    atualizar_status(users[user_id])
    salvar_dados() # Salva os dados após adicionar bônus
    await ctx.send(f":gift: | **{ctx.author.mention}**, bônus de **+{valor}** adicionado em **{atributo}**.")
    await enviar_ou_atualizar_ficha(ctx, user_id)

@bot.command()
async def removerbonus(ctx, atributo: str, valor: int):
    """
    Remove um bônus direto de um atributo ou status calculado.
    Ex: !removerbonus KRITOS 5
    """
    atributo = atributo.upper()
    user_id = str(ctx.author.id)
    if user_id not in users:
        await ctx.send(f":information_source: | **{ctx.author.mention}**, crie sua ficha primeiro com `!criar`.")
        return
    if atributo not in bonus_validos:
        await ctx.send(f":x: | **{ctx.author.mention}**, **Atributo ou status inválido** para remover bônus. Use: `{', '.join(bonus_validos)}`.")
        return
    
    if users[user_id]["bonus"][atributo] - valor < 0:
        await ctx.send(f":x: | **{ctx.author.mention}**, você **não pode remover mais bônus** do que possui em **{atributo}** (atualmente **{users[user_id]['bonus'][atributo]}**).")
        return

    users[user_id]["bonus"][atributo] -= valor
    atualizar_status(users[user_id])
    salvar_dados() # Salva os dados após remover bônus
    await ctx.send(f":wastebasket: | **{ctx.author.mention}**, bônus de **-{valor}** removido de **{atributo}**.")
    await enviar_ou_atualizar_ficha(ctx, user_id)

@bot.command()
@commands.has_permissions(manage_messages=True) # Permissão para gerenciar mensagens, comum para moderadores
async def addpontos(ctx, membro: discord.Member, valor: int):
    """
    Adiciona pontos livres para um membro específico. (Comando para moderadores)
    Uso: !addpontos @membro <valor>
    """
    user_id = str(membro.id)
    if user_id not in users:
        await ctx.send(f":x: | O usuário **{membro.display_name}** não tem uma ficha criada.")
        return
    if valor <= 0:
        await ctx.send(":x: | O valor a ser adicionado deve ser **positivo**.")
        return
    users[user_id]["pontos"] += valor
    salvar_dados() # Salva os dados após adicionar pontos
    await ctx.send(f":moneybag: | **{valor}** pontos extras adicionados para **{membro.display_name}**. Ele(a) agora tem **{users[user_id]['pontos']}** pontos livres.")
    await enviar_ou_atualizar_ficha(ctx, user_id)

@addpontos.error
async def addpontos_error(ctx, error):
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f":x: | **{ctx.author.mention}**, uso correto: `!addpontos @membro <valor>`")
    elif isinstance(error, commands.BadArgument):
        await ctx.send(f":x: | **{ctx.author.mention}**, por favor, mencione um membro válido e forneça um número para o valor.")
    elif isinstance(error, commands.MissingPermissions):
        await ctx.send(f":x: | **{ctx.author.mention}**, você não tem permissão para usar este comando. Apenas moderadores podem adicionar pontos.")


@bot.command()
@commands.has_permissions(manage_messages=True) # Permissão para gerenciar mensagens, comum para moderadores
async def removerpontos(ctx, membro: discord.Member, valor: int):
    """
    Remove pontos livres de um membro específico. (Comando para moderadores)
    Uso: !removerpontos @membro <valor>
    """
    user_id = str(membro.id)
    if user_id not in users:
        await ctx.send(f":x: | O usuário **{membro.display_name}** não tem uma ficha criada.")
        return
    if valor <= 0:
        await ctx.send(":x: | O valor a ser removido deve ser **positivo**.")
        return
    
    if users[user_id]["pontos"] < valor:
        await ctx.send(f":x: | **{membro.display_name}** não tem pontos suficientes para remover. Ele(a) possui **{users[user_id]['pontos']}** pontos livres.")
        return

    users[user_id]["pontos"] -= valor
    salvar_dados() # Salva os dados após remover pontos
    await ctx.send(f":dollar: | **{valor}** pontos removidos de **{membro.display_name}**. Ele(a) agora tem **{users[user_id]['pontos']}** pontos livres.")
    await enviar_ou_atualizar_ficha(ctx, user_id)

@removerpontos.error
async def removerpontos_error(ctx, error):
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f":x: | **{ctx.author.mention}**, uso correto: `!removerpontos @membro <valor>`")
    elif isinstance(error, commands.BadArgument):
        await ctx.send(f":x: | **{ctx.author.mention}**, por favor, mencione um membro válido e forneça um número para o valor.")
    elif isinstance(error, commands.MissingPermissions):
        await ctx.send(f":x: | **{ctx.author.mention}**, você não tem permissão para usar este comando. Apenas moderadores podem remover pontos.")

@bot.command()
async def ficha(ctx):
    """
    Exibe a ficha do usuário que usou o comando.
    """
    user_id = str(ctx.author.id)
    if user_id not in users:
        await ctx.send(f":information_source: | **{ctx.author.mention}**, você não tem ficha criada. Use `!criar` para criar uma.")
        return
    await enviar_ou_atualizar_ficha(ctx, user_id)

@bot.command()
async def apagar(ctx):
    """
    Apaga a mensagem da sua ficha do chat, mas mantém seus dados salvos.
    Útil se a ficha for enviada no canal errado.
    """
    user_id = str(ctx.author.id)
    if user_id not in users:
        await ctx.send(f":information_source: | **{ctx.author.mention}**, você não tem uma ficha criada para apagar.")
        return

    user_data = users[user_id]
    ficha_channel_id = user_data.get("ficha_channel_id")
    ficha_message_id = user_data.get("ficha_message_id")

    if ficha_channel_id and ficha_message_id:
        try:
            channel = bot.get_channel(ficha_channel_id)
            if channel:
                message = await channel.fetch_message(ficha_message_id)
                await message.delete()
                # Zera as IDs para que o bot envie uma nova ficha na próxima vez, mas os dados permanecem salvos
                user_data["ficha_message_id"] = None
                user_data["ficha_channel_id"] = None
                salvar_dados() # Salva o estado atualizado (IDs zeradas)
                await ctx.send(f":broom: | **{ctx.author.mention}**, a mensagem da sua ficha foi apagada do chat.")
            else:
                await ctx.send(f":x: | **{ctx.author.mention}**, não consegui encontrar o canal da sua ficha para apagar a mensagem. Seus dados continuam salvos.")
        except discord.NotFound:
            await ctx.send(f":x: | **{ctx.author.mention}**, a mensagem da sua ficha não foi encontrada no chat (talvez já tenha sido apagada). Seus dados continuam salvos.")
            # Zera as IDs para que o bot envie uma nova ficha na próxima vez
            user_data["ficha_message_id"] = None
            user_data["ficha_channel_id"] = None
            salvar_dados() # Salva o estado atualizado (IDs zeradas)
        except discord.Forbidden:
            await ctx.send(f":x: | **{ctx.author.mention}**, o bot não tem permissão para apagar mensagens neste canal. Por favor, verifique as permissões do bot.")
        except Exception as e:
            await ctx.send(f":x: | **{ctx.author.mention}**, ocorreu um erro ao tentar apagar sua ficha: `{e}`")
            print(f"Erro ao apagar ficha para {ctx.author.id}: {e}")
    else:
        await ctx.send(f":information_source: | **{ctx.author.mention}**, não há uma mensagem de ficha registrada para você apagar. Use `!ficha` para enviá-la novamente.")

@bot.command()
async def resetar(ctx):
    """
    Reseta a ficha do usuário, apagando todos os dados.
    """
    user_id = str(ctx.author.id)
    if user_id in users:
        # Tenta apagar a mensagem da ficha antes de resetar os dados
        user_data = users[user_id]
        ficha_channel_id = user_data.get("ficha_channel_id")
        ficha_message_id = user_data.get("ficha_message_id")

        if ficha_channel_id and ficha_message_id:
            try:
                channel = bot.get_channel(ficha_channel_id)
                if channel:
                    message = await channel.fetch_message(ficha_message_id)
                    await message.delete()
            except (discord.NotFound, discord.Forbidden):
                # Ignora erros se a mensagem já não existir ou se não tiver permissão
                pass
            except Exception as e:
                print(f"Erro ao tentar apagar mensagem da ficha durante reset para {ctx.author.id}: {e}")
        
        del users[user_id]
        salvar_dados() # Salva o estado sem a ficha resetada
        await ctx.send(f":recycle: | **{ctx.author.mention}**, sua ficha foi **resetada**.")
    else:
        await ctx.send(f":information_source: | **{ctx.author.mention}**, você **não possui** ficha para resetar.")

# Inicia o bot com o token do ambiente
bot.run(os.getenv("DISCORD_BOT_TOKEN"))