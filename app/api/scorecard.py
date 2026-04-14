from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required
from app import db
from app.models import ScorecardItem

scorecard_bp = Blueprint("scorecard", __name__)

MONTHS = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun",
          "Jul", "Ago", "Set", "Out", "Nov", "Dez"]


def _classify(realizado, orcado, seta='maior'):
    """
    Classifica status mensal conforme direção (seta) e regras:
    <= 89%  → red
    90-99%  → yellow
    100%    → green
    101-120%→ blue
    >= 121% → orange
    Para seta='menor', inverte: execução = orcado/realizado * 100
    """
    if realizado is None or orcado is None:
        return None
    try:
        r = float(realizado)
        o = float(orcado)
    except (TypeError, ValueError):
        return None
    if o == 0:
        return None

    if seta == 'menor':
        # Menor realizado = melhor → ratio = orc/rea
        ratio = abs(o) / abs(r) * 100 if r != 0 else None
    else:
        ratio = abs(r) / abs(o) * 100

    if ratio is None:
        return None
    if ratio <= 89:   return 'red'
    if ratio <= 99:   return 'yellow'
    if ratio <= 100:  return 'green'
    if ratio <= 120:  return 'blue'
    return 'orange'


def _build_tree(registros):
    """
    Estrutura: grupo → grau → descricao(pai) → atividade(filho) → mes → {rea,orc}
    Mantém seta e grau por descrição.
    """
    tree   = {}   # { grupo: { descricao: { meta } } }
    meta   = {}   # { descricao: {grau, seta, grupo} }
    filhos = {}   # { descricao: { atividade: { mes: {rea,orc} } } }

    for r in registros:
        grupo     = r.grupo     or 'Sem Grupo'
        desc      = r.descricao or 'Sem Descrição'
        atv       = r.atividade or 'Sem Atividade'
        grau      = r.grau      or 0
        seta      = r.seta      or 'maior'
        mes       = (r.mes or 1) - 1

        if desc not in meta:
            meta[desc] = {'grupo': grupo, 'grau': grau, 'seta': seta}
        if desc not in filhos:
            filhos[desc] = {}
        if atv not in filhos[desc]:
            filhos[desc][atv] = {}
        if mes not in filhos[desc][atv]:
            filhos[desc][atv][mes] = {'rea': 0.0, 'orc': 0.0}

        filhos[desc][atv][mes]['rea'] += (r.realizado or 0)
        filhos[desc][atv][mes]['orc'] += (r.orcado    or 0)

    return meta, filhos


def _serialize(meta, filhos):
    # Agrupa por Grupo, ordena por Grau dentro de cada grupo
    grupos = {}
    for desc, m in meta.items():
        g = m['grupo']
        if g not in grupos:
            grupos[g] = []
        grupos[g].append(desc)

    result = []
    for grupo_nome, descs in sorted(grupos.items()):
        # Ordena descrições por grau
        descs_sorted = sorted(descs, key=lambda d: meta[d]['grau'])
        grupo_indicadores = []

        for desc in descs_sorted:
            seta = meta[desc]['seta']
            atv_filhos = filhos.get(desc, {})
            indicadores_filho = []

            for atv, meses_data in sorted(atv_filhos.items()):
                monthly = []
                ytd_rea = ytd_orc = 0.0
                for mi in range(12):
                    v = meses_data.get(mi)
                    rea = v['rea'] if v else None
                    orc = v['orc'] if v else None
                    if rea is not None: ytd_rea += rea
                    if orc is not None: ytd_orc += orc
                    monthly.append({
                        'mes':       MONTHS[mi],
                        'realizado': rea,
                        'orcado':    orc,
                        'status':    _classify(rea, orc, seta) if v else None,
                    })

                ytd_pct = (abs(ytd_rea) / abs(ytd_orc) * 100) if ytd_orc else None
                indicadores_filho.append({
                    'id':      f'{desc}|{atv}',
                    'nome':    atv,
                    'monthly': monthly,
                    'ytd_rea': ytd_rea,
                    'ytd_orc': ytd_orc,
                    'ytd_pct': ytd_pct,
                    'seta':    seta,
                })

            # Totais do pai (desc) por mês
            pai_monthly = []
            for mi in range(12):
                rea = sum(f['monthly'][mi]['realizado'] or 0 for f in indicadores_filho)
                orc = sum(f['monthly'][mi]['orcado']    or 0 for f in indicadores_filho)
                pai_monthly.append({
                    'mes': MONTHS[mi], 'realizado': rea, 'orcado': orc,
                    'status': _classify(rea, orc, seta),
                })

            pai_rea = sum(f['ytd_rea'] for f in indicadores_filho)
            pai_orc = sum(f['ytd_orc'] for f in indicadores_filho)

            grupo_indicadores.append({
                'atividade':   desc,           # desc é o PAI
                'grau':        meta[desc]['grau'],
                'seta':        seta,
                'indicadores': indicadores_filho,
                'monthly':     pai_monthly,
                'ytd_rea':     pai_rea,
                'ytd_orc':     pai_orc,
            })

        result.append({
            'grupo':       grupo_nome,
            'indicadores': grupo_indicadores,  # lista de pais dentro do grupo
        })

    return result


@scorecard_bp.route("/", methods=["GET"])
@jwt_required()
def get_scorecard():
    grupo_f = request.args.get("grupo", "")
    desc_f  = request.args.get("descricao", "")
    ano_f   = request.args.get("ano", "")
    q       = request.args.get("q", "").strip().lower()

    query = ScorecardItem.query
    if grupo_f: query = query.filter_by(grupo=grupo_f)
    if desc_f:  query = query.filter(ScorecardItem.descricao.ilike(f"%{desc_f}%"))
    if ano_f:
        try: query = query.filter_by(ano=int(ano_f))
        except ValueError: pass

    registros = query.order_by(
        ScorecardItem.grupo, ScorecardItem.grau,
        ScorecardItem.descricao, ScorecardItem.atividade, ScorecardItem.mes
    ).all()

    meta, filhos = _build_tree(registros)

    # Filtro por busca (filtra nos filhos)
    if q:
        filhos = {
            desc: {atv: m for atv, m in atvs.items() if q in atv.lower()}
            for desc, atvs in filhos.items()
        }
        filhos = {d: a for d, a in filhos.items() if a}
        meta   = {d: m for d, m in meta.items() if d in filhos}

    groups = _serialize(meta, filhos)

    grupos_list = [r[0] for r in db.session.query(ScorecardItem.grupo).distinct().order_by(ScorecardItem.grupo).all()]
    anos_list   = sorted({r[0] for r in db.session.query(ScorecardItem.ano).distinct().all() if r[0]})

    return jsonify({
        "groups":  groups,
        "months":  MONTHS,
        "filters": {"grupos": grupos_list, "anos": anos_list},
        "total":   len(registros),
    })