import json
import pandas as pd
from app import db
from app.models import Indicador, CustoFixo

MONTHS = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun",
          "Jul", "Ago", "Set", "Out", "Nov", "Dez"]

# Mapa mês abreviado → índice (para parse de datas)
_MES_MAP = {"jan":1,"fev":2,"mar":3,"abr":4,"mai":5,"jun":6,
            "jul":7,"ago":8,"set":9,"out":10,"nov":11,"dez":12}


# ── Scorecard ──────────────────────────────────────────────────────────────────

def _is_melhor_maior(melhor):
    """Retorna True se 'melhor p/ cima' / 'maior'."""
    s = (melhor or "").lower()
    return "cima" in s or "maior" in s or "maximo" in s or "máximo" in s


def _classify(realizado, meta, tolerancia_verde, tolerancia_amar, melhor):
    """Retorna 'green','yellow','red','blue','orange' ou None."""
    if realizado is None or meta is None:
        return None
    try:
        realizado = float(realizado)
        meta = float(meta)
    except (TypeError, ValueError):
        return None
    if meta == 0:
        return None

    ratio = realizado / meta * 100  # em %
    tv = float(tolerancia_verde or 0)
    ta = float(tolerancia_amar or 0)

    if _is_melhor_maior(melhor):
        if ratio >= 121:
            return "orange"   # superado
        if ratio >= 101:
            return "blue"     # acima da meta
        if ratio >= (100 - tv):
            return "green"
        if ratio >= (100 - ta):
            return "yellow"
        return "red"
    else:  # melhor p/ baixo
        if ratio <= 79:
            return "orange"
        if ratio <= 99:
            return "blue"
        if ratio <= (100 + tv):
            return "green"
        if ratio <= (100 + ta):
            return "yellow"
        return "red"


def _calc_ytd(valores, melhor):
    """Calcula YTD acumulado de realizado e meta."""
    reas = [valores.get(f"rea_{m.lower()}") for m in MONTHS]
    mets = [valores.get(f"met_{m.lower()}") for m in MONTHS]
    # Pega até o último mês com dado
    valid_reas = [v for v in reas if v is not None]
    valid_mets = [v for v in mets if v is not None]
    ytd_rea = sum(valid_reas) if valid_reas else None
    ytd_met = sum(valid_mets) if valid_mets else None
    delta = None
    if ytd_rea is not None and ytd_met and ytd_met != 0:
        delta = (ytd_rea / ytd_met - 1) * 100
    return ytd_rea, ytd_met, delta


def build_scorecard_data(indicadores):
    """Agrupa indicadores por área e monta estrutura para o scorecard."""
    grupos = {}
    for ind in indicadores:
        area = ind.area_resultado or "Sem Área"
        if area not in grupos:
            grupos[area] = []

        valores = ind.get_valores()
        row = ind.to_dict()

        monthly = []
        for m in MONTHS:
            key = m.lower()
            rea = valores.get(f"rea_{key}")
            met = valores.get(f"met_{key}")
            monthly.append({
                "mes": m,
                "realizado": rea,
                "meta": met,
                "status": _classify(rea, met, ind.tolerancia_verde, ind.tolerancia_amar, ind.melhor),
            })

        ytd_rea, ytd_met, delta = _calc_ytd(valores, ind.melhor)
        row["monthly"] = monthly
        row["ytd_rea"] = ytd_rea
        row["ytd_met"] = ytd_met
        row["delta"] = delta
        grupos[area].append(row)

    # Retorna como dict {area: [indicadores]} para o frontend usar Object.entries()
    return {area: inds for area, inds in grupos.items()}


# ── Import Indicadores ─────────────────────────────────────────────────────────

_COL_MAP = {
    "plano_gestao":    ["plano gestão", "plano de gestão", "ano", "plano_gestao"],
    "sigla_unidade":   ["sigla unidade", "unidade", "sigla_unidade"],
    "area_resultado":  ["área de resultado", "area de resultado", "area resultado", "area_resultado"],
    "tipo":            ["sigla tipo acompanhamento", "tipo acompanhamento", "tipo"],
    "status":          ["status"],
    "nome":            ["nome do indicador", "nome", "indicador"],
    "unidade_medida":  ["unidade de medida", "unidade_medida", "un. medida"],
    "melhor":          ["melhor", "sentido"],
    "frequencia":      ["frequência", "frequencia"],
    "responsavel":     ["responsável", "responsavel"],
    "forma_acumulo":   ["forma acúmulo", "forma acumulo", "forma_acumulo", "acúmulo"],
    "ponderacao":      ["ponderação", "ponderacao", "peso"],
    "tolerancia_verde":["tolerância verde", "tolerancia verde", "tolerancia_verde", "tol verde"],
    "tolerancia_amar": ["tolerância amarelo", "tolerancia amarelo", "tolerância amarela",
                        "tolerancia_amar", "tol amarela", "tol amarelo"],
}


def _normalize(col):
    import unicodedata
    s = str(col).strip().lower().replace("\n", " ")
    # Remove acentos para comparação mais robusta
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return s


def _map_columns(df):
    norm_to_orig = {_normalize(c): c for c in df.columns}
    mapping = {}
    for field, aliases in _COL_MAP.items():
        for alias in aliases:
            alias_norm = _normalize(alias)
            if alias_norm in norm_to_orig:
                mapping[field] = norm_to_orig[alias_norm]
                break
    return mapping


def import_excel_indicadores(path: str) -> int:
    # Lê a aba 'Indicadores' se existir
    xl = pd.ExcelFile(path)
    sheet = "Indicadores" if "Indicadores" in xl.sheet_names else xl.sheet_names[0]
    df = pd.read_excel(path, sheet_name=sheet, dtype=str)
    df.columns = [str(c) for c in df.columns]
    mapping = _map_columns(df)

    if "nome" not in mapping:
        raise ValueError(f"Coluna 'Nome do Indicador' não encontrada. Colunas disponíveis: {list(df.columns)}")

    # Descobre colunas REA_JAN, MET_JAN etc. (case-insensitive)
    valor_cols = {}
    for col in df.columns:
        nc = _normalize(col)
        for prefix in ("rea_", "met_"):
            if nc.startswith(prefix):
                suffix = nc[len(prefix):][:3]
                for m in MONTHS:
                    if suffix == _normalize(m)[:3]:
                        key = prefix.rstrip("_") + f"_{m.lower()}"
                        valor_cols[key] = col
                        break

    Indicador.query.delete()
    db.session.flush()

    count = 0
    for _, row in df.iterrows():
        nome_col = mapping.get("nome", "")
        nome = str(row.get(nome_col, "") or "").strip()
        if not nome or nome.lower() == "nan":
            continue

        def get(field):
            col = mapping.get(field)
            if not col:
                return None
            val = row.get(col)
            try:
                if pd.isna(val):
                    return None
            except (TypeError, ValueError):
                pass
            s = str(val).strip()
            return s if s and s.lower() != "nan" else None

        def get_float(field):
            v = get(field)
            if v is None:
                return None
            try:
                return float(str(v).replace(",", "."))
            except (ValueError, TypeError):
                return None

        valores = {}
        for key, col in valor_cols.items():
            v = row.get(col)
            try:
                if v is not None and str(v).strip() not in ("", "nan", "None"):
                    valores[key] = float(str(v).replace(",", "."))
            except (ValueError, TypeError):
                pass

        # Normaliza plano_gestao para int
        pg = get("plano_gestao")
        try:
            pg = int(float(pg)) if pg else None
        except (ValueError, TypeError):
            pg = None

        ind = Indicador(
            plano_gestao=pg,
            sigla_unidade=get("sigla_unidade"),
            area_resultado=get("area_resultado"),
            tipo=get("tipo"),
            status=get("status") or "Ativo",
            nome=nome,
            unidade_medida=get("unidade_medida"),
            melhor=get("melhor"),
            frequencia=get("frequencia"),
            responsavel=get("responsavel"),
            forma_acumulo=get("forma_acumulo"),
            ponderacao=get_float("ponderacao"),
            tolerancia_verde=get_float("tolerancia_verde"),
            tolerancia_amar=get_float("tolerancia_amar"),
            valores_json=json.dumps(valores),
        )
        db.session.add(ind)
        count += 1

    db.session.commit()
    return count


# ── Import Custo Fixo ──────────────────────────────────────────────────────────

def import_custo_fixo(path: str) -> int:
    df = pd.read_excel(path)  # sem dtype=str para preservar números
    # Normaliza nomes de colunas
    df.columns = [str(c).strip() for c in df.columns]

    # Mapeia colunas de forma case-insensitive
    col_map = {}
    for c in df.columns:
        nc = _normalize(c)
        col_map[nc] = c

    def find_col(*names):
        for n in names:
            nn = _normalize(n)
            if nn in col_map:
                return col_map[nn]
        return None

    col_ativ  = find_col("atividade")
    col_desc  = find_col("descrição", "descricao", "descricção")
    col_data  = find_col("data")
    col_rea   = find_col("realizado")
    col_orc   = find_col("orçado", "orcado")

    if not col_ativ:
        raise ValueError("Coluna 'Atividade' não encontrada na planilha de Custo Fixo.")

    CustoFixo.query.delete()
    db.session.flush()

    count = 0
    for _, row in df.iterrows():
        atividade = str(row.get(col_ativ, "") or "").strip()
        if not atividade or atividade.lower() == "nan":
            continue

        # Parse da data — suporta dd/mm/yyyy, yyyy-mm-dd, yyyy-mm
        data_raw = row.get(col_data) if col_data else None
        data_str = ""
        ano = None
        mes = None

        if data_raw is not None:
            import datetime
            if isinstance(data_raw, (datetime.datetime, datetime.date)):
                ano = data_raw.year
                mes = data_raw.month
                data_str = f"{ano}-{mes:02d}"
            else:
                data_str = str(data_raw).strip()
                # Tenta dd/mm/yyyy
                if "/" in data_str:
                    parts = data_str.split("/")
                    if len(parts) == 3:
                        try:
                            dia, mes, ano = int(parts[0]), int(parts[1]), int(parts[2])
                            data_str = f"{ano}-{mes:02d}"
                        except ValueError:
                            pass
                # Tenta yyyy-mm-dd ou yyyy-mm
                elif "-" in data_str:
                    parts = data_str.split("-")
                    if len(parts) >= 2:
                        try:
                            ano, mes = int(parts[0]), int(parts[1])
                        except ValueError:
                            pass

        def safe_float(col):
            if not col:
                return None
            v = row.get(col)
            if v is None:
                return None
            try:
                f = float(v)
                return f if not pd.isna(f) else None
            except (ValueError, TypeError):
                return None

        cf = CustoFixo(
            atividade=atividade,
            descricao=str(row.get(col_desc, "") or "").strip() if col_desc else "",
            data=data_str,
            ano=ano,
            mes=mes,
            realizado=safe_float(col_rea),
            orcado=safe_float(col_orc),
        )
        db.session.add(cf)
        count += 1

    db.session.commit()
    return count

def import_receita(path: str) -> int:
    """Importa planilha de receita — mesma estrutura do custo fixo."""
    from app.models import Receita
    import datetime

    df = pd.read_excel(path)
    df.columns = [str(c).strip() for c in df.columns]

    col_map = {_normalize(c): c for c in df.columns}

    def find_col(*names):
        for n in names:
            if _normalize(n) in col_map:
                return col_map[_normalize(n)]
        return None

    col_ativ = find_col("atividade")
    col_desc = find_col("descrição", "descricao")
    col_data = find_col("data")
    col_rea  = find_col("realizado")
    col_orc  = find_col("orçado", "orcado")

    if not col_ativ:
        raise ValueError("Coluna 'Atividade' não encontrada na planilha de Receita.")

    Receita.query.delete()
    db.session.flush()

    count = 0
    for _, row in df.iterrows():
        atividade = str(row.get(col_ativ, "") or "").strip()
        if not atividade or atividade.lower() == "nan":
            continue

        data_raw = row.get(col_data) if col_data else None
        data_str, ano, mes = "", None, None

        if data_raw is not None:
            if isinstance(data_raw, (datetime.datetime, datetime.date)):
                ano, mes = data_raw.year, data_raw.month
                data_str = f"{ano}-{mes:02d}"
            else:
                data_str = str(data_raw).strip()
                if "/" in data_str:
                    parts = data_str.split("/")
                    if len(parts) == 3:
                        try:
                            dia, mes, ano = int(parts[0]), int(parts[1]), int(parts[2])
                            data_str = f"{ano}-{mes:02d}"
                        except ValueError:
                            pass
                elif "-" in data_str:
                    parts = data_str.split("-")
                    if len(parts) >= 2:
                        try:
                            ano, mes = int(parts[0]), int(parts[1])
                        except ValueError:
                            pass

        def safe_float(col):
            if not col:
                return None
            v = row.get(col)
            if v is None:
                return None
            try:
                f = float(v)
                return f if not pd.isna(f) else None
            except (ValueError, TypeError):
                return None

        rec = Receita(
            atividade=atividade,
            descricao=str(row.get(col_desc, "") or "").strip() if col_desc else "",
            data=data_str,
            ano=ano,
            mes=mes,
            realizado=safe_float(col_rea),
            orcado=safe_float(col_orc),
        )
        db.session.add(rec)
        count += 1

    db.session.commit()
    return count


def import_scorecard(path: str) -> int:
    """
    Importa planilha de scorecard.
    Mesma estrutura do custo fixo: Atividade | Descrição | Data | Realizado | Orçado
    """
    from app.models import ScorecardItem
    import datetime as dt

    df = pd.read_excel(path)
    df.columns = [str(c).strip() for c in df.columns]

    col_map = {_normalize(c): c for c in df.columns}

    def find_col(*names):
        for n in names:
            if _normalize(n) in col_map:
                return col_map[_normalize(n)]
        return None

    col_ativ = find_col("atividade")
    col_desc = find_col("descrição", "descricao", "descricção")
    col_data = find_col("data")
    col_rea  = find_col("realizado")
    col_orc  = find_col("orçado", "orcado")
    col_tipo = find_col("tipo")  # coluna opcional — filtra só "Realizado" se existir

    if not col_ativ:
        raise ValueError("Coluna 'Atividade' não encontrada na planilha de Scorecard.")
    if not col_desc:
        raise ValueError("Coluna 'Descrição' não encontrada na planilha de Scorecard.")

    # Se tiver coluna Tipo, mantém só as linhas de Realizado
    if col_tipo:
        df = df[df[col_tipo].astype(str).str.lower().str.strip() == 'realizado'].copy()

    ScorecardItem.query.delete()
    db.session.flush()

    count = 0
    for _, row in df.iterrows():
        atividade = str(row.get(col_ativ, "") or "").strip()
        descricao = str(row.get(col_desc, "") or "").strip()
        if not atividade or atividade.lower() == "nan":
            continue
        if not descricao or descricao.lower() == "nan":
            continue

        data_raw = row.get(col_data) if col_data else None
        data_str, ano, mes = "", None, None

        if data_raw is not None:
            if isinstance(data_raw, (dt.datetime, dt.date)):
                ano, mes = data_raw.year, data_raw.month
                data_str = f"{ano}-{mes:02d}"
            else:
                data_str = str(data_raw).strip()
                if "/" in data_str:
                    parts = data_str.split("/")
                    if len(parts) == 3:
                        try:
                            _, mes, ano = int(parts[0]), int(parts[1]), int(parts[2])
                            data_str = f"{ano}-{mes:02d}"
                        except ValueError:
                            pass
                elif "-" in data_str:
                    parts = data_str.split("-")
                    if len(parts) >= 2:
                        try:
                            ano, mes = int(parts[0]), int(parts[1])
                        except ValueError:
                            pass

        def safe_float(col):
            if not col:
                return None
            v = row.get(col)
            if v is None:
                return None
            try:
                f = float(v)
                return f if not pd.isna(f) else None
            except (ValueError, TypeError):
                return None

        item = ScorecardItem(
            atividade=atividade,
            descricao=descricao,
            data=data_str,
            ano=ano,
            mes=mes,
            realizado=safe_float(col_rea),
            orcado=safe_float(col_orc),
        )
        db.session.add(item)
        count += 1

    db.session.commit()
    return count