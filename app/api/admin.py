import os
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from werkzeug.utils import secure_filename
from app import db
from app.models import User, Indicador, ImportLog
from app.services import import_excel_indicadores, import_custo_fixo, import_receita, import_scorecard, import_dre

admin_bp = Blueprint("admin", __name__)

UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "uploads")
ALLOWED_EXT   = {"xlsx", "xls"}


def require_admin():
    user_id = int(get_jwt_identity())
    user    = User.query.get(user_id)
    if not user or not user.is_admin:
        return None, (jsonify({"error": "Acesso negado."}), 403)
    return user, None


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXT


# ── Users ─────────────────────────────────────────────────────────────────────

@admin_bp.route("/users", methods=["GET"])
@jwt_required()
def list_users():
    user, err = require_admin()
    if err: return err
    return jsonify([u.to_dict() for u in User.query.all()])


@admin_bp.route("/users", methods=["POST"])
@jwt_required()
def create_user():
    user, err = require_admin()
    if err: return err
    data     = request.get_json()
    username = (data.get("username") or "").strip()
    email    = (data.get("email")    or "").strip()
    password = data.get("password")  or ""
    is_admin = bool(data.get("is_admin", False))

    if not username or not email or not password:
        return jsonify({"error": "Campos obrigatórios: username, email, password"}), 400
    if User.query.filter((User.username == username) | (User.email == email)).first():
        return jsonify({"error": "Usuário ou e-mail já existe."}), 409

    new_user = User(username=username, email=email, is_admin=is_admin)
    new_user.set_password(password)
    db.session.add(new_user)
    db.session.commit()
    return jsonify(new_user.to_dict()), 201


@admin_bp.route("/users/<int:uid>", methods=["DELETE"])
@jwt_required()
def delete_user(uid):
    current_user, err = require_admin()
    if err: return err
    if uid == current_user.id:
        return jsonify({"error": "Não pode deletar a si mesmo."}), 400
    u = User.query.get_or_404(uid)
    db.session.delete(u)
    db.session.commit()
    return jsonify({"message": "Usuário removido."})


@admin_bp.route("/users/<int:uid>", methods=["PATCH"])
@jwt_required()
def update_user(uid):
    current_user, err = require_admin()
    if err: return err
    u    = User.query.get_or_404(uid)
    data = request.get_json()
    if "is_admin"  in data: u.is_admin  = bool(data["is_admin"])
    if "is_active" in data: u.is_active = bool(data["is_active"])
    if "password"  in data and data["password"]: u.set_password(data["password"])
    db.session.commit()
    return jsonify(u.to_dict())


# ── Import ─────────────────────────────────────────────────────────────────────

def _do_import(field_name, import_fn, tipo_log):
    user, err = require_admin()
    if err: return err
    file = request.files.get(field_name)
    if not file or file.filename == "":
        return jsonify({"error": "Nenhum arquivo selecionado."}), 400
    if not allowed_file(file.filename):
        return jsonify({"error": "Formato inválido. Envie .xlsx ou .xls."}), 400
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    filename  = secure_filename(file.filename)
    save_path = os.path.join(UPLOAD_FOLDER, filename)
    file.save(save_path)
    try:
        total = import_fn(save_path)
        log   = ImportLog(tipo=tipo_log, filename=filename, total=total, imported_by=user.username)
        db.session.add(log)
        db.session.commit()
        return jsonify({"message": f"{total} registros importados.", "total": total})
    except ValueError as e:
        return jsonify({"error": f"Erro na planilha: {e}"}), 422
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Erro inesperado: {e}"}), 500


@admin_bp.route("/import/indicadores", methods=["POST"])
@jwt_required()
def import_indicadores():
    return _do_import("planilha", import_excel_indicadores, "indicadores")


@admin_bp.route("/import/custo-fixo", methods=["POST"])
@jwt_required()
def import_custo():
    return _do_import("planilha_custo", import_custo_fixo, "custo")


@admin_bp.route("/import/receita", methods=["POST"])
@jwt_required()
def import_receita_view():
    return _do_import("planilha_receita", import_receita, "receita")


@admin_bp.route("/import/scorecard", methods=["POST"])
@jwt_required()
def import_scorecard_view():
    return _do_import("planilha_scorecard", import_scorecard, "scorecard")


@admin_bp.route("/import/dre", methods=["POST"])
@jwt_required()
def import_dre_view():
    return _do_import("planilha_dre", import_dre, "dre")


@admin_bp.route("/import/logs", methods=["GET"])
@jwt_required()
def import_logs():
    user, err = require_admin()
    if err: return err
    logs = ImportLog.query.order_by(ImportLog.imported_at.desc()).limit(30).all()
    return jsonify({
        "logs":      [l.to_dict() for l in logs],
        "total_ind": Indicador.query.count(),
    })


# ── Hierarquia (legado) ────────────────────────────────────────────────────────

@admin_bp.route("/hierarquia", methods=["GET"])
@jwt_required()
def hierarquia():
    user, err = require_admin()
    if err: return err
    inds = Indicador.query.order_by(Indicador.area_resultado, Indicador.nome).all()
    return jsonify([i.to_dict() for i in inds])


@admin_bp.route("/hierarquia/set-pai", methods=["POST"])
@jwt_required()
def set_pai():
    user, err = require_admin()
    if err: return err
    data     = request.get_json()
    filho_id = data.get("filho_id")
    pai_id   = data.get("pai_id")
    filho    = Indicador.query.get_or_404(filho_id)
    if pai_id:
        candidato = Indicador.query.get(pai_id)
        if candidato:
            cur = candidato
            while cur and cur.pai_id:
                if cur.pai_id == filho_id:
                    return jsonify({"error": "Referência circular."}), 400
                cur = Indicador.query.get(cur.pai_id)
            filho.pai_id = pai_id
            filho.nivel  = (candidato.nivel or 0) + 1
        else:
            filho.pai_id = None
            filho.nivel  = 0
    else:
        filho.pai_id = None
        filho.nivel  = 0
    db.session.commit()
    return jsonify(filho.to_dict())


@admin_bp.route("/hierarquia/<int:ind_id>/remover-pai", methods=["POST"])
@jwt_required()
def remover_pai(ind_id):
    user, err = require_admin()
    if err: return err
    ind = Indicador.query.get_or_404(ind_id)
    ind.pai_id = None
    ind.nivel  = 0
    db.session.commit()
    return jsonify(ind.to_dict())


@admin_bp.route("/hierarquia/auto-detectar", methods=["POST"])
@jwt_required()
def auto_detectar():
    user, err = require_admin()
    if err: return err
    NIVEL_TIPO  = {'IC': 0, 'IE': 1, 'IO': 2, 'IT': 3, 'IV': 4}
    inds        = Indicador.query.all()
    for ind in inds:
        ind.pai_id = None
        ind.nivel  = 0
    db.session.flush()
    inds_sorted = sorted(inds, key=lambda x: NIVEL_TIPO.get(x.tipo or '', 99))
    vinculados  = 0
    for ind in inds_sorted:
        nivel_ind  = NIVEL_TIPO.get(ind.tipo or '', 99)
        melhor_pai = None
        melhor_len = 0
        for candidato in inds_sorted:
            nivel_cand = NIVEL_TIPO.get(candidato.tipo or '', 99)
            if nivel_cand >= nivel_ind: continue
            if candidato.area_resultado != ind.area_resultado: continue
            nc = (candidato.nome or '').strip()
            ni = (ind.nome or '').strip()
            if ni.startswith(nc) and len(nc) > melhor_len:
                melhor_pai = candidato
                melhor_len = len(nc)
        if melhor_pai:
            ind.pai_id = melhor_pai.id
            ind.nivel  = (melhor_pai.nivel or 0) + 1
            vinculados += 1
    db.session.commit()
    return jsonify({"message": f"{vinculados} indicadores vinculados."})