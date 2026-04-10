from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required
from app import db
from app.models import Indicador
from app.services import build_scorecard_data, MONTHS

indicadores_bp = Blueprint("indicadores", __name__)


@indicadores_bp.route("/", methods=["GET"])
@jwt_required()
def list_indicadores():
    q = request.args.get("q", "").strip()
    unidade = request.args.get("unidade", "")
    area = request.args.get("area", "")
    status_f = request.args.get("status", "")
    ano_f = request.args.get("ano", "")
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)

    query = Indicador.query
    if q:
        query = query.filter(Indicador.nome.ilike(f"%{q}%"))
    if unidade:
        query = query.filter_by(sigla_unidade=unidade)
    if area:
        query = query.filter_by(area_resultado=area)
    if status_f:
        query = query.filter_by(status=status_f)
    if ano_f:
        try:
            query = query.filter_by(plano_gestao=int(ano_f))
        except ValueError:
            pass

    pag = query.order_by(Indicador.area_resultado, Indicador.nome).paginate(
        page=page, per_page=per_page, error_out=False
    )

    return jsonify({
        "items": [i.to_dict() for i in pag.items],
        "total": pag.total,
        "pages": pag.pages,
        "page": pag.page,
        "per_page": pag.per_page,
    })


@indicadores_bp.route("/scorecard", methods=["GET"])
@jwt_required()
def scorecard():
    q = request.args.get("q", "").strip()
    unidade = request.args.get("unidade", "")
    area = request.args.get("area", "")
    status_f = request.args.get("status", "")
    ano_f = request.args.get("ano", "")

    query = Indicador.query
    if q:
        query = query.filter(Indicador.nome.ilike(f"%{q}%"))
    if unidade:
        query = query.filter_by(sigla_unidade=unidade)
    if area:
        query = query.filter_by(area_resultado=area)
    if status_f:
        query = query.filter_by(status=status_f)
    if ano_f:
        try:
            query = query.filter_by(plano_gestao=int(ano_f))
        except ValueError:
            pass

    all_inds = query.order_by(Indicador.area_resultado, Indicador.nome).all()
    groups = build_scorecard_data(all_inds)

    all_unidades = [r[0] for r in db.session.query(Indicador.sigla_unidade).distinct().all()]
    all_areas = [r[0] for r in db.session.query(Indicador.area_resultado).distinct().all()]
    all_anos = sorted({r[0] for r in db.session.query(Indicador.plano_gestao).distinct().all()})

    return jsonify({
        "groups": groups,
        "months": MONTHS,
        "filters": {
            "unidades": all_unidades,
            "areas": all_areas,
            "anos": all_anos,
        },
    })


@indicadores_bp.route("/<int:ind_id>", methods=["GET"])
@jwt_required()
def detalhe(ind_id):
    ind = Indicador.query.get_or_404(ind_id)
    valores = ind.get_valores()

    chart_data = {
        "labels": MONTHS,
        "realizado": [valores.get(f"rea_{m.lower()}") for m in MONTHS],
        "meta": [valores.get(f"met_{m.lower()}") for m in MONTHS],
    }

    filhos = [f.to_dict() for f in ind.filhos.all()]

    return jsonify({
        **ind.to_dict(include_valores=True),
        "chart_data": chart_data,
        "filhos": filhos,
        "pai": ind.pai.to_dict() if ind.pai else None,
    })