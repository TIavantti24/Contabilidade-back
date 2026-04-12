import json
from app import db
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime


class User(db.Model):
    __tablename__ = "users"

    id            = db.Column(db.Integer, primary_key=True)
    username      = db.Column(db.String(80), unique=True, nullable=False)
    email         = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    is_admin      = db.Column(db.Boolean, default=False)
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)
    is_active     = db.Column(db.Boolean, default=True)

    def set_password(self, raw):
        self.password_hash = generate_password_hash(raw)

    def check_password(self, raw):
        return check_password_hash(self.password_hash, raw)

    def to_dict(self):
        return {
            "id":         self.id,
            "username":   self.username,
            "email":      self.email,
            "is_admin":   self.is_admin,
            "is_active":  self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Indicador(db.Model):
    __tablename__ = "indicadores"

    id               = db.Column(db.Integer, primary_key=True)
    plano_gestao     = db.Column(db.Integer)
    sigla_unidade    = db.Column(db.String(100))
    area_resultado   = db.Column(db.String(100))
    tipo             = db.Column(db.String(20))
    status           = db.Column(db.String(20))
    nome             = db.Column(db.String(300))
    unidade_medida   = db.Column(db.String(50))
    melhor           = db.Column(db.String(50))
    frequencia       = db.Column(db.String(50))
    responsavel      = db.Column(db.String(200))
    forma_acumulo    = db.Column(db.String(50))
    ponderacao       = db.Column(db.Float, nullable=True)
    tolerancia_verde = db.Column(db.Float, nullable=True)
    tolerancia_amar  = db.Column(db.Float, nullable=True)
    valores_json     = db.Column(db.Text, default="{}")
    pai_id           = db.Column(db.Integer, db.ForeignKey("indicadores.id"), nullable=True)
    nivel            = db.Column(db.Integer, default=0)

    filhos = db.relationship(
        "Indicador",
        backref=db.backref("pai", remote_side="Indicador.id"),
        lazy="dynamic",
    )

    def get_valores(self):
        return json.loads(self.valores_json or "{}")

    def to_dict(self, include_valores=False):
        d = {
            "id":               self.id,
            "plano_gestao":     self.plano_gestao,
            "sigla_unidade":    self.sigla_unidade,
            "area_resultado":   self.area_resultado,
            "tipo":             self.tipo,
            "status":           self.status,
            "nome":             self.nome,
            "unidade_medida":   self.unidade_medida,
            "melhor":           self.melhor,
            "frequencia":       self.frequencia,
            "responsavel":      self.responsavel,
            "forma_acumulo":    self.forma_acumulo,
            "ponderacao":       self.ponderacao,
            "tolerancia_verde": self.tolerancia_verde,
            "tolerancia_amar":  self.tolerancia_amar,
            "pai_id":           self.pai_id,
            "nivel":            self.nivel,
        }
        if include_valores:
            d["valores"] = self.get_valores()
        return d


class CustoFixo(db.Model):
    __tablename__ = "custo_fixo"

    id        = db.Column(db.Integer, primary_key=True)
    atividade = db.Column(db.String(100))
    descricao = db.Column(db.String(200))
    data      = db.Column(db.String(10))
    ano       = db.Column(db.Integer)
    mes       = db.Column(db.Integer)
    realizado = db.Column(db.Float, nullable=True)
    orcado    = db.Column(db.Float, nullable=True)

    def to_dict(self):
        return {
            "id":        self.id,
            "atividade": self.atividade,
            "descricao": self.descricao,
            "data":      self.data,
            "ano":       self.ano,
            "mes":       self.mes,
            "realizado": self.realizado,
            "orcado":    self.orcado,
        }


class Receita(db.Model):
    __tablename__ = "receita"

    id        = db.Column(db.Integer, primary_key=True)
    atividade = db.Column(db.String(100))
    descricao = db.Column(db.String(200))
    data      = db.Column(db.String(10))
    ano       = db.Column(db.Integer)
    mes       = db.Column(db.Integer)
    realizado = db.Column(db.Float, nullable=True)
    orcado    = db.Column(db.Float, nullable=True)

    def to_dict(self):
        return {
            "id":        self.id,
            "atividade": self.atividade,
            "descricao": self.descricao,
            "data":      self.data,
            "ano":       self.ano,
            "mes":       self.mes,
            "realizado": self.realizado,
            "orcado":    self.orcado,
        }


class ImportLog(db.Model):
    __tablename__ = "import_logs"

    id          = db.Column(db.Integer, primary_key=True)
    tipo        = db.Column(db.String(20), default="indicadores")
    filename    = db.Column(db.String(200))
    imported_at = db.Column(db.DateTime, default=datetime.utcnow)
    total       = db.Column(db.Integer, default=0)
    imported_by = db.Column(db.String(80))

    def to_dict(self):
        return {
            "id":          self.id,
            "tipo":        self.tipo,
            "filename":    self.filename,
            "imported_at": self.imported_at.isoformat() if self.imported_at else None,
            "total":       self.total,
            "imported_by": self.imported_by,
        }
