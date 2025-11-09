# ====== app.py ======
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, Response
from models import db, Order, PhoneNumber, Status, OrderHistory, Worker, Supplier, Product, Purchase, Transport, Debt, User, SystemSettings, WorkerHistory
from models import ExpenseCategory, Expense, ProductPriceHistory, ExpenseReceipt  # النماذج الجديدة
from models import TransportCategory, TransportSubType, TransportReceipt
from datetime import datetime, timezone, timedelta
import os
from sqlalchemy.orm import joinedload
from werkzeug.utils import secure_filename
import base64
from io import BytesIO
from PIL import Image

app = Flask(__name__)
app.secret_key = "secretkey123"

app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///data.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
# إعدادات تحميل الملفات للفواتير
UPLOAD_FOLDER = 'uploads/receipts'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
MAX_FILE_SIZE = 16 * 1024 * 1024  # 16MB

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_FILE_SIZE

# ==================== 🔄 APIs للتكامل مع تطبيق العمال ====================

@app.route('/api/workers/login', methods=['POST'])
def api_worker_login():
    """API لتسجيل دخول العمال من التطبيق"""
    if request.headers.get('Authorization') != 'Bearer worker_app':
        return jsonify({'error': 'غير مصرح'}), 401
    
    try:
        data = request.get_json()
        username = data.get('username')
        password = data.get('password')
        
        # البحث عن العامل (باستخدام الهاتف كاسم مستخدم)
        worker = Worker.query.filter_by(phone=username, is_active=True).first()
        
        if worker:
            # في الإصدار النهائي، استخدم تشفير كلمات المرور
            if password == "worker123":  # كلمة مرور افتراضية - تغييرها في الإنتاج
                return jsonify({
                    'success': True,
                    'id': worker.id,
                    'name': worker.name,
                    'phone': worker.phone,
                    'role': 'worker'
                }), 200
            else:
                return jsonify({'success': False, 'error': 'كلمة المرور غير صحيحة'}), 401
        else:
            return jsonify({'success': False, 'error': 'العامل غير موجود'}), 404
            
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/workers/<int:worker_id>/assigned-orders')
def api_worker_orders(worker_id):
    """API لجلب الطلبيات المعينة للعامل"""
    if request.headers.get('Authorization') != 'Bearer worker_app':
        return jsonify({'error': 'غير مصرح'}), 401
    
    try:
        # في هذا المثال، سنفترض وجود حقل assigned_worker_id في الطلبيات
        # تحتاج لإضافة هذا الحقل في قاعدة البيانات
        orders = Order.query.filter_by(assigned_worker_id=worker_id).all()
        
        orders_list = []
        for order in orders:
            # معلومات أساسية عن الطلبية
            order_info = {
                'id': order.id,
                'customer_name': order.name,
                'product': order.product,
                'address': order.wilaya,
                'phone': order.phones[0].number if order.phones else '',
                'assigned_date': order.created_at.strftime('%Y-%m-%d'),
                'expected_completion_date': (order.created_at + timedelta(days=7)).strftime('%Y-%m-%d'),
                'duration_days': 7,
                'status': 'in_progress'
            }
            orders_list.append(order_info)
        
        return jsonify({'success': True, 'orders': orders_list}), 200
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/workers/<int:worker_id>/salary-info')
def api_worker_salary(worker_id):
    """API لجلب معلومات الراتب للعامل"""
    if request.headers.get('Authorization') != 'Bearer worker_app':
        return jsonify({'error': 'غير مصرح'}), 401
    
    try:
        worker = Worker.query.get_or_404(worker_id)
        
        salary_info = {
            'success': True,
            'current_salary': worker.total_salary,
            'base_salary': worker.monthly_salary,
            'bonuses': worker.incentives + worker.outside_work_bonus,
            'deductions': worker.advances,
            'net_salary': worker.total_salary,
            'work_days': 22,  # سيتم حسابه بشكل دقيق
            'absence_days': worker.absences,
            'vacation_days': 0,
            'next_salary_date': (datetime.now(timezone.utc) + timedelta(days=5)).strftime('%Y-%m-%d')
        }
        
        return jsonify(salary_info), 200
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/orders/<int:order_id>/status', methods=['PUT'])
def api_update_order_status(order_id):
    """API لتحديث حالة الطلبية من قبل العامل"""
    if request.headers.get('Authorization') != 'Bearer worker_app':
        return jsonify({'error': 'غير مصرح'}), 401
    
    try:
        data = request.get_json()
        status = data.get('status')
        worker_id = data.get('worker_id')
        
        order = Order.query.get_or_404(order_id)
        
        # تحديث حالة الطلبية
        if status == 'completed':
            order.status_id = 2  # حالة مكتملة
        elif status == 'in_progress':
            order.status_id = 1  # حالة قيد التنفيذ
        
        # تسجيل في السجل
        history = OrderHistory(
            order_id=order.id,
            change_type="تحديث حالة من التطبيق",
            details=f"تم تحديث حالة الطلبية إلى {status} بواسطة العامل #{worker_id}"
        )
        db.session.add(history)
        db.session.commit()
        
        # إرسال إشعار للإدارة
        send_admin_notification(
            title="تحديث حالة طلبية",
            message=f"العامل #{worker_id} قام بتحديث حالة الطلبية #{order_id} إلى {status}",
            notification_type="order_update"
        )
        
        return jsonify({'success': True, 'message': 'تم تحديث حالة الطلبية'}), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/workers/<int:worker_id>/attendance', methods=['POST'])
def api_record_attendance(worker_id):
    """API لتسجيل حضور العامل من التطبيق"""
    if request.headers.get('Authorization') != 'Bearer worker_app':
        return jsonify({'error': 'غير مصرح'}), 401
    
    try:
        data = request.get_json()
        
        # هنا يمكنك تسجيل الحضور في قاعدة البيانات الرئيسية
        # هذا مثال لتسجيل الحضور
        attendance_record = WorkerAttendance(
            worker_id=worker_id,
            check_in_morning=data.get('check_in_morning'),
            check_out_morning=data.get('check_out_morning'),
            check_in_afternoon=data.get('check_in_afternoon'),
            check_out_afternoon=data.get('check_out_afternoon'),
            total_hours=data.get('total_hours', 0),
            absence_hours=data.get('absence_hours', 0),
            location_verified=data.get('location_verified', False),
            date=datetime.strptime(data.get('date'), '%Y-%m-%d').date()
        )
        
        db.session.add(attendance_record)
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'تم تسجيل الحضور'}), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

def send_admin_notification(title, message, notification_type="info"):
    """إرسال إشعار للمسؤولين"""
    # تنفيذ إرسال الإشعارات للمسؤولين
    # يمكن استخدام WebSockets أو قاعدة بيانات الإشعارات
    print(f"إشعار للمسؤولين: {title} - {message}")

# نموذج جدول حضور العمال (يضاف إلى models.py)
class WorkerAttendance(db.Model):
    __tablename__ = 'worker_attendance'
    __table_args__ = {'extend_existing': True}
    id = db.Column(db.Integer, primary_key=True)
    worker_id = db.Column(db.Integer, db.ForeignKey('worker.id'))
    date = db.Column(db.Date, default=datetime.now(timezone.utc).date())
    check_in_morning = db.Column(db.DateTime)
    check_out_morning = db.Column(db.DateTime)
    check_in_afternoon = db.Column(db.DateTime)
    check_out_afternoon = db.Column(db.DateTime)
    total_hours = db.Column(db.Float, default=0.0)
    absence_hours = db.Column(db.Float, default=0.0)
    location_verified = db.Column(db.Boolean, default=False)
    notes = db.Column(db.Text)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    worker = db.relationship('Worker', backref='attendance_records')

# إنشاء المجلد إذا لم يكن موجوداً
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def compress_image(image_data, max_size=(1200, 1200), quality=85):
    """ضغط الصورة للحفاظ على المساحة"""
    try:
        image = Image.open(BytesIO(image_data))
        
        # تغيير الحجم إذا كان كبيراً
        image.thumbnail(max_size, Image.Resampling.LANCZOS)
        
        # حفظ بصيغة مضغوطة
        output = BytesIO()
        image.save(output, format='JPEG', quality=quality, optimize=True)
        return output.getvalue()
    except Exception as e:
        print(f"خطأ في ضغط الصورة: {e}")
        return image_data
db.init_app(app)

# ========================
# 🔐 قسم المصادقة
# ========================

@app.route("/", methods=["GET", "POST"])
def login():
    """صفحة تسجيل الدخول"""
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        
        users = {
            "admin": "+f1234",
            "manager": "manager123",
            "user": "user123"
        }
        
        if username in users and password == users[username]:
            session["user"] = username
            session["role"] = username
            return redirect(url_for("dashboard"))
        else:
            return render_template("login.html", error="❌ اسم المستخدم أو كلمة المرور غير صحيحة")
    
    return render_template("login.html")

@app.route("/logout")
def logout():
    """تسجيل الخروج"""
    session.pop("user", None)
    return redirect(url_for("login"))

# ========================
# 📊 قسم لوحة التحكم
# ========================

@app.route("/dashboard")
def dashboard():
    """لوحة التحكم الرئيسية"""
    if "user" not in session:
        return redirect(url_for("login"))
    
    total_orders = Order.query.count()
    total_workers = Worker.query.count()
    total_debts = Debt.query.filter_by(status="unpaid").count()
    total_expenses = Expense.query.count()  # إضافة المصاريف للإحصائيات
    
    return render_template("dashboard.html", 
                         user=session["user"],
                         total_orders=total_orders,
                         total_workers=total_workers,
                         total_debts=total_debts,
                         total_expenses=total_expenses)  # تغيير total_purchases إلى total_expensestal_expenses

# ========================
# ⚡ قسم الطلبيات
# ========================

@app.route("/orders")
def orders():
    """صفحة إدارة الطلبيات"""
    if "user" not in session:
        return redirect(url_for("login"))
    
    show_paid = request.args.get('show_paid', 'false').lower() == 'true'
    
    if show_paid:
        orders = Order.query.options(joinedload(Order.phones)).order_by(Order.created_at.desc()).all()
    else:
        orders = Order.query.options(joinedload(Order.phones)).filter(Order.is_paid == False).order_by(Order.created_at.desc()).all()
    
    statuses = Status.query.all()
    products = Product.query.all()
    
    return render_template("orders.html", 
                         orders=orders, 
                         statuses=statuses, 
                         products=products,
                         show_paid=show_paid)

@app.route("/orders/add", methods=["POST"])
def add_order():
    """إضافة طلبية جديدة"""
    if "user" not in session:
        return redirect(url_for("login"))

    name = request.form.get("name")
    wilaya = request.form.get("wilaya")
    product = request.form.get("product")
    paid = float(request.form.get("paid") or 0)
    total = float(request.form.get("total") or 0)
    note = request.form.get("note", "")
    phones_raw = request.form.get("phones", "")
    status_id = request.form.get("status") or None

    order = Order(
        name=name, wilaya=wilaya, product=product, paid=paid, total=total, note=note,
        status_id=int(status_id) if status_id else None,
        is_paid=(paid >= total)
    )
    db.session.add(order)
    db.session.commit()

    phone_list = [p.strip() for p in phones_raw.split(",") if p.strip()]
    for idx, p in enumerate(phone_list):
        pn = PhoneNumber(order_id=order.id, number=p, is_primary=(idx==0))
        db.session.add(pn)
    db.session.commit()

    db.session.add(OrderHistory(order_id=order.id, change_type="إنشاء الطلب", details=f"إنشاء الطلب بواسطة {session.get('user')}"))
    db.session.commit()

    return redirect(url_for("orders"))

@app.route("/orders/edit/<int:id>", methods=["POST"])
def edit_order(id):
    """تعديل طلبية"""
    if "user" not in session:
        return redirect(url_for("login"))
    
    order = Order.query.get_or_404(id)
    
    old_data = {
        'name': order.name,
        'wilaya': order.wilaya,
        'product': order.product,
        'paid': order.paid,
        'total': order.total,
        'note': order.note,
        'status_id': order.status_id
    }
    
    order.name = request.form.get("name")
    order.wilaya = request.form.get("wilaya")
    order.product = request.form.get("product")
    order.paid = float(request.form.get("paid") or 0)
    order.total = float(request.form.get("total") or 0)
    order.note = request.form.get("note", "")
    order.status_id = request.form.get("status") or None
    order.is_paid = (order.paid >= order.total)
    
    changes = []
    if old_data['name'] != order.name:
        changes.append(f"تغيير الاسم: {old_data['name']} → {order.name}")
    if old_data['wilaya'] != order.wilaya:
        changes.append(f"تغيير الولاية: {old_data['wilaya']} → {order.wilaya}")
    if old_data['product'] != order.product:
        changes.append(f"تغيير المنتج: {old_data['product']} → {order.product}")
    if old_data['paid'] != order.paid:
        changes.append(f"تغيير المدفوع: {old_data['paid']} → {order.paid}")
    if old_data['total'] != order.total:
        changes.append(f"تغيير الإجمالي: {old_data['total']} → {order.total}")
    if old_data['status_id'] != order.status_id:
        old_status = Status.query.get(old_data['status_id'])
        new_status = Status.query.get(order.status_id)
        old_status_name = old_status.name if old_status else "بدون"
        new_status_name = new_status.name if new_status else "بدون"
        changes.append(f"تغيير الحالة: {old_status_name} → {new_status_name}")
    
    PhoneNumber.query.filter_by(order_id=order.id).delete()
    phones_raw = request.form.get("phones", "")
    phone_list = [p.strip() for p in phones_raw.split(",") if p.strip()]
    for idx, p in enumerate(phone_list):
        pn = PhoneNumber(order_id=order.id, number=p, is_primary=(idx==0))
        db.session.add(pn)
    
    if changes:
        change_details = " | ".join(changes)
        history = OrderHistory(
            order_id=order.id, 
            change_type="تعديل الطلبية", 
            details=f"تم التعديل بواسطة {session.get('user')}. التغييرات: {change_details}"
        )
        db.session.add(history)
    
    db.session.commit()
    return redirect(url_for("orders"))

@app.route("/orders/payment/<int:id>", methods=["POST"])
def add_order_payment(id):
    """إضافة دفعة على طلبية"""
    if "user" not in session:
        return jsonify({"success": False, "error": "غير مصرح"})
    
    try:
        order = Order.query.get_or_404(id)
        
        amount = float(request.form.get("amount") or 0)
        payment_date = datetime.strptime(request.form.get("payment_date"), "%Y-%m-%d")
        payment_method = request.form.get("payment_method", "نقدي")
        notes = request.form.get("notes", "")
        
        remaining = order.total - order.paid
        if amount > remaining:
            return jsonify({"success": False, "error": f"المبلغ يتجاوز المتبقي ({remaining} دج)"})
        
        order.paid += amount
        order.is_paid = (order.paid >= order.total)
        
        history = OrderHistory(
            order_id=order.id,
            change_type="دفعة مالية",
            details=f"تم إضافة دفعة بقيمة {amount} دج بواسطة {session.get('user')}. طريقة الدفع: {payment_method}. الملاحظات: {notes}"
        )
        db.session.add(history)
        db.session.commit()
        
        return jsonify({
            "success": True, 
            "message": "تم إضافة الدفعة بنجاح",
            "new_paid": order.paid,
            "new_remaining": order.total - order.paid,
            "is_paid": order.is_paid
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)})

@app.route("/orders/delete/<int:id>")
def delete_order(id):
    """حذف طلبية"""
    if "user" not in session:
        return redirect(url_for("login"))
    
    order = Order.query.get_or_404(id)
    db.session.delete(order)
    db.session.commit()
    
    return redirect(url_for("orders"))

@app.route("/orders/history/<int:id>")
def order_history(id):
    """سجل الطلبية"""
    if "user" not in session:
        return jsonify({"error": "غير مصرح"})
    
    order = Order.query.get_or_404(id)
    histories = OrderHistory.query.filter_by(order_id=id).order_by(OrderHistory.timestamp.desc()).all()
    
    result = []
    for h in histories:
        result.append({
            "change_type": h.change_type,
            "details": h.details,
            "timestamp": h.timestamp.strftime("%Y-%m-%d %H:%M:%S")
        })
    
    order_info = {
        "order_id": order.id,
        "customer_name": order.name,
        "total_amount": order.total,
        "paid_amount": order.paid,
        "remaining_amount": order.remaining,
        "is_paid": order.is_paid
    }
    
    return jsonify({
        "order_info": order_info,
        "history": result
    })

# ========================
# 👥 قسم العمال
# ========================

@app.route("/workers")
def workers():
    """صفحة إدارة العمال"""
    if "user" not in session:
        return redirect(url_for("login"))
    
    workers = Worker.query.order_by(Worker.created_at.desc()).all()
    
    total_salaries = sum(worker.total_salary for worker in workers)
    total_advances = sum(worker.advances for worker in workers)
    
    active_workers = [worker for worker in workers if worker.is_active]
    frozen_workers = [worker for worker in workers if not worker.is_active]
    
    return render_template(
        "workers.html", 
        workers=workers, 
        total_salaries=total_salaries,
        total_advances=total_advances,
        active_workers=active_workers,
        frozen_workers=frozen_workers,
        now=datetime.now(timezone.utc)
    )

@app.route("/workers/add", methods=["POST"])
def add_worker():
    """إضافة عامل جديد"""
    if "user" not in session:
        return redirect(url_for("login"))
    
    try:
        worker_data = {
            "name": request.form.get("name"),
            "phone": request.form.get("phone"),
            "address": request.form.get("address"),
            "id_card": request.form.get("id_card"),
            "start_date": datetime.strptime(request.form.get("start_date"), "%Y-%m-%d"),
            "monthly_salary": float(request.form.get("monthly_salary") or 0),
        }
        
        worker = Worker(**worker_data)
        db.session.add(worker)
        db.session.commit()
        
        return redirect(url_for("workers"))
    except Exception as e:
        db.session.rollback()
        return f"خطأ في إضافة العامل: {str(e)}", 400

@app.route("/workers/edit/<int:id>", methods=["POST"])
def edit_worker(id):
    """تعديل بيانات عامل"""
    if "user" not in session:
        return redirect(url_for("login"))
    
    try:
        worker = Worker.query.get_or_404(id)
        
        worker.name = request.form.get("name")
        worker.phone = request.form.get("phone")
        worker.address = request.form.get("address")
        worker.id_card = request.form.get("id_card")
        worker.monthly_salary = float(request.form.get("monthly_salary") or 0)
        
        db.session.commit()
        return redirect(url_for("workers"))
    except Exception as e:
        db.session.rollback()
        return f"خطأ في تعديل العامل: {str(e)}", 400

@app.route("/workers/delete/<int:id>")
def delete_worker(id):
    """حذف عامل"""
    if "user" not in session:
        return redirect(url_for("login"))
    
    try:
        worker = Worker.query.get_or_404(id)
        db.session.delete(worker)
        db.session.commit()
        return redirect(url_for("workers"))
    except Exception as e:
        db.session.rollback()
        return f"خطأ في حذف العامل: {str(e)}", 400

@app.route("/workers/toggle_status/<int:id>")
def toggle_worker_status(id):
    """تجميد/تفعيل عامل"""
    if "user" not in session:
        return redirect(url_for("login"))
    
    try:
        worker = Worker.query.get_or_404(id)
        worker.is_active = not worker.is_active
        db.session.commit()
        return redirect(url_for("workers"))
    except Exception as e:
        db.session.rollback()
        return f"خطأ في تغيير حالة العامل: {str(e)}", 400

@app.route("/workers/record_absence/<int:id>", methods=["POST"])
def record_worker_absence(id):
    """تسجيل غياب للعامل"""
    if "user" not in session:
        return jsonify({"success": False, "error": "غير مصرح"})
    
    try:
        worker = Worker.query.get_or_404(id)
        absence_type = request.form.get("type", "full")
        notes = request.form.get("notes", "")
        days_to_add = 0.5 if absence_type == "half" else 1
        
        daily_salary = worker.monthly_salary / 30.0
        deduction_amount = days_to_add * daily_salary
        
        worker.absences += days_to_add
        
        history = WorkerHistory(
            worker_id=worker.id,
            change_type="غياب",
            details=f"تسجيل {absence_type} غياب. {notes}",
            amount=-deduction_amount
        )
        db.session.add(history)
        
        db.session.commit()
        
        return jsonify({
            "success": True, 
            "message": f"تم تسجيل غياب {absence_type} للعامل",
            "new_absences": worker.absences,
            "deduction": deduction_amount
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)})

@app.route("/workers/record_advance/<int:id>", methods=["POST"])
def record_worker_advance(id):
    """تسجيل تسبيق للعامل"""
    if "user" not in session:
        return jsonify({"success": False, "error": "غير مصرح"})
    
    try:
        worker = Worker.query.get_or_404(id)
        amount = float(request.form.get("amount") or 0)
        notes = request.form.get("notes", "")
        
        worker.advances += amount
        
        history = WorkerHistory(
            worker_id=worker.id,
            change_type="تسبيق",
            details=f"تسجيل تسبيق. {notes}",
            amount=-amount
        )
        db.session.add(history)
        
        db.session.commit()
        
        return jsonify({
            "success": True, 
            "message": f"تم تسجيل تسبيق بمبلغ {amount} دج",
            "new_advances": worker.advances
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)})

@app.route("/workers/pay_salary/<int:id>", methods=["POST"])
def pay_worker_salary(id):
    """دفع راتب العامل"""
    if "user" not in session:
        return jsonify({"success": False, "error": "غير مصرح"})
    
    try:
        worker = Worker.query.get_or_404(id)
        amount = float(request.form.get("amount") or 0)
        payment_method = request.form.get("payment_method", "نقدي")
        notes = request.form.get("notes", "")
        
        if amount <= 0:
            return jsonify({"success": False, "error": "المبلغ يجب أن يكون أكبر من الصفر"})
        
        current_total_salary = worker.total_salary
        
        if amount > current_total_salary:
            return jsonify({"success": False, "error": f"المبلغ يتجاوز المستحق ({current_total_salary:.2f} دج)"})
        
        old_data = {
            'start_date': worker.start_date.strftime('%Y-%m-%d'),
            'absences': worker.absences,
            'outside_work_days': worker.outside_work_days,
            'outside_work_bonus': worker.outside_work_bonus,
            'advances': worker.advances,
            'incentives': worker.incentives,
            'late_hours': worker.late_hours,
            'total_salary': worker.total_salary
        }
        
        worker.start_date = datetime.now(timezone.utc).date()
        worker.absences = 0
        worker.outside_work_days = 0
        worker.outside_work_bonus = 0
        worker.advances = 0
        worker.incentives = 0
        worker.late_hours = 0
        
        history = WorkerHistory(
            worker_id=worker.id,
            change_type="دفع راتب",
            details=f"تم دفع راتب بقيمة {amount:.2f} دج. طريقة الدفع: {payment_method}. {notes} | بداية فترة جديدة من: {worker.start_date.strftime('%Y-%m-%d')}",
            amount=-amount
        )
        db.session.add(history)
        
        db.session.commit()
        
        new_total_salary = worker.total_salary
        
        return jsonify({
            "success": True, 
            "message": f"تم دفع راتب بقيمة {amount:.2f} دج وبدء فترة عمل جديدة",
            "paid_amount": amount,
            "new_start_date": worker.start_date.strftime('%Y-%m-%d'),
            "old_salary": current_total_salary,
            "new_salary": new_total_salary,
            "worker_name": worker.name
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ خطأ في دفع الراتب: {str(e)}")
        return jsonify({"success": False, "error": str(e)})

# ========================
# 💰 قسم المصاريف والمشتريات (المحسّن)
# ========================

@app.route("/expenses")
def expenses():
    """صفحة إدارة المصاريف والمشتريات - المحسنة"""
    if "user" not in session:
        return redirect(url_for("login"))
    
    expense_type = request.args.get('type', 'all')
    category_id = request.args.get('category', '')
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    
    query = Expense.query
    
    if expense_type == 'paid':
        query = query.filter(Expense.payment_status == 'paid')
    elif expense_type == 'unpaid':
        query = query.filter(Expense.payment_status == 'unpaid')
    elif expense_type == 'owner':
        query = query.filter(Expense.purchased_by == 'owner')
    elif expense_type == 'partner':
        query = query.filter(Expense.purchased_by == 'partner')
    elif expense_type == 'worker':
        query = query.filter(Expense.purchased_by == 'worker')
    
    if category_id and category_id != 'all':
        query = query.filter(Expense.category_id == int(category_id))
    
    if date_from:
        query = query.filter(Expense.purchase_date >= datetime.strptime(date_from, "%Y-%m-%d"))
    if date_to:
        query = query.filter(Expense.purchase_date <= datetime.strptime(date_to, "%Y-%m-%d"))
    
    expenses_list = query.order_by(Expense.created_at.desc()).all()
    categories = ExpenseCategory.query.all()
    suppliers = Supplier.query.all()
    
    total_amount = sum(expense.total_amount for expense in expenses_list)
    paid_amount = sum(expense.total_amount for expense in expenses_list if expense.payment_status == 'paid')
    unpaid_amount = sum(expense.total_amount for expense in expenses_list if expense.payment_status == 'unpaid')
    
    return render_template("expenses.html", 
                         expenses=expenses_list,
                         categories=categories,
                         suppliers=suppliers,
                         expense_type=expense_type,
                         category_id=category_id,
                         date_from=date_from,
                         date_to=date_to,
                         total_amount=total_amount,
                         paid_amount=paid_amount,
                         unpaid_amount=unpaid_amount)

@app.route("/expenses/add", methods=["POST"])
def add_expense():
    """إضافة مصروف جديد - مع إعادة التوجيه"""
    if "user" not in session:
        return jsonify({"success": False, "error": "غير مصرح"})
    
    try:
        quantity = int(request.form.get("quantity", 1))
        unit_price = float(request.form.get("unit_price", 0))
        total_amount = quantity * unit_price
        
        # جعل supplier_id اختياري - يمكن أن يكون None
        supplier_id = request.form.get("supplier_id")
        if supplier_id and supplier_id != '':
            supplier_id = int(supplier_id)
        else:
            supplier_id = None
        
        # الحصول على حالة الدفع والمبلغ المدفوع مع قيم افتراضية
        payment_status = request.form.get("payment_status", "paid")
        paid_amount = float(request.form.get("paid_amount", 0) or 0)
        
        expense = Expense(
            category_id=int(request.form.get("category_id")),
            description=request.form.get("description", ""),
            amount=total_amount,
            quantity=quantity,
            unit_price=unit_price,
            total_amount=total_amount,
            supplier_id=supplier_id,
            purchased_by=request.form.get("purchased_by", "owner"),
            recorded_by=session["user"],
            purchase_date=datetime.strptime(request.form.get("purchase_date"), "%Y-%m-%d"),
            payment_status=payment_status,
            payment_method=request.form.get("payment_method", "cash"),
            notes=request.form.get("notes", "")
        )
        db.session.add(expense)
        db.session.flush()  # هذا مهم للحصول على expense.id قبل الـ commit
        
        # حفظ في سجل الأسعار إذا طلب المستخدم ذلك
        if request.form.get("save_to_price_history") == "yes":
            price_history = ProductPriceHistory(
                product_name=request.form.get("description", ""),
                supplier_id=supplier_id,
                price=unit_price,
                purchase_date=datetime.strptime(request.form.get("purchase_date"), "%Y-%m-%d"),
                recorded_by=session["user"]
            )
            db.session.add(price_history)
        
        # 🆕 إذا كان المصروف غير مدفوع أو مدفوع جزئياً، إنشاء دين تلقائياً
        if payment_status in ['unpaid', 'partial']:
            remaining_amount = total_amount - paid_amount
            
            debt = Debt(
                name=expense.supplier.name if expense.supplier else "مورد",
                phone=expense.supplier.phone if expense.supplier else "",
                address=expense.supplier.address if expense.supplier else "",
                debt_amount=total_amount,
                paid_amount=paid_amount,
                start_date=expense.purchase_date,
                status="unpaid",
                source_type='expense',
                source_id=expense.id,
                description=f"{expense.description} - {expense.category.name if expense.category else 'عام'}",
                recorded_by=session["user"]
            )
            db.session.add(debt)
            print(f"✅ تم إنشاء دين تلقائي للمصروف #{expense.id}")
        
        # حفظ الفاتورة إذا كانت موجودة
        if 'receipt' in request.files:
            file = request.files['receipt']
            if file and file.filename != '':
                # حفظ الفاتورة
                file_data = file.read()
                if file_data:
                    compressed_data = compress_image(file_data)
                    
                    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
                    file_extension = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else 'jpg'
                    filename = f"receipt_{expense.id}_{timestamp}.{file_extension}"
                    
                    receipt = ExpenseReceipt(
                        expense_id=expense.id,
                        filename=filename,
                        original_filename=file.filename,
                        file_size=len(compressed_data),
                        mime_type=file.mimetype,
                        image_data=compressed_data,
                        captured_by=session["user"]
                    )
                    db.session.add(receipt)
        
        db.session.commit()
        print(f"✅ تم إضافة المصروف #{expense.id} بحالة دفع: {payment_status}")
        
        return redirect(url_for('expenses'))
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ خطأ في إضافة المصروف: {str(e)}")
        return jsonify({"success": False, "error": str(e)})

@app.route("/expenses/price_history")
def get_price_history():
    """الحصول على السجل التاريخي لأسعار المنتج"""
    if "user" not in session:
        return jsonify({"error": "غير مصرح"})
    
    product_name = request.args.get('product_name', '')
    
    if not product_name:
        return jsonify({"error": "اسم المنتج مطلوب"})
    
    price_history = ProductPriceHistory.query.filter(
        ProductPriceHistory.product_name.ilike(f"%{product_name}%")
    ).order_by(ProductPriceHistory.purchase_date.desc()).limit(10).all()
    
    result = []
    for item in price_history:
        result.append({
            "product_name": item.product_name,
            "supplier": item.supplier.name if item.supplier else "غير معروف",
            "price": item.price,
            "purchase_date": item.purchase_date.strftime("%Y-%m-%d"),
            "recorded_by": item.recorded_by
        })
    
    return jsonify({"success": True, "price_history": result})

@app.route("/expenses/quick_add", methods=["POST"])
def quick_add_expense():
    """إضافة مصروف سريع - مع إعادة التوجيه"""
    if "user" not in session:
        return jsonify({"error": "غير مصرح"})
    
    try:
        # جعل supplier_id اختياري
        supplier_id = request.form.get("supplier_id")
        if supplier_id and supplier_id != '':
            supplier_id = int(supplier_id)
        else:
            supplier_id = None
            
        amount = float(request.form.get("amount", 0))
        quantity = int(request.form.get("quantity", 1))
        total_amount = amount * quantity
        
        # الحصول على حالة الدفع والمبلغ المدفوع مع قيم افتراضية
        payment_status = request.form.get("payment_status", "paid")
        paid_amount = float(request.form.get("paid_amount", 0) or 0)
        
        expense = Expense(
            category_id=int(request.form.get("category_id")),
            description=request.form.get("description", ""),
            amount=total_amount,
            quantity=quantity,
            unit_price=amount,
            total_amount=total_amount,
            supplier_id=supplier_id,
            purchased_by="owner",
            recorded_by=session["user"],
            purchase_date=datetime.now(timezone.utc).date(),
            payment_status=payment_status,
            payment_method="cash",
            notes=request.form.get("notes", "")
        )
        db.session.add(expense)
        db.session.flush()  # هذا مهم للحصول على expense.id قبل الـ commit
        
        # 🆕 إذا كان المصروف غير مدفوع أو مدفوع جزئياً، إنشاء دين تلقائياً
        if payment_status in ['unpaid', 'partial']:
            remaining_amount = total_amount - paid_amount
            
            debt = Debt(
                name=expense.supplier.name if expense.supplier else "مورد",
                phone=expense.supplier.phone if expense.supplier else "",
                address=expense.supplier.address if expense.supplier else "",
                debt_amount=total_amount,
                paid_amount=paid_amount,
                start_date=expense.purchase_date,
                status="unpaid",
                source_type='expense',
                source_id=expense.id,
                description=f"{expense.description} - {expense.category.name if expense.category else 'عام'}",
                recorded_by=session["user"]
            )
            db.session.add(debt)
            print(f"✅ تم إنشاء دين تلقائي للمصروف السريع #{expense.id}")
        
        # حفظ الفاتورة إذا كانت موجودة
        if 'receipt' in request.files:
            file = request.files['receipt']
            if file and file.filename != '':
                # حفظ الفاتورة
                file_data = file.read()
                if file_data:
                    compressed_data = compress_image(file_data)
                    
                    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
                    file_extension = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else 'jpg'
                    filename = f"receipt_{expense.id}_{timestamp}.{file_extension}"
                    
                    receipt = ExpenseReceipt(
                        expense_id=expense.id,
                        filename=filename,
                        original_filename=file.filename,
                        file_size=len(compressed_data),
                        mime_type=file.mimetype,
                        image_data=compressed_data,
                        captured_by=session["user"]
                    )
                    db.session.add(receipt)
        
        db.session.commit()
        print(f"✅ تم إضافة المصروف السريع #{expense.id} بحالة دفع: {payment_status}")
        
        return redirect(url_for('expenses'))
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ خطأ في الإضافة السريعة: {str(e)}")
        return jsonify({"success": False, "error": str(e)})

@app.route("/expenses/statistics")
def expenses_statistics():
    """إحصائيات المصاريف"""
    if "user" not in session:
        return jsonify({"error": "غير مصرح"})
    
    categories_stats = db.session.query(
        ExpenseCategory.name,
        db.func.sum(Expense.total_amount).label('total')
    ).join(Expense).group_by(ExpenseCategory.name).all()
    
    monthly_stats = db.session.query(
        db.func.strftime('%Y-%m', Expense.purchase_date).label('month'),
        db.func.sum(Expense.total_amount).label('total')
    ).group_by('month').order_by('month').all()
    
    suppliers_stats = db.session.query(
        Supplier.name,
        db.func.sum(Expense.total_amount).label('total')
    ).join(Expense).group_by(Supplier.name).all()
    
    return jsonify({
        "success": True,
        "categories_stats": [{"name": stat[0], "total": stat[1]} for stat in categories_stats],
        "monthly_stats": [{"month": stat[0], "total": stat[1]} for stat in monthly_stats],
        "suppliers_stats": [{"name": stat[0], "total": stat[1]} for stat in suppliers_stats]
    })

@app.route("/expenses/delete/<int:id>")
def delete_expense(id):
    """حذف مصروف"""
    if "user" not in session:
        return redirect(url_for("login"))
    
    try:
        expense = Expense.query.get_or_404(id)
        db.session.delete(expense)
        db.session.commit()
        return redirect(url_for('expenses'))  # إعادة التوجيه بدلاً من JSON
    except Exception as e:
        db.session.rollback()
        return redirect(url_for('expenses'))
    

@app.route("/expenses/delete_ajax/<int:id>", methods=["DELETE"])
def delete_expense_ajax(id):
    """حذف مصروف باستخدام AJAX"""
    if "user" not in session:
        return jsonify({"success": False, "error": "غير مصرح"})
    
    try:
        expense = Expense.query.get_or_404(id)
        db.session.delete(expense)
        db.session.commit()
        return jsonify({"success": True, "message": "تم حذف المصروف بنجاح"})
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)})


# ========================
# 📸 قسم فواتير المصاريف (الجديد)
# ========================

@app.route("/expenses/<int:expense_id>/receipts")
def get_expense_receipts(expense_id):
    """الحصول على فواتير المصروف"""
    if "user" not in session:
        return jsonify({"error": "غير مصرح"})
    
    try:
        receipts = ExpenseReceipt.query.filter_by(expense_id=expense_id).all()
        result = []
        for receipt in receipts:
            result.append({
                "id": receipt.id,
                "filename": receipt.filename,
                "original_filename": receipt.original_filename,
                "file_size": receipt.file_size,
                "mime_type": receipt.mime_type,
                "captured_at": receipt.captured_at.strftime("%Y-%m-%d %H:%M"),
                "captured_by": receipt.captured_by
            })
        
        return jsonify({"success": True, "receipts": result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route("/expenses/<int:expense_id>/receipts/upload", methods=["POST"])
def upload_expense_receipt(expense_id):
    """رفع فاتورة للمصروف"""
    if "user" not in session:
        return jsonify({"success": False, "error": "غير مصرح"})
    
    try:
        # التحقق من وجود المصروف
        expense = Expense.query.get_or_404(expense_id)
        
        if 'receipt' not in request.files:
            return jsonify({"success": False, "error": "لم يتم اختيار ملف"})
        
        file = request.files['receipt']
        
        if file.filename == '':
            return jsonify({"success": False, "error": "لم يتم اختيار ملف"})
        
        if file and allowed_file(file.filename):
            # قراءة بيانات الملف
            file_data = file.read()
            
            # ضغط الصورة
            compressed_data = compress_image(file_data)
            
            # إنشاء اسم فريد للملف
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            file_extension = file.filename.rsplit('.', 1)[1].lower()
            filename = f"receipt_{expense_id}_{timestamp}.{file_extension}"
            
            # حفظ في قاعدة البيانات
            receipt = ExpenseReceipt(
                expense_id=expense_id,
                filename=filename,
                original_filename=file.filename,
                file_size=len(compressed_data),
                mime_type=file.mimetype,
                image_data=compressed_data,
                captured_by=session["user"]
            )
            db.session.add(receipt)
            db.session.commit()
            
            return jsonify({
                "success": True, 
                "message": "تم رفع الفاتورة بنجاح",
                "receipt_id": receipt.id
            })
        else:
            return jsonify({"success": False, "error": "نوع الملف غير مسموح"})
            
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)})

@app.route("/expenses/<int:expense_id>/receipts/capture", methods=["POST"])
def capture_expense_receipt(expense_id):
    """التقاط فاتورة مباشرة من الكاميرا"""
    if "user" not in session:
        return jsonify({"success": False, "error": "غير مصرح"})
    
    try:
        expense = Expense.query.get_or_404(expense_id)
        
        if 'image' not in request.json:
            return jsonify({"success": False, "error": "لا توجد بيانات صورة"})
        
        # الحصول على بيانات الصورة base64
        image_data_url = request.json['image']
        
        # تحويل base64 إلى بيانات ثنائية
        if ',' in image_data_url:
            header, data = image_data_url.split(',', 1)
            image_data = base64.b64decode(data)
        else:
            image_data = base64.b64decode(image_data_url)
        
        # ضغط الصورة
        compressed_data = compress_image(image_data)
        
        # إنشاء اسم فريد
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        filename = f"receipt_{expense_id}_{timestamp}.jpg"
        
        # حفظ في قاعدة البيانات
        receipt = ExpenseReceipt(
            expense_id=expense_id,
            filename=filename,
            original_filename=f"كاميرا_{timestamp}.jpg",
            file_size=len(compressed_data),
            mime_type="image/jpeg",
            image_data=compressed_data,
            captured_by=session["user"]
        )
        db.session.add(receipt)
        db.session.commit()
        
        return jsonify({
            "success": True, 
            "message": "تم حفظ الصورة بنجاح",
            "receipt_id": receipt.id
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)})
@app.route("/expenses/<int:expense_id>/receipts/capture_upload", methods=["POST"])
def capture_upload_expense_receipt(expense_id):
    """رفع فاتورة ملتقطة بالكاميرا"""
    if "user" not in session:
        return jsonify({"success": False, "error": "غير مصرح"})
    
    try:
        expense = Expense.query.get_or_404(expense_id)
        
        if 'image' not in request.files:
            return jsonify({"success": False, "error": "لا توجد صورة"})
        
        file = request.files['image']
        
        if file and file.filename != '':
            # حفظ الفاتورة
            file_data = file.read()
            if file_data:
                compressed_data = compress_image(file_data)
                
                timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
                filename = f"receipt_{expense.id}_{timestamp}.jpg"
                
                receipt = ExpenseReceipt(
                    expense_id=expense.id,
                    filename=filename,
                    original_filename=f"كاميرا_{timestamp}.jpg",
                    file_size=len(compressed_data),
                    mime_type="image/jpeg",
                    image_data=compressed_data,
                    captured_by=session["user"]
                )
                db.session.add(receipt)
                db.session.commit()
                
                return jsonify({
                    "success": True, 
                    "message": "تم حفظ الفاتورة بنجاح",
                    "receipt_id": receipt.id
                })
        
        return jsonify({"success": False, "error": "لم يتم حفظ الصورة"})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)})

@app.route("/receipts/<int:receipt_id>")
def get_receipt_image(receipt_id):
    """عرض صورة الفاتورة"""
    if "user" not in session:
        return jsonify({"error": "غير مصرح"})
    
    try:
        receipt = ExpenseReceipt.query.get_or_404(receipt_id)
        
        # إرجاع الصورة كاستجابة
        return Response(receipt.image_data, mimetype=receipt.mime_type)
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route("/receipts/<int:receipt_id>/delete", methods=["DELETE"])
def delete_receipt(receipt_id):
    """حذف فاتورة"""
    if "user" not in session:
        return jsonify({"success": False, "error": "غير مصرح"})
    
    try:
        receipt = ExpenseReceipt.query.get_or_404(receipt_id)
        db.session.delete(receipt)
        db.session.commit()
        
        return jsonify({"success": True, "message": "تم حذف الفاتورة بنجاح"})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)})
    
    # ========================
# 📦 واجهات برمجة التطبيقات للمنتجات
# ========================

@app.route("/api/category_products")
def get_category_products():
    """الحصول على المنتجات حسب التصنيف"""
    if "user" not in session:
        return jsonify({"error": "غير مصرح"})
    
    category_id = request.args.get('category_id')
    
    if category_id and category_id != 'all':
        products = Product.query.filter_by(category_id=category_id).all()
    else:
        products = Product.query.all()
    
    result = [{"id": p.id, "name": p.name} for p in products]
    return jsonify({"success": True, "products": result})

@app.route("/api/products/add", methods=["POST"])
def add_product():
    """إضافة منتج جديد"""
    if "user" not in session:
        return jsonify({"error": "غير مصرح"})
    
    try:
        data = request.get_json()
        product = Product(
            name=data['name'],
            category_id=data['category_id']
        )
        db.session.add(product)
        db.session.commit()
        
        return jsonify({"success": True, "message": "تم إضافة المنتج بنجاح", "product_id": product.id})
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)})

@app.route("/api/expenses/<int:expense_id>")
def get_expense(expense_id):
    """الحصول على بيانات مصروف للتعديل"""
    if "user" not in session:
        return jsonify({"error": "غير مصرح"})
    
    try:
        expense = Expense.query.get_or_404(expense_id)
        return jsonify({
            "success": True,
            "expense": {
                "id": expense.id,
                "category_id": expense.category_id,
                "description": expense.description,
                "unit_price": expense.unit_price,
                "quantity": expense.quantity,
                "supplier_id": expense.supplier_id,
                "purchase_date": expense.purchase_date.strftime('%Y-%m-%d'),
                "payment_status": expense.payment_status,
                "payment_method": expense.payment_method,
                "notes": expense.notes
            }
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route("/expenses/edit/<int:expense_id>", methods=["POST"])
def edit_expense(expense_id):
    """تعديل مصروف - الإصلاح"""
    if "user" not in session:
        return jsonify({"success": False, "error": "غير مصرح"})
    
    try:
        expense = Expense.query.get_or_404(expense_id)
        
        quantity = int(request.form.get("quantity", 1))
        unit_price = float(request.form.get("unit_price", 0))
        total_amount = quantity * unit_price
        
        supplier_id = request.form.get("supplier_id")
        if supplier_id and supplier_id != '':
            supplier_id = int(supplier_id)
        else:
            supplier_id = None
        
        # تحديث البيانات فقط - بدون إنشاء جديد
        expense.category_id = int(request.form.get("category_id"))
        expense.description = request.form.get("description", "")
        expense.quantity = quantity
        expense.unit_price = unit_price
        expense.total_amount = total_amount
        expense.supplier_id = supplier_id
        expense.purchase_date = datetime.strptime(request.form.get("purchase_date"), "%Y-%m-%d")
        expense.payment_status = request.form.get("payment_status", "paid")
        expense.payment_method = request.form.get("payment_method", "cash")
        expense.notes = request.form.get("notes", "")
        
        db.session.commit()
        
        return jsonify({"success": True, "message": "تم تعديل المصروف بنجاح"})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)})

# ========================
# 🏢 قسم الموردين
# ========================

# ========================
# 🏢 قسم الموردين
# ========================

@app.route("/suppliers")
def suppliers():
    """صفحة الموردين"""
    if "user" not in session:
        return redirect(url_for("login"))
    
    suppliers = Supplier.query.order_by(Supplier.created_at.desc()).all()
    return render_template("suppliers.html", suppliers=suppliers)

@app.route("/suppliers/add", methods=["POST"])
def add_supplier():
    """إضافة مورد جديد"""
    if "user" not in session:
        return jsonify({"success": False, "error": "غير مصرح"})
    
    try:
        supplier = Supplier(
            name=request.form.get("name"),
            phone=request.form.get("phone"),
            address=request.form.get("address")
        )
        db.session.add(supplier)
        db.session.commit()
        
        return jsonify({"success": True, "message": "تم إضافة المورد بنجاح", "supplier_id": supplier.id})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)})

# ========================
# 🛒 قسم المشتريات القديم (دمج مع النظام الجديد)
# ========================

@app.route("/purchases")
def purchases():
    """دمج المشتريات مع النظام الجديد للمصاريف"""
    if "user" not in session:
        return redirect(url_for("login"))
    
    # استخدام نفس دالة المصاريف الجديدة
    return expenses()  # هذا سيوجه المستخدم لنفس صفحة المصاريف

@app.route("/purchases/add", methods=["POST"])
def add_purchase():
    """إضافة مشتريات (قديم)"""
    if "user" not in session:
        return redirect(url_for("login"))
    
    try:
        # الحصول على supplier_id والتعامل مع القيمة الفارغة
        supplier_id_str = request.form.get("supplier_id", "")
        supplier_id = None
        
        if supplier_id_str and supplier_id_str.strip():
            supplier_id = int(supplier_id_str)
        
        product_id_str = request.form.get("product_id")
        if not product_id_str:
            return "خطأ: يجب اختيار المنتج", 400
        
        purchase = Purchase(
            supplier_id=supplier_id,  # يمكن أن تكون None الآن
            product_id=int(product_id_str),
            price=float(request.form.get("price") or 0),
            quantity=int(request.form.get("quantity") or 1),
            total_price=float(request.form.get("price") or 0) * int(request.form.get("quantity") or 1),
            purchase_date=datetime.strptime(request.form.get("purchase_date"), "%Y-%m-%d"),
            status=request.form.get("status", "unpaid"),
            type=request.form.get("type", "fixed")
        )
        db.session.add(purchase)
        db.session.commit()
        
        # فقط إذا كان هناك مورد وكانت العملية غير مدفوعة، نضيف دين
        if purchase.status == "unpaid" and supplier_id:
            supplier = Supplier.query.get(purchase.supplier_id)
            if supplier:  # تأكد من وجود المورد
                debt = Debt(
                    name=supplier.name,
                    phone=supplier.phone,
                    address=supplier.address,
                    debt_amount=purchase.total_price,
                    paid_amount=0.0
                )
                db.session.add(debt)
                db.session.commit()
        
        return redirect(url_for("purchases", type=purchase.type))
        
    except ValueError as e:
        db.session.rollback()
        return f"خطأ في القيم المدخلة: {str(e)}", 400
    except Exception as e:
        db.session.rollback()
        return f"حدث خطأ: {str(e)}", 500

@app.route("/purchases/paid/<int:id>")
def mark_purchase_paid(id):
    """تعيين المشتريات كمدفوعة"""
    if "user" not in session:
        return redirect(url_for("login"))
    
    purchase = Purchase.query.get_or_404(id)
    purchase.status = "paid"
    db.session.commit()
    
    return redirect(url_for("purchases"))

@app.route("/purchases/delete/<int:id>")
def delete_purchase(id):
    """حذف مشتريات"""
    if "user" not in session:
        return redirect(url_for("login"))
    
    purchase = Purchase.query.get_or_404(id)
    db.session.delete(purchase)
    db.session.commit()
    
    return redirect(url_for("purchases"))

# ========================
# 🚚 قسم النقل المحسّن
# ========================

@app.route("/transport")
def transport():
    """صفحة النقل المحسّنة - محدثة"""
    if "user" not in session:
        return redirect(url_for("login"))
    
    transport_type = request.args.get('type', 'inside')
    category_id = request.args.get('category', '')
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    
    query = Transport.query.options(
        joinedload(Transport.category),
        joinedload(Transport.sub_type),
        joinedload(Transport.receipts)
    )
    
    if transport_type == 'inside':
        query = query.filter(Transport.type == 'inside')
    elif transport_type == 'outside':
        query = query.filter(Transport.type == 'outside')
    
    if category_id and category_id != 'all':
        query = query.filter(Transport.category_id == int(category_id))
    
    if date_from:
        query = query.filter(Transport.transport_date >= datetime.strptime(date_from, "%Y-%m-%d"))
    if date_to:
        query = query.filter(Transport.transport_date <= datetime.strptime(date_to, "%Y-%m-%d"))
    
    transports = query.order_by(Transport.created_at.desc()).all()
    categories = TransportCategory.query.all()
    sub_types = TransportSubType.query.all()
    
    total_amount = sum(transport.transport_amount for transport in transports)
    paid_amount = sum(transport.paid_amount for transport in transports)
    remaining_amount = sum(transport.remaining_amount for transport in transports)
    
    return render_template("transport.html", 
                         transports=transports, 
                         transport_type=transport_type,
                         categories=categories,
                         sub_types=sub_types,
                         category_id=category_id,
                         date_from=date_from,
                         date_to=date_to,
                         total_amount=total_amount,
                         paid_amount=paid_amount,
                         remaining_amount=remaining_amount,
                         now=datetime.now(timezone.utc))

@app.route("/transport/add", methods=["POST"])
def add_transport():
    """إضافة نقل جديد - النظام المحسّن"""
    if "user" not in session:
        return jsonify({"success": False, "error": "غير مصرح"})
    
    try:
        # جعل الحقول اختيارية
        category_id = request.form.get("category_id")
        if category_id and category_id != '':
            category_id = int(category_id)
        else:
            category_id = None
            
        sub_type_id = request.form.get("sub_type_id")
        if sub_type_id and sub_type_id != '':
            sub_type_id = int(sub_type_id)
        else:
            sub_type_id = None
        
        transport_amount = float(request.form.get("transport_amount", 0))
        
        # الحصول على حالة الدفع والمبلغ المدفوع مع قيم افتراضية
        payment_status = request.form.get("payment_status", "paid")
        paid_amount = float(request.form.get("paid_amount", 0) or 0)
        
        transport = Transport(
            name=request.form.get("name", "نقل شخصي"),
            phone=request.form.get("phone", ""),
            address=request.form.get("address", ""),
            transport_amount=transport_amount,
            destination=request.form.get("destination", "العلمة"),
            paid_amount=paid_amount,
            type=request.form.get("type", "inside"),
            category_id=category_id,
            sub_type_id=sub_type_id,
            transport_method=request.form.get("transport_method", "car"),
            purpose=request.form.get("purpose", ""),
            distance=float(request.form.get("distance", 0)),
            notes=request.form.get("notes", ""),
            is_quick=request.form.get("is_quick") == "true",
            recorded_by=session["user"],  # إضافة اسم المستخدم
            transport_date=datetime.strptime(request.form.get("transport_date"), "%Y-%m-%d")
        )
        db.session.add(transport)
        db.session.flush()
        
        # 🆕 إذا كان النقل غير مدفوع أو مدفوع جزئياً، إنشاء دين تلقائياً
        if payment_status in ['unpaid', 'partial']:
            remaining_amount = transport_amount - paid_amount
            
            debt = Debt(
                name=transport.name,
                phone=transport.phone,
                address=transport.address,
                debt_amount=transport_amount,
                paid_amount=paid_amount,
                start_date=transport.transport_date,
                status="unpaid",
                source_type='transport',
                source_id=transport.id,
                description=f"{transport.purpose} - {transport.destination}",
                recorded_by=session["user"]
            )
            db.session.add(debt)
            print(f"✅ تم إنشاء دين تلقائي للنقل #{transport.id}")
        
        # حفظ الفاتورة إذا كانت موجودة
        if 'receipt' in request.files:
            file = request.files['receipt']
            if file and file.filename != '':
                file_data = file.read()
                if file_data:
                    compressed_data = compress_image(file_data)
                    
                    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
                    file_extension = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else 'jpg'
                    filename = f"transport_receipt_{transport.id}_{timestamp}.{file_extension}"
                    
                    receipt = TransportReceipt(
                        transport_id=transport.id,
                        filename=filename,
                        original_filename=file.filename,
                        file_size=len(compressed_data),
                        mime_type=file.mimetype,
                        image_data=compressed_data,
                        captured_by=session["user"]
                    )
                    db.session.add(receipt)
        
        db.session.commit()
        print(f"✅ تم إضافة النقل #{transport.id} بحالة دفع: {payment_status}")
        
        return redirect(url_for("transport", type=transport.type))
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ خطأ في إضافة النقل: {str(e)}")
        return jsonify({"success": False, "error": str(e)})

@app.route("/transport/quick_add", methods=["POST"])
def quick_add_transport():
    """إضافة نقل سريع - محدث"""
    if "user" not in session:
        return jsonify({"success": False, "error": "غير مصرح"})
    
    try:
        # جعل category_id اختياري
        category_id = request.form.get("category_id")
        if category_id and category_id != '':
            category_id = int(category_id)
        else:
            category_id = None

        amount = float(request.form.get("amount", 0))
        
        # الحصول على حالة الدفع والمبلغ المدفوع مع قيم افتراضية
        payment_status = request.form.get("payment_status", "paid")
        paid_amount = float(request.form.get("paid_amount", 0) or 0)

        transport = Transport(
            name="نقل سريع",
            transport_amount=amount,
            paid_amount=paid_amount,
            type="inside",
            category_id=category_id,
            transport_method=request.form.get("transport_method", "taxi"),
            purpose=request.form.get("purpose", "تنقل سريع"),
            is_quick=True,
            recorded_by=session["user"],  # إضافة اسم المستخدم
            transport_date=datetime.now(timezone.utc).date(),
            notes=request.form.get("notes", "")
        )
        db.session.add(transport)
        db.session.flush()  # للحصول على ID قبل الـ commit
        
        # 🆕 إذا كان النقل غير مدفوع أو مدفوع جزئياً، إنشاء دين تلقائياً
        if payment_status in ['unpaid', 'partial']:
            remaining_amount = amount - paid_amount
            
            debt = Debt(
                name=transport.name,
                phone=transport.phone,
                address=transport.address,
                debt_amount=amount,
                paid_amount=paid_amount,
                start_date=transport.transport_date,
                status="unpaid",
                source_type='transport',
                source_id=transport.id,
                description=f"{transport.purpose} - {transport.destination}",
                recorded_by=session["user"]
            )
            db.session.add(debt)
            print(f"✅ تم إنشاء دين تلقائي للنقل السريع #{transport.id}")
        
        # حفظ الفاتورة إذا كانت موجودة
        if 'receipt' in request.files:
            file = request.files['receipt']
            if file and file.filename != '':
                file_data = file.read()
                if file_data:
                    compressed_data = compress_image(file_data)
                    
                    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
                    file_extension = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else 'jpg'
                    filename = f"transport_receipt_{transport.id}_{timestamp}.{file_extension}"
                    
                    receipt = TransportReceipt(
                        transport_id=transport.id,
                        filename=filename,
                        original_filename=file.filename,
                        file_size=len(compressed_data),
                        mime_type=file.mimetype,
                        image_data=compressed_data,
                        captured_by=session["user"]
                    )
                    db.session.add(receipt)
        
        db.session.commit()
        print(f"✅ تم إضافة النقل السريع #{transport.id} بحالة دفع: {payment_status}")
        
        return redirect(url_for("transport"))
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ خطأ في إضافة النقل السريع: {str(e)}")
        return jsonify({"success": False, "error": str(e)})

@app.route("/transport/delete/<int:id>")
def delete_transport(id):
    """حذف نقل"""
    if "user" not in session:
        return redirect(url_for("login"))
    
    try:
        transport = Transport.query.get_or_404(id)
        db.session.delete(transport)
        db.session.commit()
        return redirect(url_for("transport", type=transport.type))
    except Exception as e:
        db.session.rollback()
        return redirect(url_for("transport"))

@app.route("/transport/pay/<int:id>", methods=["POST"])
def add_transport_payment(id):
    """إضافة دفعة على نقل"""
    if "user" not in session:
        return jsonify({"success": False, "error": "غير مصرح"})
    
    try:
        transport = Transport.query.get_or_404(id)
        
        amount = float(request.form.get("amount", 0))
        payment_method = request.form.get("payment_method", "نقدي")
        notes = request.form.get("notes", "")
        
        if amount > transport.remaining_amount:
            return jsonify({"success": False, "error": f"المبلغ يتجاوز المتبقي ({transport.remaining_amount} دج)"})
        
        transport.paid_amount += amount
        
        db.session.commit()
        
        return jsonify({
            "success": True, 
            "message": f"تم إضافة دفعة بقيمة {amount} دج",
            "new_paid": transport.paid_amount,
            "new_remaining": transport.remaining_amount
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)})

@app.route("/api/transport_subtypes")
def get_transport_subtypes():
    """الحصول على الأنواع الفرعية حسب التصنيف"""
    if "user" not in session:
        return jsonify({"error": "غير مصرح"})
    
    category_id = request.args.get('category_id')
    if category_id and category_id != 'all':
        sub_types = TransportSubType.query.filter_by(category_id=category_id).all()
    else:
        sub_types = TransportSubType.query.all()
    
    result = [{"id": st.id, "name": st.name} for st in sub_types]
    return jsonify({"success": True, "sub_types": result})

@app.route("/transport/<int:transport_id>/receipts/upload", methods=["POST"])
def upload_transport_receipt(transport_id):
    """رفع فاتورة للنقل - محدثة"""
    if "user" not in session:
        return jsonify({"success": False, "error": "غير مصرح"})
    
    try:
        transport = Transport.query.get_or_404(transport_id)
        
        if 'receipt' not in request.files:
            return jsonify({"success": False, "error": "لم يتم اختيار ملف"})
        
        file = request.files['receipt']
        
        if file.filename == '':
            return jsonify({"success": False, "error": "لم يتم اختيار ملف"})
        
        if file and allowed_file(file.filename):
            file_data = file.read()
            compressed_data = compress_image(file_data)
            
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            file_extension = file.filename.rsplit('.', 1)[1].lower()
            filename = f"transport_receipt_{transport_id}_{timestamp}.{file_extension}"
            
            receipt = TransportReceipt(
                transport_id=transport_id,
                filename=filename,
                original_filename=file.filename,
                file_size=len(compressed_data),
                mime_type=file.mimetype,
                image_data=compressed_data,
                captured_by=session["user"]  # إضافة اسم المستخدم
            )
            db.session.add(receipt)
            db.session.commit()
            
            return jsonify({
                "success": True, 
                "message": "تم رفع الفاتورة بنجاح",
                "receipt_id": receipt.id
            })
        else:
            return jsonify({"success": False, "error": "نوع الملف غير مسموح"})
            
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)})

@app.route("/transport/receipts/<int:receipt_id>")
def get_transport_receipt_image(receipt_id):
    """عرض صورة فاتورة النقل"""
    if "user" not in session:
        return jsonify({"error": "غير مصرح"})
    
    try:
        receipt = TransportReceipt.query.get_or_404(receipt_id)
        return Response(receipt.image_data, mimetype=receipt.mime_type)
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

# ========================
# 🚚 دوال النقل الجديدة
# ========================

@app.route("/transport/<int:transport_id>/receipts")
def get_transport_receipts(transport_id):
    """الحصول على فواتير النقل"""
    if "user" not in session:
        return jsonify({"error": "غير مصرح"})
    
    try:
        receipts = TransportReceipt.query.filter_by(transport_id=transport_id).all()
        result = []
        for receipt in receipts:
            result.append({
                "id": receipt.id,
                "filename": receipt.filename,
                "original_filename": receipt.original_filename,
                "file_size": receipt.file_size,
                "mime_type": receipt.mime_type,
                "captured_at": receipt.captured_at.strftime("%Y-%m-%d %H:%M"),
                "captured_by": receipt.captured_by
            })
        
        return jsonify({"success": True, "receipts": result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route("/transport/receipts/<int:receipt_id>/delete", methods=["DELETE"])
def delete_transport_receipt(receipt_id):
    """حذف فاتورة النقل"""
    if "user" not in session:
        return jsonify({"success": False, "error": "غير مصرح"})
    
    try:
        receipt = TransportReceipt.query.get_or_404(receipt_id)
        transport_id = receipt.transport_id
        db.session.delete(receipt)
        db.session.commit()
        
        return jsonify({"success": True, "message": "تم حذف الفاتورة بنجاح"})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)})
    
# ========================
# 💸 قسم الديون
# ========================
# ========================
# 🔄 دوال التحديث الذكي بين الجداول
# ========================

@app.route("/debts/update_source/<int:debt_id>", methods=["POST"])
def update_debt_source(debt_id):
    """تحديث المصدر الأصلي (مصروف/نقل) عند سداد الدين"""
    if "user" not in session:
        return jsonify({"success": False, "error": "غير مصرح"})
    
    try:
        debt = Debt.query.get_or_404(debt_id)
        payment_amount = float(request.form.get("payment_amount", 0))
        
        print(f"🔄 جاري تحديث المصدر للدين #{debt_id} بمبلغ {payment_amount}")
        
        # تحديث المصدر الأصلي حسب نوع المصدر
        if debt.source_type == 'expense':
            expense = Expense.query.get(debt.source_id)
            if expense:
                # تحديث المبلغ المدفوع في المصروف
                expense.paid_amount = debt.paid_amount + payment_amount
                
                # تحديث حالة الدفع بناءً على المبلغ المدفوع
                if expense.paid_amount >= expense.total_amount:
                    expense.payment_status = 'paid'
                    print(f"✅ تم تحديث المصروف #{expense.id} إلى حالة: مدفوعة")
                elif expense.paid_amount > 0:
                    expense.payment_status = 'partial'
                    print(f"✅ تم تحديث المصروف #{expense.id} إلى حالة: مدفوع جزئياً")
                else:
                    expense.payment_status = 'unpaid'
                    print(f"✅ تم تحديث المصروف #{expense.id} إلى حالة: غير مدفوعة")
                
                db.session.commit()
                return jsonify({
                    "success": True, 
                    "message": f"تم تحديث المصروف #{expense.id} بنجاح",
                    "new_status": expense.payment_status,
                    "paid_amount": expense.paid_amount
                })
            else:
                return jsonify({"success": False, "error": "المصروف المرتبط غير موجود"})
        
        elif debt.source_type == 'transport':
            transport = Transport.query.get(debt.source_id)
            if transport:
                # تحديث المبلغ المدفوع في النقل
                transport.paid_amount = debt.paid_amount + payment_amount
                
                print(f"✅ تم تحديث النقل #{transport.id} - المدفوع: {transport.paid_amount} دج")
                
                db.session.commit()
                return jsonify({
                    "success": True, 
                    "message": f"تم تحديث النقل #{transport.id} بنجاح",
                    "paid_amount": transport.paid_amount
                })
            else:
                return jsonify({"success": False, "error": "النقل المرتبط غير موجود"})
        
        else:
            return jsonify({"success": False, "error": "نوع المصدر غير معروف"})
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ خطأ في تحديث المصدر: {str(e)}")
        return jsonify({"success": False, "error": str(e)})
@app.route("/debts")
def debts():
    """صفحة الديون المحسنة - النظام الذكي"""
    if "user" not in session:
        return redirect(url_for("login"))
    
    debt_status = request.args.get('status', 'unpaid')
    source_type = request.args.get('source', 'all')
    
    # جلب الديون اليدوية
    manual_debts_query = Debt.query.filter(Debt.source_type == 'manual')
    
    # جلب الديون التلقائية من المصاريف غير المدفوعة
    expense_debts = []
    unpaid_expenses = Expense.query.filter(Expense.payment_status == 'unpaid').all()
    for expense in unpaid_expenses:
        # التحقق إذا كان هذا المصروف مضافاً كدين مسبقاً
        existing_debt = Debt.query.filter_by(source_type='expense', source_id=expense.id).first()
        if not existing_debt:
            debt = Debt(
                name=expense.supplier.name if expense.supplier else "مورد",
                phone=expense.supplier.phone if expense.supplier else "",
                address=expense.supplier.address if expense.supplier else "",
                debt_amount=expense.total_amount,
                paid_amount=0.0,
                start_date=expense.purchase_date,
                status="unpaid",
                source_type='expense',
                source_id=expense.id,
                description=f"{expense.description} - {expense.category.name if expense.category else 'عام'}",
                recorded_by=expense.recorded_by
            )
            expense_debts.append(debt)
    
    # جلب الديون التلقائية من المشتريات غير المدفوعة
    purchase_debts = []
    unpaid_purchases = Purchase.query.filter(Purchase.status == "unpaid").all()
    for purchase in unpaid_purchases:
        existing_debt = Debt.query.filter_by(source_type='purchase', source_id=purchase.id).first()
        if not existing_debt and purchase.supplier:
            debt = Debt(
                name=purchase.supplier.name,
                phone=purchase.supplier.phone,
                address=purchase.supplier.address,
                debt_amount=purchase.total_price,
                paid_amount=0.0,
                start_date=purchase.purchase_date,
                status="unpaid",
                source_type='purchase',
                source_id=purchase.id,
                description=f"{purchase.product.name if purchase.product else 'منتج'} - {purchase.quantity} وحدة",
                recorded_by="system"
            )
            purchase_debts.append(debt)
    
    # جلب الديون التلقائية من النقل غير المدفوع
    transport_debts = []
    unpaid_transports = Transport.query.filter(Transport.paid_amount < Transport.transport_amount).all()
    for transport in unpaid_transports:
        existing_debt = Debt.query.filter_by(source_type='transport', source_id=transport.id).first()
        if not existing_debt and transport.remaining_amount > 0:
            debt = Debt(
                name=transport.name,
                phone=transport.phone,
                address=transport.address,
                debt_amount=transport.remaining_amount,
                paid_amount=0.0,
                start_date=transport.transport_date,
                status="unpaid",
                source_type='transport',
                source_id=transport.id,
                description=f"{transport.purpose} - {transport.destination}",
                recorded_by=transport.recorded_by
            )
            transport_debts.append(debt)
    
    # حفظ الديون التلقائية الجديدة في قاعدة البيانات
    for debt in expense_debts + purchase_debts + transport_debts:
        db.session.add(debt)
    
    if expense_debts or purchase_debts or transport_debts:
        db.session.commit()
    
    # بناء الاستعلام النهائي للديون
    query = Debt.query
    
    if debt_status == 'unpaid':
        query = query.filter(Debt.status == 'unpaid')
    elif debt_status == 'paid':
        query = query.filter(Debt.status == 'paid')
    
    if source_type != 'all':
        query = query.filter(Debt.source_type == source_type)
    
    debts_list = query.order_by(Debt.created_at.desc()).all()
    
    # حساب الإحصائيات
    total_debts = sum(debt.remaining_amount for debt in debts_list if debt.status == 'unpaid')
    total_all_debts = sum(debt.debt_amount for debt in debts_list)
    total_paid = sum(debt.paid_amount for debt in debts_list)
    
    # إحصائيات حسب المصدر
    expense_debts_count = Debt.query.filter_by(source_type='expense', status='unpaid').count()
    purchase_debts_count = Debt.query.filter_by(source_type='purchase', status='unpaid').count()
    transport_debts_count = Debt.query.filter_by(source_type='transport', status='unpaid').count()
    manual_debts_count = Debt.query.filter_by(source_type='manual', status='unpaid').count()
    
    return render_template("debts.html", 
                         debts=debts_list, 
                         debt_status=debt_status,
                         source_type=source_type,
                         total_debts=total_debts,
                         total_all_debts=total_all_debts,
                         total_paid=total_paid,
                         expense_debts_count=expense_debts_count,
                         purchase_debts_count=purchase_debts_count,
                         transport_debts_count=transport_debts_count,
                         manual_debts_count=manual_debts_count,
                         now=datetime.now(timezone.utc))

@app.route("/debts/add", methods=["POST"])
def add_debt():
    """إضافة دين يدوي"""
    if "user" not in session:
        return redirect(url_for("login"))
    
    debt = Debt(
        name=request.form.get("name"),
        phone=request.form.get("phone"),
        address=request.form.get("address"),
        debt_amount=float(request.form.get("debt_amount") or 0),
        paid_amount=float(request.form.get("paid_amount") or 0),
        start_date=datetime.strptime(request.form.get("start_date"), "%Y-%m-%d"),
        status="unpaid",
        source_type='manual',
        description=request.form.get("description", ""),
        recorded_by=session["user"]
    )
    db.session.add(debt)
    db.session.commit()
    
    return redirect(url_for("debts"))

@app.route("/debts/pay/<int:id>", methods=["POST"])
def pay_debt_smart(id):
    """دفع دين - النظام الذكي مع التحديث التلقائي للمصدر"""
    if "user" not in session:
        return jsonify({"success": False, "error": "غير مصرح"})
    
    try:
        debt = Debt.query.get_or_404(id)
        payment_amount = float(request.form.get("payment_amount", 0))
        payment_date = datetime.strptime(request.form.get("payment_date"), "%Y-%m-%d")
        notes = request.form.get("notes", "")
        
        if payment_amount <= 0:
            return jsonify({"success": False, "error": "المبلغ يجب أن يكون أكبر من الصفر"})
        
        if payment_amount > debt.remaining_amount:
            return jsonify({"success": False, "error": f"المبلغ يتجاوز المتبقي ({debt.remaining_amount} دج)"})
        
        # تحديث المبلغ المدفوع في الدين
        old_paid_amount = debt.paid_amount
        debt.paid_amount += payment_amount
        
        # إذا تم دفع كامل المبلغ، تحديث الحالة
        if debt.paid_amount >= debt.debt_amount:
            debt.status = "paid"
            debt.payment_date = payment_date
            print(f"✅ تم دفع الدين #{debt.id} بالكامل")
        else:
            print(f"✅ تم دفع {payment_amount} دج للدين #{debt.id} (مدفوع جزئياً)")
        
        # 🆕 تحديث المصدر الأصلي (مصروف/نقل) تلقائياً
        update_response = update_debt_source(debt.id)
        
        db.session.commit()
        
        return jsonify({
            "success": True, 
            "message": f"تم دفع {payment_amount} دج بنجاح وتحديث المصدر الأصلي",
            "new_paid": debt.paid_amount,
            "new_remaining": debt.remaining_amount,
            "status": debt.status,
            "source_updated": True
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)})

@app.route("/debts/pay_full/<int:id>")
def pay_debt(id):
    """دفع دين كامل - للتوافق مع النظام القديم"""
    if "user" not in session:
        return redirect(url_for("login"))
    
    debt = Debt.query.get_or_404(id)
    debt.paid_amount = debt.debt_amount
    debt.payment_date = datetime.now(timezone.utc)
    debt.status = "paid"
    
    # تحديث المصدر الأصلي إذا كان موجوداً
    if debt.source_type == 'expense':
        expense = Expense.query.get(debt.source_id)
        if expense:
            expense.payment_status = 'paid'
            expense.paid_amount = expense.total_amount
    elif debt.source_type == 'purchase':
        purchase = Purchase.query.get(debt.source_id)
        if purchase:
            purchase.status = "paid"
            purchase.paid_amount = purchase.total_price
    
    db.session.commit()
    
    return redirect(url_for("debts"))

@app.route("/debts/delete/<int:id>")
def delete_debt(id):
    """حذف دين"""
    if "user" not in session:
        return redirect(url_for("login"))
    
    debt = Debt.query.get_or_404(id)
    db.session.delete(debt)
    db.session.commit()
    return redirect(url_for("debts"))

# ========================
# 📊 قسم الإحصائيات
# ========================

@app.route("/stats")
def stats():
    """صفحة الإحصائيات"""
    if "user" not in session:
        return redirect(url_for("login"))
    
    total_orders = Order.query.count()
    paid_orders = Order.query.filter_by(is_paid=True).count()
    pending_orders = Order.query.filter_by(is_paid=False).count()
    total_orders_amount = sum(order.total for order in Order.query.all())
    
    workers = Worker.query.all()
    total_workers = len(workers)
    total_salaries = sum(worker.total_salary for worker in workers)
    
    debts = Debt.query.all()
    total_debts = len(debts)
    debts_unpaid = Debt.query.filter_by(status="unpaid").count()
    debts_paid = Debt.query.filter_by(status="paid").count()
    total_debts_amount = sum(debt.remaining_amount for debt in Debt.query.filter_by(status="unpaid"))
    debts_paid_amount = sum(debt.debt_amount for debt in Debt.query.filter_by(status="paid"))
    
    expenses = Expense.query.all()
    total_expenses = len(expenses)
    expenses_amount = sum(expense.total_amount for expense in expenses)
    
    return render_template("stats.html",
                         total_orders=total_orders,
                         paid_orders=paid_orders,
                         pending_orders=pending_orders,
                         total_orders_amount=total_orders_amount,
                         total_workers=total_workers,
                         total_salaries=total_salaries,
                         workers=workers,
                         total_debts=total_debts,
                         total_debts_amount=total_debts_amount,
                         debts_unpaid=debts_unpaid,
                         debts_paid=debts_paid,
                         debts_paid_amount=debts_paid_amount,
                         total_expenses=total_expenses,
                         expenses_amount=expenses_amount,
                         now=datetime.now(timezone.utc))

# ========================
# ⚙️ قسم الإعدادات
# ========================

@app.route("/settings")
def settings():
    """صفحة الإعدادات"""
    if "user" not in session:
        return redirect(url_for("login"))
    
    users = User.query.all()
    statuses = Status.query.all()
    suppliers = Supplier.query.all()
    products = Product.query.all()
    expense_categories = ExpenseCategory.query.all()
    settings_obj = SystemSettings.query.first()
    
    return render_template("settings.html", 
                         users=users,
                         statuses=statuses,
                         suppliers=suppliers,
                         products=products,
                         expense_categories=expense_categories,
                         settings=settings_obj)

@app.route("/settings/user/add", methods=["POST"])
def add_settings_user():
    """إضافة مستخدم"""
    if "user" not in session:
        return redirect(url_for("login"))
    
    user = User(
        username=request.form.get("username"),
        email=request.form.get("email"),
        password=request.form.get("password"),
        full_name=request.form.get("full_name"),
        phone=request.form.get("phone"),
        role=request.form.get("role", "user"),
        is_active=True
    )
    db.session.add(user)
    db.session.commit()
    
    return redirect(url_for("settings"))

@app.route("/settings/user/toggle/<int:user_id>")
def toggle_user_status(user_id):
    """تفعيل/تعطيل مستخدم"""
    if "user" not in session:
        return redirect(url_for("login"))
    
    user = User.query.get_or_404(user_id)
    user.is_active = not user.is_active
    db.session.commit()
    
    return redirect(url_for("settings"))

@app.route("/settings/user/delete/<int:user_id>")
def delete_settings_user(user_id):
    """حذف مستخدم"""
    if "user" not in session:
        return redirect(url_for("login"))
    
    user = User.query.get_or_404(user_id)
    db.session.delete(user)
    db.session.commit()
    
    return redirect(url_for("settings"))

@app.route("/settings/status/add", methods=["POST"])
def add_status():
    """إضافة حالة"""
    if "user" not in session:
        return redirect(url_for("login"))
    
    status = Status(
        name=request.form.get("name"),
        color=request.form.get("color", "#FFC107")
    )
    db.session.add(status)
    db.session.commit()
    
    return redirect(url_for("settings"))

@app.route("/settings/status/delete/<int:id>")
def delete_status(id):
    """حذف حالة"""
    if "user" not in session:
        return redirect(url_for("login"))
    st = Status.query.get_or_404(id)
    db.session.delete(st)
    db.session.commit()
    return redirect(url_for("settings"))

@app.route("/settings/status/edit/<int:id>", methods=["POST"])
def edit_status(id):
    """تعديل حالة"""
    if "user" not in session:
        return redirect(url_for("login"))
    st = Status.query.get_or_404(id)
    st.name = request.form.get("name")
    st.color = request.form.get("color") or st.color
    db.session.commit()
    return redirect(url_for("settings"))

@app.route("/settings/expense_category/add", methods=["POST"])
def add_expense_category():
    """إضافة تصنيف مصاريف"""
    if "user" not in session:
        return redirect(url_for("login"))
    
    category = ExpenseCategory(
        name=request.form.get("name"),
        icon=request.form.get("icon", "📦"),
        color=request.form.get("color", "#3B82F6")
    )
    db.session.add(category)
    db.session.commit()
    
    return redirect(url_for("settings"))

# ========================
# 🔌 APIs إضافية
# ========================

@app.route("/api/supplier/<int:id>")
def get_supplier(id):
    """API للحصول على بيانات المورد"""
    if "user" not in session:
        return jsonify({"error": "غير مصرح"})
    supplier = Supplier.query.get_or_404(id)
    return jsonify({
        "name": supplier.name,
        "phone": supplier.phone,
        "address": supplier.address
    })

# ========================
# 🗃️ تهيئة القاعدة
# ========================

with app.app_context():
    try:
        # التحقق من وجود الأعمدة الجديدة في جدول الديون وإضافتها إذا كانت مفقودة
        from sqlalchemy import inspect, text
        
        inspector = inspect(db.engine)
        
        # التحقق إذا كان جدول الديون موجوداً
        if 'debt' in inspector.get_table_names():
            debt_columns = [col['name'] for col in inspector.get_columns('debt')]
            print(f"🔍 الأعمدة الحالية في جدول الديون: {debt_columns}")
            
            # الأعمدة المطلوبة في النموذج الجديد
            required_columns = ['source_type', 'source_id', 'description', 'recorded_by']
            missing_columns = [col for col in required_columns if col not in debt_columns]
            
            if missing_columns:
                print(f"🔄 جاري إضافة الأعمدة المفقودة: {missing_columns}")
                
                try:
                    with db.engine.begin() as conn:
                        for column in missing_columns:
                            try:
                                if column == 'source_type':
                                    conn.execute(text("ALTER TABLE debt ADD COLUMN source_type VARCHAR(50)"))
                                elif column == 'source_id':
                                    conn.execute(text("ALTER TABLE debt ADD COLUMN source_id INTEGER"))
                                elif column == 'description':
                                    conn.execute(text("ALTER TABLE debt ADD COLUMN description TEXT"))
                                elif column == 'recorded_by':
                                    conn.execute(text("ALTER TABLE debt ADD COLUMN recorded_by VARCHAR(50)"))
                                print(f"✅ تم إضافة العمود: {column}")
                            except Exception as column_error:
                                print(f"⚠️ لم يتم إضافة العمود {column}: {column_error}")
                    
                    print("✅ تم تحديث جدول الديون بنجاح")
                    
                except Exception as alter_error:
                    print(f"❌ خطأ في تحديث الجدول: {alter_error}")
            else:
                print("✅ جدول الديون محدث ومحتوي على جميع الأعمدة المطلوبة")
        else:
            print("ℹ️ جدول الديون غير موجود، سيتم إنشاؤه تلقائياً")
        
    except Exception as e:
        print(f"❌ خطأ في التحقق من الجدول: {e}")
    
    # إنشاء جميع الجداول (سيتم إنشاء الجداول الجديدة فقط)
    db.create_all()
    
    try:
        if not SystemSettings.query.first():
            db.session.add(SystemSettings())
            print("✅ تم إضافة إعدادات النظام")
        
        if not Status.query.first():
            db.session.add(Status(name="قيد التنفيذ", color="#FFC107"))
            db.session.add(Status(name="مدفوعة", color="#28A745"))
            print("✅ تم إضافة الحالات الافتراضية")
        
        # تهيئة تصنيفات المصاريف الجديدة
        if not ExpenseCategory.query.first():
            categories = [
                ExpenseCategory(name="مواد بناء", icon="🏗️", color="#EF4444"),
                ExpenseCategory(name="مواد تلحيم", icon="🔥", color="#3B82F6"),
                ExpenseCategory(name="محركات ومعدات", icon="⚡", color="#10B981"),
                ExpenseCategory(name="عتاد الورشة", icon="🔧", color="#F59E0B"),
                ExpenseCategory(name="مصاريف تركيب", icon="🚚", color="#8B5CF6"),
                ExpenseCategory(name="مصاريف تشغيل", icon="💼", color="#06B6D4"),
                ExpenseCategory(name="مصاريف صيانة", icon="🛠️", color="#F97316"),
                ExpenseCategory(name="مشتريات عمال", icon="👷", color="#84CC16")
            ]
            for category in categories:
                db.session.add(category)
            print("✅ تم إضافة تصنيفات المصاريف")
        
        if not User.query.first():
            admin_user = User(
                username="admin",
                password="+f1234",
                full_name="مدير النظام",
                role="admin",
                is_active=True
            )
            db.session.add(admin_user)
            print("✅ تم إضافة مستخدم المدير")
        
        # ✅ تهيئة المنتجات
        if not Product.query.first():
            default_products = {
                "مواد بناء": ["صباغة", "شوفيات", "لصقة كحلة", "مفاتيح", "مفك براغي", "أسمنت", "رمل", "طوب"],
                "مواد تلحيم": ["ديسك تقطاع صغير", "ديسك مولاج صغير", "ديسك تقطاع متوسط", "ديسك تقطاع كبير", "بقيط 3", "بقيط 2", "TUBE CARE 20 PAR 18", "TUBE CARE 40 PAR 18"],
                "محركات ومعدات": ["مونتشارج بيترو 500", "مونتشارج بيترو 600", "مونتشارج بيترو 800", "مونتشارج بيترو 1000", "رولو كابل 2×1.5", "رولو 3×1.5", "فانت كورس", "كونطاكتار"],
                "عتاد الورشة": ["طرونسوناز كبيرة كراون", "بوسطا سودي 250A كراون", "طرونسوناز اطابل كراون", "نيفو لازار", "نيفو المنيوم", "مفكات", "شواكيش"],
                "مصاريف تركيب": ["اطعام العمال", "حقوق الايواء", "شراء اضطراري عند السفر", "مواصلات", "فنادق"],
                "مصاريف تشغيل": ["تأمين العمال", "تأمين المسير", "كهرباء", "غاز", "ماء", "كراء", "ضرائب", "اتصالات"],
                "مصاريف صيانة": ["صيانة السيارة", "صيانة العتاد", "صيانة المباني", "صيانة المعدات"],
                "مشتريات العمال": ["أدوات وقائية", "ملابس عمل", "مستلزمات شخصية"]
            }
            
            product_count = 0
            for category in ExpenseCategory.query.all():
                if category.name in default_products:
                    for product_name in default_products[category.name]:
                        product = Product(name=product_name, category_id=category.id)
                        db.session.add(product)
                        product_count += 1
            
            print(f"✅ تم إضافة {product_count} منتج")
        
        # ✅ تهيئة تصنيفات وأنواع النقل
        if not TransportCategory.query.first():
            transport_categories = [
                TransportCategory(name="معاينة مواقع", icon="📍", color="#3B82F6"),
                TransportCategory(name="تركيب معدات", icon="⚡", color="#10B981"),
                TransportCategory(name="إصلاح أعطال", icon="🔧", color="#F59E0B"),
                TransportCategory(name="شراء مواد", icon="🛒", color="#EF4444"),
                TransportCategory(name="بحث عن منتجات", icon="🔍", color="#8B5CF6"),
                TransportCategory(name="توصيل سلع", icon="🚚", color="#06B6D4"),
                TransportCategory(name="اجتماعات عمل", icon="💼", color="#F97316"),
                TransportCategory(name="تنقلات شخصية", icon="👤", color="#84CC16")
            ]
            for category in transport_categories:
                db.session.add(category)
            
            db.session.flush()
            
            # إضافة الأنواع الفرعية
            sub_types_data = {
                "معاينة مواقع": ["معاينة تركيب مونتشارج", "معاينة موقع عميل", "معاينة موقع جديد"],
                "تركيب معدات": ["تركيب مونتشارج", "تركيب محركات", "تركيب معدات ورشة"],
                "إصلاح أعطال": ["إصلاح أخطاء تركيب", "صيانة وقائية", "إصلاح عطل طارئ"],
                "شراء مواد": ["شراء مواد بناء", "شراء مواد تلحيم", "شراء معدات", "شراء مستلزمات"],
                "بحث عن منتجات": ["بحث عن سعر", "مقارنة أسعار", "بحث عن مورد جديد"],
                "توصيل سلع": ["توصيل للعميل", "استلام من المورد", "نقل بين الورش"],
                "اجتماعات عمل": ["اجتماع مع عميل", "اجتماع مع مورد", "اجتماع مع فريق"],
                "تنقلات شخصية": ["ذهاب للعمل", "عودة من العمل", "مهمة شخصية"]
            }
            
            sub_type_count = 0
            for category in transport_categories:
                if category.name in sub_types_data:
                    for sub_type_name in sub_types_data[category.name]:
                        sub_type = TransportSubType(name=sub_type_name, category_id=category.id)
                        db.session.add(sub_type)
                        sub_type_count += 1
            
            print(f"✅ تم إضافة {len(transport_categories)} تصنيف نقل و {sub_type_count} نوع فرعي")
        
        db.session.commit()
        print("🎉 تم تهيئة قاعدة البيانات بنجاح بالكامل")
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ خطأ في تهيئة قاعدة البيانات: {e}")

# ==================== 🔄 APIs للتكامل مع تطبيق العمال ====================

@app.route('/api/workers/login', methods=['POST'])
def api_worker_login():
    """API لتسجيل دخول العمال من التطبيق"""
    if request.headers.get('Authorization') != 'Bearer worker_app':
        return jsonify({'error': 'غير مصرح'}), 401
    
    try:
        data = request.get_json()
        username = data.get('username')
        password = data.get('password')
        
        # البحث عن العامل (باستخدام الهاتف كاسم مستخدم)
        worker = Worker.query.filter_by(phone=username, is_active=True).first()
        
        if worker:
            # في الإصدار النهائي، استخدم تشفير كلمات المرور
            if password == "worker123":  # كلمة مرور افتراضية - تغييرها في الإنتاج
                return jsonify({
                    'success': True,
                    'id': worker.id,
                    'name': worker.name,
                    'phone': worker.phone,
                    'role': 'worker'
                }), 200
            else:
                return jsonify({'success': False, 'error': 'كلمة المرور غير صحيحة'}), 401
        else:
            return jsonify({'success': False, 'error': 'العامل غير موجود'}), 404
            
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/workers/<int:worker_id>/assigned-orders')
def api_worker_orders(worker_id):
    """API لجلب الطلبيات المعينة للعامل"""
    if request.headers.get('Authorization') != 'Bearer worker_app':
        return jsonify({'error': 'غير مصرح'}), 401
    
    try:
        # جلب الطلبيات المعينة للعامل
        orders = Order.query.filter(Order.assigned_worker_id == worker_id).all()
        
        orders_list = []
        for order in orders:
            order_info = {
                'id': order.id,
                'customer_name': order.name,
                'product': order.product,
                'address': order.wilaya,
                'phone': order.phones[0].number if order.phones else '',
                'assigned_date': order.created_at.strftime('%Y-%m-%d'),
                'expected_completion_date': (order.created_at + timedelta(days=7)).strftime('%Y-%m-%d'),
                'duration_days': 7,
                'status': 'in_progress'
            }
            orders_list.append(order_info)
        
        return jsonify({'success': True, 'orders': orders_list}), 200
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/workers/<int:worker_id>/salary-info')
def api_worker_salary(worker_id):
    """API لجلب معلومات الراتب للعامل"""
    if request.headers.get('Authorization') != 'Bearer worker_app':
        return jsonify({'error': 'غير مصرح'}), 401
    
    try:
        worker = Worker.query.get_or_404(worker_id)
        
        salary_info = {
            'success': True,
            'current_salary': worker.total_salary,
            'base_salary': worker.monthly_salary,
            'bonuses': worker.incentives + worker.outside_work_bonus,
            'deductions': worker.advances,
            'net_salary': worker.total_salary,
            'work_days': 22,
            'absence_days': worker.absences,
            'vacation_days': 0,
            'next_salary_date': (datetime.now(timezone.utc) + timedelta(days=5)).strftime('%Y-%m-%d')
        }
        
        return jsonify(salary_info), 200
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/orders/<int:order_id>/status', methods=['PUT'])
def api_update_order_status(order_id):
    """API لتحديث حالة الطلبية من قبل العامل"""
    if request.headers.get('Authorization') != 'Bearer worker_app':
        return jsonify({'error': 'غير مصرح'}), 401
    
    try:
        data = request.get_json()
        status = data.get('status')
        worker_id = data.get('worker_id')
        
        order = Order.query.get_or_404(order_id)
        
        # تحديث حالة الطلبية
        if status == 'completed':
            # البحث عن حالة "مكتملة"
            completed_status = Status.query.filter_by(name="مكتملة").first()
            if completed_status:
                order.status_id = completed_status.id
        
        # تسجيل في السجل
        history = OrderHistory(
            order_id=order.id,
            change_type="تحديث حالة من التطبيق",
            details=f"تم تحديث حالة الطلبية إلى {status} بواسطة العامل #{worker_id}"
        )
        db.session.add(history)
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'تم تحديث حالة الطلبية'}), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


# ========================
# 🚀 تشغيل التطبيق
# ========================

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)