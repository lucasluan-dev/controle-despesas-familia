import hashlib
import html
import json
import sqlite3
import tempfile
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta

import pandas as pd
import streamlit as st

DB_FILE = f"{tempfile.gettempdir()}/despesas.db"
ONLINE_WINDOW_MINUTES = 5
CROWN_AVATAR_VALUE = "admin::crown"

AVATARES_PADRAO = {
    "Anonimo": "👤",
    "Gato": "🐱",
    "Cachorro": "🐶",
    "Leao": "🦁",
    "Paisagem": "🏞️",
    "Montanha": "🏔️",
    "Foguete": "🚀",
}

TIMES_FUTEBOL = {
    "Atletico Mineiro": "Clube Atletico Mineiro",
    "Cruzeiro": "Cruzeiro Esporte Clube",
    "Flamengo": "CR Flamengo",
    "Corinthians": "Sport Club Corinthians Paulista",
    "Palmeiras": "SE Palmeiras",
    "Sao Paulo": "Sao Paulo FC",
    "Santos": "Santos FC",
    "Gremio": "Gremio FBPA",
    "Internacional": "Sport Club Internacional",
    "Vasco": "CR Vasco da Gama",
    "Real Madrid": "Real Madrid CF",
    "Barcelona": "FC Barcelona",
    "Atletico de Madrid": "Atletico Madrid",
    "Manchester United": "Manchester United F.C.",
    "Manchester City": "Manchester City F.C.",
    "Liverpool": "Liverpool F.C.",
    "Chelsea": "Chelsea F.C.",
    "Bayern de Munique": "FC Bayern Munich",
    "PSG": "Paris Saint-Germain F.C.",
    "Juventus": "Juventus FC",
}

MESES_PT_BR = {
    1: "janeiro", 2: "fevereiro", 3: "marco", 4: "abril", 5: "maio", 6: "junho",
    7: "julho", 8: "agosto", 9: "setembro", 10: "outubro", 11: "novembro", 12: "dezembro",
}


def get_conn():
    return sqlite3.connect(DB_FILE, check_same_thread=False)


def hash_senha(senha):
    return hashlib.sha256(senha.encode("utf-8")).hexdigest()


def agora_iso():
    return datetime.now().replace(microsecond=0).isoformat(sep=" ")


@st.cache_data(ttl=86400, show_spinner=False)
def carregar_escudos_times_web():
    titulos = "|".join(TIMES_FUTEBOL.values())
    params = {
        "action": "query",
        "format": "json",
        "prop": "pageimages",
        "piprop": "thumbnail",
        "pithumbsize": 64,
        "titles": titulos,
    }
    url = "https://pt.wikipedia.org/w/api.php?" + urllib.parse.urlencode(params)
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        pages = data.get("query", {}).get("pages", {})
        by_title = {}
        for _, page in pages.items():
            t = page.get("title")
            thumb = page.get("thumbnail", {}).get("source")
            if t and thumb:
                by_title[t] = thumb
        out = {}
        for nome, titulo in TIMES_FUTEBOL.items():
            if titulo in by_title:
                out[nome] = by_title[titulo]
        return out
    except Exception:
        return {}


def init_db(conn):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            senha_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'USUARIO',
            avatar_icone TEXT NOT NULL DEFAULT '👤',
            nome_exibicao TEXT,
            email TEXT,
            telefone TEXT,
            ultimo_acesso TEXT,
            criado_em TEXT NOT NULL
        )
        """
    )

    cols_usuarios = conn.execute("PRAGMA table_info(usuarios)").fetchall()
    col_names_usuarios = [c[1] for c in cols_usuarios]
    if "role" not in col_names_usuarios:
        conn.execute("ALTER TABLE usuarios ADD COLUMN role TEXT NOT NULL DEFAULT 'USUARIO'")
    if "avatar_icone" not in col_names_usuarios:
        conn.execute("ALTER TABLE usuarios ADD COLUMN avatar_icone TEXT NOT NULL DEFAULT '👤'")
    if "nome_exibicao" not in col_names_usuarios:
        conn.execute("ALTER TABLE usuarios ADD COLUMN nome_exibicao TEXT")
    if "email" not in col_names_usuarios:
        conn.execute("ALTER TABLE usuarios ADD COLUMN email TEXT")
    if "telefone" not in col_names_usuarios:
        conn.execute("ALTER TABLE usuarios ADD COLUMN telefone TEXT")
    if "ultimo_acesso" not in col_names_usuarios:
        conn.execute("ALTER TABLE usuarios ADD COLUMN ultimo_acesso TEXT")

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS avatars_times (
            nome_time TEXT PRIMARY KEY,
            imagem_url TEXT NOT NULL,
            atualizado_em TEXT NOT NULL
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS despesas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pessoa TEXT NOT NULL,
            descricao TEXT NOT NULL,
            valor REAL NOT NULL,
            data_vencimento TEXT NOT NULL,
            status_pagamento TEXT NOT NULL DEFAULT 'PENDENTE',
            data_pagamento TEXT,
            criado_por TEXT,
            info_adicional TEXT,
            criado_em TEXT NOT NULL
        )
        """
    )

    cols = conn.execute("PRAGMA table_info(despesas)").fetchall()
    col_names = [c[1] for c in cols]
    if "status_pagamento" not in col_names:
        conn.execute("ALTER TABLE despesas ADD COLUMN status_pagamento TEXT NOT NULL DEFAULT 'PENDENTE'")
    if "data_pagamento" not in col_names:
        conn.execute("ALTER TABLE despesas ADD COLUMN data_pagamento TEXT")
    if "criado_por" not in col_names:
        conn.execute("ALTER TABLE despesas ADD COLUMN criado_por TEXT")
    conn.commit()
    sincronizar_escudos_times(conn)


def sincronizar_escudos_times(conn):
    atuais = {r[0]: r[1] for r in conn.execute("SELECT nome_time, imagem_url FROM avatars_times").fetchall()}
    faltantes = [n for n in TIMES_FUTEBOL.keys() if n not in atuais]
    if not faltantes:
        return
    web = carregar_escudos_times_web()
    for nome in faltantes:
        url = web.get(nome)
        if url:
            conn.execute(
                "INSERT OR REPLACE INTO avatars_times (nome_time, imagem_url, atualizado_em) VALUES (?, ?, ?)",
                (nome, url, agora_iso()),
            )
    conn.commit()


def carregar_escudos_do_banco(conn):
    return {r[0]: r[1] for r in conn.execute("SELECT nome_time, imagem_url FROM avatars_times").fetchall()}


def montar_opcoes_avatar(role):
    opcoes = dict(AVATARES_PADRAO)
    if role == "ADMIN":
        opcoes["Coroa ADM"] = CROWN_AVATAR_VALUE
    for nome_time in TIMES_FUTEBOL.keys():
        opcoes[f"Time: {nome_time}"] = f"team::{nome_time}"
    return opcoes


def avatar_para_html(avatar_ref, escudos_cache, size=18):
    if avatar_ref == CROWN_AVATAR_VALUE:
        return "👑"
    if avatar_ref and avatar_ref.startswith("team::"):
        nome_time = avatar_ref.split("::", 1)[1]
        url = escudos_cache.get(nome_time)
        if url:
            nome_safe = html.escape(nome_time)
            return f'<img src="{url}" alt="{nome_safe}" width="{size}" height="{size}" style="border-radius:50%;vertical-align:middle;">'
        return "⚽"
    return html.escape(avatar_ref or "👤")


def criar_usuario(conn, username, senha, avatar_icone):
    username = username.strip().lower()
    total_usuarios = conn.execute("SELECT COUNT(*) FROM usuarios").fetchone()[0]
    role = "ADMIN" if total_usuarios == 0 else "USUARIO"
    if avatar_icone == CROWN_AVATAR_VALUE and role != "ADMIN":
        avatar_icone = AVATARES_PADRAO["Anonimo"]
    try:
        conn.execute(
            """
            INSERT INTO usuarios (username, senha_hash, role, avatar_icone, nome_exibicao, email, telefone, ultimo_acesso, criado_em)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (username, hash_senha(senha), role, avatar_icone, username, None, None, None, date.today().isoformat()),
        )
        conn.commit()
        return True, f"Usuario criado com sucesso como {role}."
    except sqlite3.IntegrityError:
        return False, "Esse usuario ja existe."


def atualizar_ultimo_acesso(conn, username):
    conn.execute("UPDATE usuarios SET ultimo_acesso = ? WHERE username = ?", (agora_iso(), username))
    conn.commit()


def obter_usuario(conn, username):
    return conn.execute(
        "SELECT username, role, avatar_icone, nome_exibicao, email, telefone FROM usuarios WHERE username = ?",
        (username,),
    ).fetchone()


def atualizar_perfil(conn, username, avatar_icone, nome_exibicao, email, telefone, role):
    if avatar_icone == CROWN_AVATAR_VALUE and role != "ADMIN":
        avatar_icone = AVATARES_PADRAO["Anonimo"]
    conn.execute(
        """
        UPDATE usuarios
        SET avatar_icone = ?, nome_exibicao = ?, email = ?, telefone = ?
        WHERE username = ?
        """,
        (
            avatar_icone,
            nome_exibicao.strip() if nome_exibicao else None,
            email.strip() if email else None,
            telefone.strip() if telefone else None,
            username,
        ),
    )
    conn.commit()


def autenticar_usuario(conn, username, senha):
    username = username.strip().lower()
    row = conn.execute(
        """
        SELECT id, username, role, avatar_icone, COALESCE(nome_exibicao, username)
        FROM usuarios
        WHERE username = ? AND senha_hash = ?
        """,
        (username, hash_senha(senha)),
    ).fetchone()
    if row:
        atualizar_ultimo_acesso(conn, row[1])
    return row


def listar_usuarios(conn):
    return pd.read_sql_query("SELECT username, role, avatar_icone, ultimo_acesso, criado_em FROM usuarios ORDER BY username ASC", conn)


def formatar_data_pt_br(data_iso):
    dt = date.fromisoformat(data_iso)
    return f"{dt.day:02d} de {MESES_PT_BR[dt.month]} de {dt.year}"


def formatar_data_hora_pt_br(data_hora_iso):
    if not data_hora_iso:
        return "Nunca"
    dt = datetime.fromisoformat(data_hora_iso)
    return f"{dt.day:02d}/{dt.month:02d}/{dt.year} {dt.hour:02d}:{dt.minute:02d}:{dt.second:02d}"


def formatar_moeda_br(valor):
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def usuario_esta_online(ultimo_acesso_iso):
    if not ultimo_acesso_iso:
        return False
    ultimo = datetime.fromisoformat(ultimo_acesso_iso)
    return datetime.now() - ultimo <= timedelta(minutes=ONLINE_WINDOW_MINUTES)


def calcular_status_real(data_vencimento_iso, status_informado):
    if status_informado == "PAGO":
        return "PAGO"
    venc = date.fromisoformat(data_vencimento_iso)
    return "ATRASADO" if venc < date.today() else "PENDENTE"


def add_despesa(conn, pessoa, descricao, valor, data_vencimento, status_pagamento, info_adicional, criado_por):
    status_real = calcular_status_real(data_vencimento, status_pagamento)
    conn.execute(
        """
        INSERT INTO despesas (pessoa, descricao, valor, data_vencimento, status_pagamento, criado_por, info_adicional, criado_em)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (pessoa, descricao, valor, data_vencimento, status_real, criado_por, info_adicional, date.today().isoformat()),
    )
    conn.commit()


def delete_despesa(conn, despesa_id):
    conn.execute("DELETE FROM despesas WHERE id = ?", (int(despesa_id),))
    conn.commit()


def atualizar_status_pagamento(conn, despesa_id, novo_status):
    if novo_status == "PAGO":
        conn.execute("UPDATE despesas SET status_pagamento = ?, data_pagamento = ? WHERE id = ?", ("PAGO", date.today().isoformat(), int(despesa_id)))
    else:
        conn.execute("UPDATE despesas SET status_pagamento = ?, data_pagamento = NULL WHERE id = ?", ("PENDENTE", int(despesa_id)))
    conn.commit()


def list_despesas(conn, pessoa, username, role):
    query = "SELECT id, pessoa, descricao, valor, data_vencimento, status_pagamento, data_pagamento, criado_por, info_adicional, criado_em FROM despesas"
    filtros = []
    params = []
    if role != "ADMIN":
        filtros.append("criado_por = ?")
        params.append(username)
    if role == "ADMIN" and pessoa != "Todos":
        filtros.append("pessoa = ?")
        params.append(pessoa)
    if filtros:
        query += " WHERE " + " AND ".join(filtros)
    query += " ORDER BY data_vencimento ASC, id DESC"
    return pd.read_sql_query(query, conn, params=tuple(params))


def build_aviso_vencimento(data_vencimento, status_pagamento):
    if status_pagamento == "PAGO":
        return ""
    dias = (date.fromisoformat(data_vencimento) - date.today()).days
    if dias < 0:
        return f"Atrasado ha {abs(dias)} dia(s)"
    if dias == 0:
        return "Vence hoje"
    if dias == 1:
        return "Vence amanha"
    return ""


def linha_por_status(row):
    status = row.get("status_real", row.get("Status real", "PENDENTE"))
    if status == "PAGO":
        cor = "rgba(60, 198, 138, 0.25)"
    elif status == "ATRASADO":
        cor = "rgba(244, 67, 54, 0.25)"
    else:
        venc = date.fromisoformat(row.get("data_vencimento", row.get("Data de vencimento")))
        cor = "rgba(255, 193, 7, 0.25)" if (venc - date.today()).days == 0 else ""
    return [f"background-color: {cor}" if cor else "" for _ in row]


def apply_theme():
    st.markdown(
        """
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Poppins:wght@500;600;700&display=swap');
            :root { --bg:#061529; --text:#eaf2ff; --muted:#9db7dd; --accent:#2f7df6; --accent-2:#69a7ff; --border:#1d3f68; }
            .stApp { background: radial-gradient(circle at 10% 10%, #133560 0%, rgba(19,53,96,0) 35%), radial-gradient(circle at 90% 20%, #1b4b85 0%, rgba(27,75,133,0) 30%), linear-gradient(170deg, #041022 0%, var(--bg) 55%, #020a16 100%); color: var(--text); }
            .session-box { font-family:'Poppins',sans-serif; background: rgba(255,255,255,0.04); border:1px solid var(--border); border-radius:12px; padding:.65rem .75rem; margin-bottom:.6rem; }
            .session-title { color:#cfe1ff; font-size:.75rem; letter-spacing:.06em; text-transform:uppercase; margin:0 0 .2rem 0; }
            .session-value { color:#fff; font-size:1rem; font-weight:600; margin:0; }
            .main-card { background: linear-gradient(160deg, rgba(17,44,78,0.95), rgba(11,30,56,0.93)); border:1px solid var(--border); border-radius:18px; padding:1.2rem; box-shadow:0 10px 30px rgba(0,0,0,.25); margin-bottom:1rem; }
            .title-text { font-size:2rem; font-weight:700; color:var(--text); margin:0; }
            .subtitle-text { color:var(--muted); margin-top:.2rem; margin-bottom:0; }
            div[data-testid="stMetric"], div[data-testid="stDataFrame"] { border:1px solid var(--border); border-radius:14px; overflow:hidden; }
            div[data-testid="stMetricValue"] { color:#fff !important; }
            .stButton > button, .stForm button { background: linear-gradient(120deg, var(--accent), var(--accent-2)) !important; color:#fff !important; border:none !important; border-radius:10px !important; font-weight:600 !important; }
            section[data-testid="stSidebar"] { background: linear-gradient(180deg, #081a33 0%, #061326 100%); border-right:1px solid var(--border); }
            label,.stMarkdown,.stTextInput label,.stNumberInput label,.stDateInput label,.stSelectbox label,.stSubheader { color:#fff !important; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def check_auth(conn):
    if st.session_state.get("authenticated"):
        return True
    st.markdown("### Acesso da Familia")
    aba_login, aba_cadastro = st.tabs(["Entrar", "Criar usuario"])
    with aba_login:
        usuario_login = st.text_input("Usuario", key="login_usuario")
        senha_login = st.text_input("Senha", type="password", key="login_senha")
        if st.button("Entrar", key="btn_entrar"):
            user = autenticar_usuario(conn, usuario_login, senha_login)
            if user:
                st.session_state["authenticated"] = True
                st.session_state["username"] = user[1]
                st.session_state["role"] = user[2]
                st.session_state["avatar_icone"] = user[3]
                st.session_state["nome_exibicao"] = user[4]
                st.rerun()
            st.error("Usuario ou senha invalidos.")

    with aba_cadastro:
        novo_usuario = st.text_input("Novo usuario", key="cad_usuario")
        nova_senha = st.text_input("Nova senha", type="password", key="cad_senha")
        confirmar_senha = st.text_input("Confirmar senha", type="password", key="cad_confirmar")
        total_usuarios = conn.execute("SELECT COUNT(*) FROM usuarios").fetchone()[0]
        role_novo = "ADMIN" if total_usuarios == 0 else "USUARIO"
        opcoes_avatar = montar_opcoes_avatar(role_novo)
        avatar_escolhido = st.selectbox("Escolha seu icone", list(opcoes_avatar.keys()), index=0, key="cad_avatar")
        if st.button("Criar conta", key="btn_criar"):
            if len(novo_usuario.strip()) < 3:
                st.error("Usuario deve ter pelo menos 3 caracteres.")
            elif len(nova_senha) < 6:
                st.error("Senha deve ter pelo menos 6 caracteres.")
            elif nova_senha != confirmar_senha:
                st.error("As senhas nao conferem.")
            else:
                ok, msg = criar_usuario(conn, novo_usuario, nova_senha, opcoes_avatar[avatar_escolhido])
                st.success(msg) if ok else st.error(msg)
    return False


def main():
    st.set_page_config(page_title="Controle de Despesas da Familia", page_icon="💰", layout="wide")
    apply_theme()
    conn = get_conn()
    init_db(conn)
    escudos_cache = carregar_escudos_do_banco(conn)

    if not check_auth(conn):
        st.stop()

    username = st.session_state.get("username", "")
    role = st.session_state.get("role", "USUARIO")
    avatar_icone = st.session_state.get("avatar_icone", "👤")
    nome_exibicao = st.session_state.get("nome_exibicao", username)
    atualizar_ultimo_acesso(conn, username)

    st.sidebar.markdown("### Sessao")
    st.sidebar.markdown(
        f"""
        <div class="session-box"><p class="session-title">Usuario</p><p class="session-value">{avatar_para_html(avatar_icone, escudos_cache)} {nome_exibicao}</p></div>
        <div class="session-box"><p class="session-title">Perfil</p><p class="session-value">{role}</p></div>
        """,
        unsafe_allow_html=True,
    )

    usuarios_df = listar_usuarios(conn)
    st.sidebar.markdown("### Usuarios cadastrados")
    for _, urow in usuarios_df.iterrows():
        avatar_html = avatar_para_html(urow["avatar_icone"], escudos_cache)
        st.sidebar.markdown(f"<div style='display:flex;align-items:center;gap:8px;margin-bottom:4px;'>{avatar_html}<span>{urow['username']}</span></div>", unsafe_allow_html=True)

    perfil = obter_usuario(conn, username)
    opcoes_avatar = montar_opcoes_avatar(role)
    avatar_ref = perfil[2] if perfil else avatar_icone
    nome_val = perfil[3] if perfil and perfil[3] else username
    email_val = perfil[4] if perfil and perfil[4] else ""
    tel_val = perfil[5] if perfil and perfil[5] else ""
    avatar_label = next((k for k, v in opcoes_avatar.items() if v == avatar_ref), "Anonimo")

    with st.sidebar.expander("⚙️ Editar Perfil"):
        novo_nome = st.text_input("Nome", value=nome_val)
        novo_email = st.text_input("Email", value=email_val)
        novo_telefone = st.text_input("Numero", value=tel_val)
        novo_avatar_label = st.selectbox("Seu icone", list(opcoes_avatar.keys()), index=list(opcoes_avatar.keys()).index(avatar_label) if avatar_label in opcoes_avatar else 0)
        if st.button("Salvar Perfil"):
            novo_avatar = opcoes_avatar[novo_avatar_label]
            atualizar_perfil(conn, username, novo_avatar, novo_nome, novo_email, novo_telefone, role)
            st.session_state["avatar_icone"] = novo_avatar
            st.session_state["nome_exibicao"] = novo_nome.strip() if novo_nome.strip() else username
            st.success("Perfil atualizado com sucesso.")
            st.rerun()
        if st.button("Sair"):
            st.session_state["authenticated"] = False
            st.session_state["username"] = ""
            st.session_state["role"] = ""
            st.session_state["avatar_icone"] = "👤"
            st.session_state["nome_exibicao"] = ""
            st.rerun()

    if role == "ADMIN":
        st.sidebar.markdown("### Status de acesso")
        status_df = usuarios_df.copy()
        status_df["online"] = status_df["ultimo_acesso"].apply(lambda x: "Online" if usuario_esta_online(x) else "Offline")
        status_df["ultimo_acesso_fmt"] = status_df["ultimo_acesso"].apply(formatar_data_hora_pt_br)
        st.sidebar.dataframe(status_df[["username", "role", "online", "ultimo_acesso_fmt"]], use_container_width=True, hide_index=True)

    st.markdown("""<div class="main-card"><p class="title-text">Controle de Despesas da Familia</p><p class="subtitle-text">Adicione despesas como em um site: nome, valor e data de vencimento.</p></div>""", unsafe_allow_html=True)

    st.sidebar.header("Filtro")
    pessoas_df = pd.read_sql_query("SELECT DISTINCT pessoa FROM despesas WHERE pessoa IS NOT NULL AND TRIM(pessoa) <> '' ORDER BY pessoa ASC", conn)
    pessoas = pessoas_df["pessoa"].tolist()
    if role == "ADMIN":
        busca_usuario = st.sidebar.text_input("Pesquisar usuario", value="", placeholder="Digite o nome...")
        termo = busca_usuario.strip().lower()
        pessoas_filtradas = [p for p in pessoas if termo in p.lower()] if termo else pessoas
        opcoes_filtro = ["Todos", *pessoas_filtradas] if pessoas_filtradas else ["Todos"]
        pessoa_filtro = st.sidebar.selectbox("Ver despesas de:", opcoes_filtro)
    else:
        st.sidebar.text_input("Ver despesas de:", value=username, disabled=True)
        pessoa_filtro = "Todos"

    st.subheader("Adicionar despesa")
    with st.form("form_despesa", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            pessoa = st.text_input("Pessoa")
            descricao = st.text_input("Nome da despesa")
            valor = st.number_input("Valor (R$)", min_value=0.0, step=1.0, format="%.2f")
        with col2:
            data_vencimento = st.date_input("Data de vencimento", value=date.today(), format="DD/MM/YYYY")
            status_pagamento = st.selectbox("Status", ["PENDENTE", "PAGO"], index=0)
            info_adicional = st.text_input("Informacoes adicionais")
        if st.form_submit_button("Salvar despesa"):
            if not pessoa.strip():
                st.error("Informe o nome da pessoa.")
            elif not descricao.strip():
                st.error("Informe o nome da despesa.")
            elif float(valor) <= 0:
                st.error("Informe um valor maior que zero.")
            else:
                add_despesa(conn, pessoa.strip(), descricao.strip(), float(valor), data_vencimento.isoformat(), status_pagamento, info_adicional.strip(), username)
                st.success("Despesa salva com sucesso.")

    st.subheader("Despesas cadastradas")
    df = list_despesas(conn, pessoa_filtro, username, role)
    if df.empty:
        st.info("Nenhuma despesa cadastrada ainda.")
        return

    df["status_real"] = df.apply(lambda row: calcular_status_real(row["data_vencimento"], row["status_pagamento"]), axis=1)
    df["aviso_vencimento"] = df.apply(lambda row: build_aviso_vencimento(row["data_vencimento"], row["status_real"]), axis=1)
    df["data_vencimento_pt"] = df["data_vencimento"].apply(formatar_data_pt_br)
    df["criado_em_pt"] = df["criado_em"].apply(formatar_data_pt_br)
    st.metric("Total Listado", formatar_moeda_br(float(df["valor"].sum())))

    df_exibicao = df[["id", "pessoa", "descricao", "valor", "data_vencimento", "data_vencimento_pt", "status_real", "aviso_vencimento", "info_adicional", "criado_em_pt"]].copy()
    df_exibicao["valor"] = df_exibicao["valor"].apply(formatar_moeda_br)
    df_exibicao = df_exibicao.rename(columns={"id":"Id","pessoa":"Pessoa","descricao":"Descricao","valor":"Valor","data_vencimento":"Data de vencimento","data_vencimento_pt":"Data de vencimento (pt)","status_real":"Status real","aviso_vencimento":"Aviso de vencimento","info_adicional":"Info adicional","criado_em_pt":"Criado em (pt)"})
    st.dataframe(df_exibicao.style.apply(linha_por_status, axis=1), use_container_width=True, hide_index=True)

    st.subheader("Sua Atividade")
    st.caption("Marque como pago ou exclua quando necessario.")
    for _, row in df.iterrows():
        c1, c2, c3, c4, c5 = st.columns([2.2, 3.2, 1.8, 1.3, 0.7])
        c1.write(f"{row['pessoa']} - {formatar_moeda_br(row['valor'])}")
        c2.write(f"{row['descricao']} ({formatar_data_pt_br(row['data_vencimento'])})")
        c3.write(row["status_real"])
        pode_editar = role == "ADMIN" or row.get("criado_por") == username
        if row["status_real"] == "PAGO":
            if c4.button("Desfazer", key=f"undo_{int(row['id'])}", disabled=not pode_editar):
                atualizar_status_pagamento(conn, int(row["id"]), "PENDENTE")
                st.warning("Pagamento desfeito.")
                st.rerun()
        else:
            if c4.button("Marcar como Pago", key=f"pay_{int(row['id'])}", disabled=not pode_editar):
                atualizar_status_pagamento(conn, int(row["id"]), "PAGO")
                st.success("Conta marcada como paga.")
                st.balloons()
                st.rerun()
        if c5.button("🗑️", key=f"del_{int(row['id'])}", disabled=not pode_editar):
            delete_despesa(conn, int(row["id"]))
            st.success("Despesa excluida com sucesso.")
            st.rerun()

    if role == "ADMIN":
        st.subheader("Resumo por Usuario")
        df_resumo = list_despesas(conn, "Todos", username, role)
        df_resumo["status_real"] = df_resumo.apply(lambda r: calcular_status_real(r["data_vencimento"], r["status_pagamento"]), axis=1)
        resumo_admin = (
            df_resumo.assign(
                valor_pago=df_resumo.apply(lambda r: r["valor"] if r["status_real"] == "PAGO" else 0.0, axis=1),
                valor_pendente=df_resumo.apply(lambda r: r["valor"] if r["status_real"] == "PENDENTE" else 0.0, axis=1),
                valor_atrasado=df_resumo.apply(lambda r: r["valor"] if r["status_real"] == "ATRASADO" else 0.0, axis=1),
            )
            .groupby("pessoa", as_index=False)[["valor_pago", "valor_pendente", "valor_atrasado", "valor"]]
            .sum()
            .sort_values("pessoa")
            .rename(columns={"pessoa": "Usuario", "valor_pago": "Pago", "valor_pendente": "Pendente", "valor_atrasado": "Atrasado", "valor": "Total"})
        )
        for col in ["Pago", "Pendente", "Atrasado", "Total"]:
            resumo_admin[col] = resumo_admin[col].apply(formatar_moeda_br)
        st.dataframe(resumo_admin, use_container_width=True, hide_index=True)


if __name__ == "__main__":
    main()
