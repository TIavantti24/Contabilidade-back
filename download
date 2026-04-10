from flask import Blueprint, jsonify
from flask_jwt_extended import jwt_required
from app import db
from app.models import Indicador, ImportLog

dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.route("/stats", methods=["GET"])
@jwt_required()
def stats():
    total = Indicador.query.count()
    ativos = Indicador.query.filter_by(status="Ativo").count()
    inativos = total - ativos

    unidades = db.session.query(Indicador.sigla_unidade, db.func.count(Indicador.id)) \
        .group_by(Indicador.sigla_unidade).all()

    areas = db.session.query(Indicador.area_resultado, db.func.count(Indicador.id)) \
        .group_by(Indicador.area_resultado).all()

    anos = db.session.query(Indicador.plano_gestao, db.func.count(Indicador.id)) \
        .group_by(Indicador.plano_gestao).all()

    last_import = ImportLog.query.order_by(ImportLog.imported_at.desc()).first()

    return jsonify({
        "total": total,
        "ativos": ativos,
        "inativos": inativos,
        "unidades": [{"nome": u, "total": c} for u, c in unidades],
        "areas": [{"nome": a, "total": c} for a, c in areas],
        "anos": [{"ano": a, "total": c} for a, c in anos],
        "last_import": last_import.to_dict() if last_import else None,
    })