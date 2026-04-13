from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required
from app import db
from app.models import ScorecardItem

scorecard_bp = Blueprint("scorecard", __name__)

MONTHS     = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun",
              "Jul", "Ago", "Set", "Out", "Nov", "Dez"]
MONTH_ABBR = ["jan","fev","mar","abr","mai","jun",
              "jul","ago","set","out","nov","dez"]


def _label_to_mes(label):
    """Converte dd/mm/yyyy ou yyyy-mm → índice 0–11."""
    if not label:
        return -1
    if "/" in label:
        parts = label.split("/")
        if len(parts) == 3:
            return int(parts[1]) - 1
    if "-" in label:
        parts = label.split("-")
        if len(parts) >= 2:
            return int(parts[1]) - 1
    return -1


def _classify(realizado, orcado):
    """
    Classifica o status mensal.
    Usa valor absoluto para funcionar com negativos (custo/receita).
    - green:  realizado ≤ orcado (executou dentro)
    - yellow: até 10% acima
    - red:    mais de 10% acima
    - gray:   sem dados
    """
    if realizado is None or orcado is None:
        return "gray"
    try:
        r = float(realizado)
        o = float(orcado)
    except (TypeError, ValueError):
        return "gray"
    if o == 0:
        return "gray"

    # Trabalha com absolutos para uniformizar custo (negativo) e receita (positivo)
    ar = abs(r)
    ao = abs(o)
    ratio = ar / ao * 100

    if ratio <= 100:
        return "green"
    if ratio <= 110:
        return "yellow"
    return "red"


def _build_scorecard(registros):
    """
    Monta estrutura hierárquica:
    Descrição = PAI (grupo), Atividade = FILHO (indicador)
    { descricao: { atividade: { mes(0-11): {rea, orc} } } }
    """
    tree = {}
    for r in registros:
        pai  = r.descricao or "Sem Grupo"   # Descrição é o PAI
        filho = r.atividade or "Sem Atividade"  # Atividade é o FILHO
        mes  = (r.mes or 1) - 1  # 0-based

        if pai not in tree:
            tree[pai] = {}
        if filho not in tree[pai]:
            tree[pai][filho] = {}
        if mes not in tree[pai][filho]:
            tree[pai][filho][mes] = {"rea": 0.0, "orc": 0.0}

        tree[pai][filho][mes]["rea"] += (r.realizado or 0)
        tree[pai][filho][mes]["orc"] += (r.orcado or 0)

    return tree


def _serialize(tree):
    """Converte a árvore para JSON serializável com status mensais."""
    groups = []
    for atividade, descricoes in sorted(tree.items()):
        indicadores = []
        for descricao, meses in sorted(descricoes.items()):
            # Monta vetor de 12 meses
            monthly = []
            ytd_rea = 0.0
            ytd_orc = 0.0
            for mi in range(12):
                v = meses.get(mi)
                rea = v["rea"] if v else None
                orc = v["orc"] if v else None
                if rea is not None:
                    ytd_rea += rea
                if orc is not None:
                    ytd_orc += orc
                monthly.append({
                    "mes":       MONTHS[mi],
                    "realizado": rea,
                    "orcado":    orc,
                    "status":    _classify(rea, orc) if v else "gray",
                })

            # Delta YTD
            ytd_pct = (abs(ytd_rea) / abs(ytd_orc) * 100) if ytd_orc else None

            indicadores.append({
                "id":        f"{atividade}|{descricao}",
                "nome":      descricao,
                "atividade": atividade,
                "monthly":   monthly,
                "ytd_rea":   ytd_rea,
                "ytd_orc":   ytd_orc,
                "ytd_pct":   ytd_pct,
            })

        # Totais do grupo (atividade)
        group_monthly = []
        for mi in range(12):
            rea = sum((ind["monthly"][mi]["realizado"] or 0) for ind in indicadores)
            orc = sum((ind["monthly"][mi]["orcado"]    or 0) for ind in indicadores)
            group_monthly.append({
                "mes":       MONTHS[mi],
                "realizado": rea,
                "orcado":    orc,
                "status":    _classify(rea, orc),
            })

        groups.append({
            "atividade":   atividade,
            "indicadores": indicadores,
            "monthly":     group_monthly,
            "ytd_rea":     sum(ind["ytd_rea"] for ind in indicadores),
            "ytd_orc":     sum(ind["ytd_orc"] for ind in indicadores),
        })

    return groups


@scorecard_bp.route("/", methods=["GET"])
@jwt_required()
def get_scorecard():
    ativ_f = request.args.get("atividade", "")
    desc_f = request.args.get("descricao", "")
    ano_f  = request.args.get("ano", "")
    mes_f  = request.args.get("mes", "", type=str)

    query = ScorecardItem.query
    if ativ_f:
        query = query.filter_by(descricao=ativ_f)  # descricao é o grupo pai
    if desc_f:
        query = query.filter(ScorecardItem.descricao.ilike(f"%{desc_f}%"))
    if ano_f:
        try:
            query = query.filter_by(ano=int(ano_f))
        except ValueError:
            pass
    if mes_f:
        try:
            query = query.filter_by(mes=int(mes_f))
        except ValueError:
            pass

    registros = query.order_by(ScorecardItem.atividade, ScorecardItem.descricao, ScorecardItem.mes).all()

    tree   = _build_scorecard(registros)
    groups = _serialize(tree)

    # Filtros disponíveis
    atividades = [r[0] for r in db.session.query(ScorecardItem.descricao).distinct().order_by(ScorecardItem.descricao).all()]
    anos       = sorted({r[0] for r in db.session.query(ScorecardItem.ano).distinct().all() if r[0]})

    return jsonify({
        "groups":  groups,
        "months":  MONTHS,
        "filters": {
            "atividades": atividades,
            "anos":       anos,
        },
        "total": len(registros),
    })