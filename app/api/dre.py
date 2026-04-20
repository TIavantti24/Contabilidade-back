from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required
from app import db
from app.models import Dre

dre_bp = Blueprint("dre", __name__)


@dre_bp.route("/kpi", methods=["GET"])
@jwt_required()
def get_kpi():
    """Retorna sempre KPIs de Lucro Líquido, independente de filtros."""
    ano_f = request.args.get("ano", "")
    query = Dre.query.filter_by(descricao='Lucro Líquido')
    if ano_f:
        try:
            query = query.filter_by(ano=int(ano_f))
        except ValueError:
            pass
    registros = query.all()
    total_rea = sum(r.realizado or 0 for r in registros)
    total_orc = sum(r.orcado    or 0 for r in registros)
    return jsonify({
        "realizado": total_rea,
        "orcado":    total_orc,
        "variacao":  total_rea - total_orc,
        "pct":       (total_rea / total_orc * 100) if total_orc else 0,
    })


@dre_bp.route("/", methods=["GET"])
@jwt_required()
def list_dre():
    ativ_f = request.args.get("atividade", "")
    ano_f  = request.args.get("ano", "")
    desc_f = request.args.get("descricao", "")

    query = Dre.query.order_by(Dre.grau, Dre.descricao, Dre.atividade, Dre.mes)
    if ativ_f:
        query = query.filter_by(atividade=ativ_f)
    if ano_f:
        try:
            query = query.filter_by(ano=int(ano_f))
        except ValueError:
            pass
    if desc_f:
        query = query.filter_by(descricao=desc_f)

    registros = query.all()

    total_realizado = sum(r.realizado or 0 for r in registros)
    total_orcado    = sum(r.orcado    or 0 for r in registros)
    variacao        = total_realizado - total_orcado

    all_labels = sorted({r.data for r in registros})
    chart = {}
    if all_labels:
        chart["Lucro Líquido"] = {
            "labels":    all_labels,
            "realizado": [sum(r.realizado or 0 for r in registros if r.data == lb) for lb in all_labels],
            "orcado":    [sum(r.orcado    or 0 for r in registros if r.data == lb) for lb in all_labels],
            "is_parent": True,
        }
    for r in registros:
        key = r.atividade
        if key not in chart:
            chart[key] = {"labels": [], "realizado": [], "orcado": [], "is_parent": False}
        chart[key]["labels"].append(r.data)
        chart[key]["realizado"].append(r.realizado)
        chart[key]["orcado"].append(r.orcado)

    atividades = [r[0] for r in db.session.query(Dre.atividade).distinct().order_by(Dre.atividade).all()]
    descricoes  = [r[0] for r in db.session.query(Dre.descricao).distinct().order_by(Dre.descricao).all() if r[0]]
    anos        = sorted({r[0] for r in db.session.query(Dre.ano).distinct().all() if r[0]})

    return jsonify({
        "registros": [r.to_dict() for r in registros],
        "chart":     chart,
        "totals": {
            "realizado":       total_realizado,
            "orcado":          total_orcado,
            "variacao":        variacao,
            "total_registros": len(registros),
            "pct_execucao":    (total_realizado / total_orcado * 100) if total_orcado else 0,
        },
        "filters": {
            "atividades": atividades,
            "descricoes":  descricoes,
            "anos":        anos,
        },
    })