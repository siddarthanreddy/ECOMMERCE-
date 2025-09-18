from app import create_app
from models import db, Product

app = create_app()

with app.app_context():
    products = Product.query.all()
    for p in products:
        if p.image_url and p.image_url.startswith("/static/uploads/"):
            fixed = p.image_url.replace("/static/uploads/", "")
            print(f"Fixing {p.name}: {p.image_url} -> {fixed}")
            p.image_url = fixed
    db.session.commit()

print("✅ Fixed all image paths")
