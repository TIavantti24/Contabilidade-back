import pymysql
pymysql.install_as_MySQLdb()

from dotenv import load_dotenv
load_dotenv()

import os
from urllib.parse import urlparse

url = os.environ.get("DATABASE_URL", "")
parsed = urlparse(url)
host     = parsed.hostname or "localhost"
port     = parsed.port or 3306
user     = parsed.username or "root"
password = parsed.password or ""
dbname   = parsed.path.lstrip("/").split("?")[0]

try:
    conn = pymysql.connect(host=host, port=port, user=user, password=password, charset="utf8mb4")
    conn.cursor().execute(f"CREATE DATABASE IF NOT EXISTS `{dbname}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
    conn.commit()
    conn.close()
    print(f"✅ Banco '{dbname}' criado/verificado.")
except Exception as e:
    print(f"⚠️  Erro ao criar banco: {e}")
    exit(1)

from app import create_app, db
from app.models import User

app = create_app()

with app.app_context():
    db.create_all()
    if not User.query.filter_by(username="admin").first():
        admin = User(username="admin", email="admin@admin.com", is_admin=True)
        admin.set_password("admin123")
        db.session.add(admin)
        db.session.commit()
        print("✅ Tabelas criadas e usuário admin gerado (senha: admin123)")
    else:
        print("ℹ️  Banco já inicializado.")
