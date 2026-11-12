"""Quản lý sách: CRUD danh mục, CRUD sách theo danh mục, dashboard (Flask + SQLite)."""
from flask import Flask, flash, redirect, render_template, request, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import CSRFProtect
from sqlalchemy import ForeignKey, String, func, or_
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


db = SQLAlchemy(model_class=Base)
csrf = CSRFProtect()

app = Flask(__name__)
app.config["SECRET_KEY"] = "dev-doi-truoc-khi-trien-khai"
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///quanlysach.db"  # instance/quanlysach.db
db.init_app(app)
csrf.init_app(app)  # chống giả mạo form: mọi form POST đều kèm csrf_token


# ---------------------------------------------------------------- Model
class Category(db.Model):
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    description: Mapped[str | None] = mapped_column(String(255))
    # Xoá danh mục thì xoá luôn các sách thuộc danh mục đó
    books: Mapped[list["Book"]] = relationship(
        back_populates="category",
        cascade="all, delete-orphan",
        order_by="Book.title",
    )


class Book(db.Model):
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    author: Mapped[str] = mapped_column(String(100))
    year: Mapped[int | None] = mapped_column()
    price: Mapped[int] = mapped_column(default=0)
    quantity: Mapped[int] = mapped_column(default=0)
    category_id: Mapped[int] = mapped_column(ForeignKey("category.id"), index=True)
    category: Mapped["Category"] = relationship(back_populates="books")


with app.app_context():
    db.create_all()


# ---------------------------------------------------------------- Tiện ích
@app.template_filter("vnd")
def vnd(value):
    """20000 -> '20.000 đ'"""
    return f"{value:,.0f}".replace(",", ".") + " đ"


def to_int(text, maximum=10**9):
    """'45.000' -> 45000. Trả về None nếu không phải số nguyên không âm hợp lệ."""
    cleaned = text.replace(".", "").replace(",", "").replace(" ", "")
    if not (cleaned.isascii() and cleaned.isdigit()):
        return None
    value = int(cleaned)
    return value if value <= maximum else None


def read_form(*fields):
    return {name: request.form.get(name, "").strip() for name in fields}


def category_counts():
    """[(Category, số sách), ...] sắp theo tên danh mục."""
    stmt = (
        db.select(Category, func.count(Book.id))
        .join(Category.books, isouter=True)
        .group_by(Category.id)
        .order_by(Category.name)
    )
    return db.session.execute(stmt).all()


def validate_category(form, current_id=None):
    errors = {}
    name = form["name"]
    if not name:
        errors["name"] = "Vui lòng nhập tên danh mục."
    elif len(name) > 100:
        errors["name"] = "Tên danh mục tối đa 100 ký tự."
    else:
        stmt = db.select(Category).where(
            or_(Category.name == name, func.lower(Category.name) == name.lower())
        )
        existing = db.session.scalar(stmt)
        if existing is not None and existing.id != current_id:
            errors["name"] = "Tên danh mục này đã tồn tại."
    if len(form["description"]) > 255:
        errors["description"] = "Mô tả tối đa 255 ký tự."
    return errors


def validate_book(form):
    errors = {}
    if not form["title"]:
        errors["title"] = "Vui lòng nhập tên sách."
    elif len(form["title"]) > 200:
        errors["title"] = "Tên sách tối đa 200 ký tự."
    if not form["author"]:
        errors["author"] = "Vui lòng nhập tác giả."
    elif len(form["author"]) > 100:
        errors["author"] = "Tên tác giả tối đa 100 ký tự."
    if form["year"]:
        year = to_int(form["year"])
        if year is None or not 1000 <= year <= 2100:
            errors["year"] = "Năm xuất bản không hợp lệ (từ 1000 đến 2100)."
    if to_int(form["price"]) is None:
        errors["price"] = "Giá phải là số nguyên không âm."
    if to_int(form["quantity"], maximum=10**6) is None:
        errors["quantity"] = "Số lượng phải là số nguyên không âm."
    category_id = to_int(form["category_id"])
    if category_id is None or db.session.get(Category, category_id) is None:
        errors["category_id"] = "Vui lòng chọn danh mục."
    return errors


def apply_book_form(book, form):
    book.title = form["title"]
    book.author = form["author"]
    book.year = to_int(form["year"]) if form["year"] else None
    book.price = to_int(form["price"])
    book.quantity = to_int(form["quantity"], maximum=10**6)
    book.category_id = to_int(form["category_id"])


BOOK_FIELDS = ("title", "author", "year", "price", "quantity", "category_id")


def seed_data():
    sample = {
        "Văn học": ("Tiểu thuyết, truyện ngắn và thơ.", [
            ("Dế Mèn phiêu lưu ký", "Tô Hoài", 1941, 52000, 15),
            ("Tắt đèn", "Ngô Tất Tố", 1939, 38000, 8),
            ("Số đỏ", "Vũ Trọng Phụng", 1936, 45000, 0),
        ]),
        "Khoa học": ("Sách khoa học phổ thông.", [
            ("Lược sử thời gian", "Stephen Hawking", 1988, 98000, 6),
            ("Sapiens: Lược sử loài người", "Yuval Noah Harari", 2011, 189000, 12),
        ]),
        "Lập trình": ("Sách học lập trình và phần mềm.", [
            ("Clean Code", "Robert C. Martin", 2008, 250000, 5),
            ("Python Crash Course", "Eric Matthes", 2015, 320000, 7),
            ("Flask Web Development", "Miguel Grinberg", 2014, 280000, 3),
        ]),
        "Thiếu nhi": ("Truyện và sách cho thiếu nhi.", [
            ("Hoàng tử bé", "Antoine de Saint-Exupéry", 1943, 60000, 20),
            ("Totto-chan bên cửa sổ", "Tetsuko Kuroyanagi", 1981, 79000, 9),
        ]),
    }
    for name, (description, books) in sample.items():
        category = Category(name=name, description=description)
        for title, author, year, price, quantity in books:
            category.books.append(
                Book(title=title, author=author, year=year, price=price, quantity=quantity)
            )
        db.session.add(category)
    db.session.commit()


# ---------------------------------------------------------------- Dashboard
@app.get("/")
def dashboard():
    n_categories = db.session.scalar(db.select(func.count(Category.id)))
    n_books = db.session.scalar(db.select(func.count(Book.id)))
    total_quantity = db.session.scalar(
        db.select(func.coalesce(func.sum(Book.quantity), 0)))
    stock_value = db.session.scalar(
        db.select(func.coalesce(func.sum(Book.price * Book.quantity), 0)))
    rows = category_counts()
    max_count = max((count for _, count in rows), default=0)
    recent = db.session.scalars(
        db.select(Book).order_by(Book.id.desc()).limit(5)).all()
    return render_template(
        "dashboard.html",
        n_categories=n_categories, n_books=n_books,
        total_quantity=total_quantity, stock_value=stock_value,
        rows=rows, max_count=max_count, recent=recent,
    )


@app.post("/seed")
def seed():
    if db.session.scalar(db.select(func.count(Category.id))) > 0:
        flash("Đã có dữ liệu, không thêm dữ liệu mẫu nữa.", "error")
    else:
        seed_data()
        flash("Đã thêm dữ liệu mẫu.", "success")
    return redirect(url_for("dashboard"))


# ---------------------------------------------------------------- CRUD danh mục
@app.get("/categories")
def category_list():
    return render_template("category_list.html", rows=category_counts())


@app.route("/categories/new", methods=["GET", "POST"])
def category_create():
    form = {"name": "", "description": ""}
    errors = {}
    if request.method == "POST":
        form = read_form("name", "description")
        errors = validate_category(form)
        if not errors:
            db.session.add(Category(
                name=form["name"], description=form["description"] or None))
            db.session.commit()
            flash(f"Đã thêm danh mục “{form['name']}”.", "success")
            return redirect(url_for("category_list"))
    return render_template("category_form.html",
                           form=form, errors=errors, category=None)


@app.route("/categories/<int:category_id>/edit", methods=["GET", "POST"])
def category_edit(category_id):
    category = db.get_or_404(Category, category_id)
    form = {"name": category.name, "description": category.description or ""}
    errors = {}
    if request.method == "POST":
        form = read_form("name", "description")
        errors = validate_category(form, current_id=category.id)
        if not errors:
            category.name = form["name"]
            category.description = form["description"] or None
            db.session.commit()
            flash(f"Đã cập nhật danh mục “{category.name}”.", "success")
            return redirect(url_for("category_list"))
    return render_template("category_form.html",
                           form=form, errors=errors, category=category)


@app.post("/categories/<int:category_id>/delete")
def category_delete(category_id):
    category = db.get_or_404(Category, category_id)
    name = category.name
    n_books = len(category.books)
    db.session.delete(category)
    db.session.commit()
    if n_books:
        flash(f"Đã xoá danh mục “{name}” và {n_books} sách trong đó.", "success")
    else:
        flash(f"Đã xoá danh mục “{name}”.", "success")
    return redirect(url_for("category_list"))


# ---------------------------------------------------------------- CRUD sách theo danh mục
@app.get("/categories/<int:category_id>/books")
def category_books(category_id):
    category = db.get_or_404(Category, category_id)
    q = request.args.get("q", "").strip()
    stmt = (db.select(Book)
            .where(Book.category_id == category.id)
            .order_by(Book.title))
    if q:
        pattern = f"%{q}%"
        stmt = stmt.where(or_(Book.title.ilike(pattern), Book.author.ilike(pattern)))
    books = db.session.scalars(stmt).all()
    return render_template("category_books.html",
                           category=category, books=books, q=q)


@app.route("/books/new", methods=["GET", "POST"])
def book_create():
    categories = db.session.scalars(db.select(Category).order_by(Category.name)).all()
    if not categories:
        flash("Hãy tạo danh mục trước khi thêm sách.", "error")
        return redirect(url_for("category_create"))
    preselect = request.args.get("category_id", "")  # ?category_id=3 chọn sẵn danh mục
    form = {"title": "", "author": "", "year": "", "price": "", "quantity": "0",
            "category_id": preselect if to_int(preselect) is not None else ""}
    errors = {}
    if request.method == "POST":
        form = read_form(*BOOK_FIELDS)
        errors = validate_book(form)
        if not errors:
            book = Book()
            apply_book_form(book, form)
            db.session.add(book)
            db.session.commit()
            flash(f"Đã thêm sách “{book.title}”.", "success")
            return redirect(url_for("category_books", category_id=book.category_id))
    return render_template("book_form.html", form=form, errors=errors,
                           categories=categories, book=None)


@app.route("/books/<int:book_id>/edit", methods=["GET", "POST"])
def book_edit(book_id):
    book = db.get_or_404(Book, book_id)
    categories = db.session.scalars(db.select(Category).order_by(Category.name)).all()
    form = {"title": book.title, "author": book.author,
            "year": "" if book.year is None else str(book.year),
            "price": str(book.price), "quantity": str(book.quantity),
            "category_id": str(book.category_id)}
    errors = {}
    if request.method == "POST":
        form = read_form(*BOOK_FIELDS)
        errors = validate_book(form)
        if not errors:
            apply_book_form(book, form)
            db.session.commit()
            flash(f"Đã cập nhật sách “{book.title}”.", "success")
            return redirect(url_for("category_books", category_id=book.category_id))
    return render_template("book_form.html", form=form, errors=errors,
                           categories=categories, book=book)


@app.post("/books/<int:book_id>/delete")
def book_delete(book_id):
    book = db.get_or_404(Book, book_id)
    category_id = book.category_id
    title = book.title
    db.session.delete(book)
    db.session.commit()
    flash(f"Đã xoá sách “{title}”.", "success")
    return redirect(url_for("category_books", category_id=category_id))


if __name__ == "__main__":
    app.run(debug=True)