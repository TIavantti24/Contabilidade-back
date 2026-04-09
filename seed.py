"""
Cria o banco de dados e um usuário admin inicial.
Execute uma vez após configurar o .env:

    python seed.py
"""
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
        print("✅ Banco criado e usuário admin gerado (senha: admin123)")
    else:
        print("ℹ️  Banco já inicializado.")