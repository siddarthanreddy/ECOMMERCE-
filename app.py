import os
from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename
from forms import ProductForm, AdminLoginForm
from models import db, Product, Order, OrderItem
from dotenv import load_dotenv

load_dotenv()

UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), "static", "uploads")
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif"}

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

def create_app():
    app = Flask(__name__)
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "devsecret")
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///ecommerce.db"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)

    db.init_app(app)

    @app.context_processor
    def cart_count():
        cart = session.get("cart", {})
        total_qty = sum(item["qty"] for item in cart.values())
        return dict(cart_count=total_qty)

    @app.route("/")
    def index():
        products = Product.query.order_by(Product.id.desc()).all()
        return render_template("index.html", products=products)

    @app.route("/product/<int:product_id>")
    def product_detail(product_id):
        product = Product.query.get_or_404(product_id)
        return render_template("product.html", product=product)

    @app.route("/cart/add/<int:product_id>", methods=["POST"])
    def add_to_cart(product_id):
        qty = int(request.form.get("quantity", 1))
        product = Product.query.get_or_404(product_id)
        cart = session.get("cart", {})
        item = cart.get(str(product_id), {
            "id": product_id,
            "name": product.name,
            "price": float(product.price),
            "qty": 0,
            "image_url": product.image_url,
        })
        item["qty"] += qty
        cart[str(product_id)] = item
        session["cart"] = cart
        flash("Added to cart")
        return redirect(url_for("cart"))

    @app.route("/cart")
    def cart():
        cart = session.get("cart", {})
        subtotal = sum(item["price"] * item["qty"] for item in cart.values())
        return render_template("cart.html", cart=cart, subtotal=subtotal)

    @app.route("/cart/update", methods=["POST"])
    def cart_update():
        cart = session.get("cart", {})
        for key, val in request.form.items():
            if key.startswith("qty_"):
                pid = key.split("_", 1)[1]
                try:
                    q = int(val)
                except ValueError:
                    q = 0
                if q <= 0:
                    cart.pop(pid, None)
                else:
                    if pid in cart:
                        cart[pid]["qty"] = q
        session["cart"] = cart
        return redirect(url_for("cart"))

    @app.route("/checkout", methods=["GET", "POST"])
    def checkout():
        cart = session.get("cart", {})
        if request.method == "POST":
            name = request.form.get("name")
            email = request.form.get("email")
            address = request.form.get("address")
            if not cart:
                flash("Cart empty")
                return redirect(url_for("index"))
            order = Order(customer_name=name, customer_email=email, address=address)
            db.session.add(order)
            db.session.flush()
            total = 0
            for item in cart.values():
                oi = OrderItem(
                    order_id=order.id,
                    product_name=item["name"],
                    price=item["price"],
                    quantity=item["qty"],
                )
                total += item["price"] * item["qty"]
                db.session.add(oi)
            order.total = total
            db.session.commit()
            session["cart"] = {}
            flash("Order placed — this is a demo, no real payment processed")
            return redirect(url_for("index"))
        subtotal = sum(item["price"] * item["qty"] for item in cart.values())
        return render_template("checkout.html", cart=cart, subtotal=subtotal)

    # Admin auth helper
    def admin_auth_required(fn):
        from functools import wraps
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if not session.get("is_admin"):
                return redirect(url_for("admin_login"))
            return fn(*args, **kwargs)
        return wrapper

    @app.route("/admin/login", methods=["GET", "POST"])
    def admin_login():
        form = AdminLoginForm()
        if form.validate_on_submit():
            pw = os.environ.get("ADMIN_PASSWORD", "admin")
            if form.password.data == pw:
                session["is_admin"] = True
                return redirect(url_for("admin_dashboard"))
            else:
                flash("Incorrect password")
        return render_template("admin/login.html", form=form)

    @app.route("/admin/logout")
    def admin_logout():
        session.pop("is_admin", None)
        return redirect(url_for("index"))

    @app.route("/admin")
    @admin_auth_required
    def admin_dashboard():
        products = Product.query.order_by(Product.id.desc()).all()
        return render_template("admin/dashboard.html", products=products)

    @app.route("/admin/product/new", methods=["GET", "POST"])
    @admin_auth_required
    def admin_product_new():
        form = ProductForm()
        if form.validate_on_submit():
            image_file = request.files.get("image_file")
            filename = None
            if image_file and allowed_file(image_file.filename):
                filename = secure_filename(image_file.filename)
                path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
                image_file.save(path)
            p = Product(
                name=form.name.data,
                description=form.description.data,
                price=form.price.data,
                image_url=filename if filename else "",
            )
            db.session.add(p)
            db.session.commit()
            return redirect(url_for("admin_dashboard"))
        return render_template("admin/product_form.html", form=form)

    @app.route("/admin/product/edit/<int:product_id>", methods=["GET", "POST"])
    @admin_auth_required
    def admin_product_edit(product_id):
        p = Product.query.get_or_404(product_id)
        form = ProductForm(obj=p)
        if form.validate_on_submit():
            form.populate_obj(p)
            image_file = request.files.get("image_file")
            if image_file and allowed_file(image_file.filename):
                filename = secure_filename(image_file.filename)
                path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
                image_file.save(path)
                p.image_url = filename
            db.session.commit()
            return redirect(url_for("admin_dashboard"))
        return render_template("admin/product_form.html", form=form, product=p)

    @app.route("/admin/product/delete/<int:product_id>", methods=["POST"])
    @admin_auth_required
    def admin_product_delete(product_id):
        p = Product.query.get_or_404(product_id)
        db.session.delete(p)
        db.session.commit()
        return redirect(url_for("admin_dashboard"))

    return app

if __name__ == "__main__":
    app = create_app()
    app.run(debug=True)
