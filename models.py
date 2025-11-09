# ====== models.py ======
from datetime import datetime, timezone, timedelta
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

# دالة مساعدة للوقت الحالي
def now_utc():
    return datetime.now(timezone.utc)

# ========================
# 🏷️ قسم الحالات والطلبيات
# ========================

class Status(db.Model):
    __tablename__ = 'status'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(60), nullable=False)
    color = db.Column(db.String(20), default="#FFC107")

    def __repr__(self):
        return f"<Status {self.name}>"

class Order(db.Model):
    __tablename__ = 'order'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    wilaya = db.Column(db.String(50))
    product = db.Column(db.String(200))
    paid = db.Column(db.Float, default=0.0)
    total = db.Column(db.Float, default=0.0)
    note = db.Column(db.Text, default="")
    status_id = db.Column(db.Integer, db.ForeignKey('status.id'), nullable=True)
    status = db.relationship('Status', backref='orders')
    created_at = db.Column(db.DateTime, default=now_utc)
    is_paid = db.Column(db.Boolean, default=False)

    # الحقول الجديدة للنظام المحسن
    assigned_worker_id = db.Column(db.Integer, db.ForeignKey('worker.id'))
    production_details = db.Column(db.Text)
    expected_delivery_date = db.Column(db.Date)
    actual_delivery_date = db.Column(db.Date)
    is_travel_assignment = db.Column(db.Boolean, default=False)
    travel_worker_id = db.Column(db.Integer, db.ForeignKey('worker.id'))
    media_attachments = db.Column(db.JSON)

    # العلاقات الجديدة
    assigned_worker = db.relationship('Worker', foreign_keys=[assigned_worker_id], backref='assigned_orders')
    travel_worker = db.relationship('Worker', foreign_keys=[travel_worker_id], backref='travel_assignments')

    phones = db.relationship('PhoneNumber', backref='order', cascade="all, delete-orphan", lazy=True)
    history = db.relationship('OrderHistory', backref='order', cascade="all, delete-orphan", lazy=True)

    @property
    def remaining(self):
        return round((self.total or 0.0) - (self.paid or 0.0), 2)

class PhoneNumber(db.Model):
    __tablename__ = 'phone_number'
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'))
    number = db.Column(db.String(40), nullable=False)
    is_primary = db.Column(db.Boolean, default=False)

class OrderHistory(db.Model):
    __tablename__ = 'order_history'
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'))
    change_type = db.Column(db.String(120))
    details = db.Column(db.Text)
    timestamp = db.Column(db.DateTime, default=now_utc)

# ========================
# 👥 قسم العمال
# ========================

class WorkerHistory(db.Model):
    __tablename__ = 'worker_history'
    id = db.Column(db.Integer, primary_key=True)
    worker_id = db.Column(db.Integer, db.ForeignKey('worker.id'))
    change_type = db.Column(db.String(120))
    details = db.Column(db.Text)
    amount = db.Column(db.Float, default=0.0)
    timestamp = db.Column(db.DateTime, default=now_utc)
    worker = db.relationship('Worker', backref='history_records')

class Worker(db.Model):
    __tablename__ = 'worker'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(40), nullable=False)
    address = db.Column(db.String(200))
    id_card = db.Column(db.String(50), unique=False, nullable=True)
    start_date = db.Column(db.Date, nullable=False)
    monthly_salary = db.Column(db.Float, default=0.0)
    absences = db.Column(db.Float, default=0.0)
    outside_work_days = db.Column(db.Integer, default=0)
    outside_work_bonus = db.Column(db.Float, default=0.0)
    advances = db.Column(db.Float, default=0.0)
    incentives = db.Column(db.Float, default=0.0)
    late_hours = db.Column(db.Float, default=0.0)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=now_utc)

    @property
    def total_salary(self):
        """حساب الراتب الإجمالي المستحق بدقة"""
        try:
            today = now_utc().date()
            days_since_start = (today - self.start_date).days
            days_worked = max(0, days_since_start)
            
            daily_salary = self.monthly_salary / 30.0
            base_salary = days_worked * daily_salary
            
            absence_deduction = self.absences * daily_salary
            late_deduction = self.late_hours * 500
            
            total = (base_salary + 
                    self.outside_work_bonus + 
                    self.incentives - 
                    self.advances - 
                    absence_deduction - 
                    late_deduction)
            
            return max(0, round(total, 2))
        except:
            return 0.0

class WorkerAttendance(db.Model):
    __tablename__ = 'worker_attendance'
    __table_args__ = {'extend_existing': True}
    id = db.Column(db.Integer, primary_key=True)
    worker_id = db.Column(db.Integer, db.ForeignKey('worker.id'))
    date = db.Column(db.Date, default=lambda: now_utc().date())
    check_in_morning = db.Column(db.DateTime)
    check_out_morning = db.Column(db.DateTime)
    check_in_afternoon = db.Column(db.DateTime)
    check_out_afternoon = db.Column(db.DateTime)
    total_hours = db.Column(db.Float, default=0.0)
    absence_hours = db.Column(db.Float, default=0.0)
    location_verified = db.Column(db.Boolean, default=False)
    notes = db.Column(db.Text)
    
    created_at = db.Column(db.DateTime, default=now_utc)
    
    worker = db.relationship('Worker', backref='attendance_records')

# ========================
# 💰 قسم المصاريف والمشتريات
# ========================

class ExpenseCategory(db.Model):
    __tablename__ = 'expense_category'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    color = db.Column(db.String(7), default='#3B82F6')
    icon = db.Column(db.String(50), default='📦')
    created_at = db.Column(db.DateTime, default=now_utc)

class Expense(db.Model):
    __tablename__ = 'expense'
    id = db.Column(db.Integer, primary_key=True)
    category_id = db.Column(db.Integer, db.ForeignKey('expense_category.id'))
    description = db.Column(db.String(200), nullable=False)
    amount = db.Column(db.Float, default=0.0)
    quantity = db.Column(db.Integer, default=1)
    unit_price = db.Column(db.Float, default=0.0)
    total_amount = db.Column(db.Float, default=0.0)
    supplier_id = db.Column(db.Integer, db.ForeignKey('supplier.id'))
    purchased_by = db.Column(db.String(50), default='owner')
    recorded_by = db.Column(db.String(50), nullable=False)
    purchase_date = db.Column(db.Date, default=lambda: now_utc().date())
    payment_status = db.Column(db.String(20), default='paid')
    payment_method = db.Column(db.String(20), default='cash')
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=now_utc)
    
    category = db.relationship('ExpenseCategory', backref='expenses')
    supplier = db.relationship('Supplier', backref='expenses')
    
    @property
    def calculated_total(self):
        return self.quantity * self.unit_price

class ProductPriceHistory(db.Model):
    __tablename__ = 'product_price_history'
    id = db.Column(db.Integer, primary_key=True)
    product_name = db.Column(db.String(200), nullable=False)
    supplier_id = db.Column(db.Integer, db.ForeignKey('supplier.id'))
    price = db.Column(db.Float, default=0.0)
    purchase_date = db.Column(db.Date, default=lambda: now_utc().date())
    recorded_by = db.Column(db.String(50), nullable=False)
    created_at = db.Column(db.DateTime, default=now_utc)
    
    supplier = db.relationship('Supplier', backref='price_history')

# ========================
# 🏢 قسم الموردين
# ========================

class Supplier(db.Model):
    __tablename__ = 'supplier'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(40))
    address = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=now_utc)

# ========================
# 📦 قسم المنتجات
# ========================

class Product(db.Model):
    __tablename__ = 'product'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey('expense_category.id'))
    created_at = db.Column(db.DateTime, default=now_utc)
    
    category = db.relationship('ExpenseCategory', backref='products')

# ========================
# 🛒 قسم المشتريات القديم (للتوافق)
# ========================

class Purchase(db.Model):
    __tablename__ = 'purchase'
    id = db.Column(db.Integer, primary_key=True)
    supplier_id = db.Column(db.Integer, db.ForeignKey('supplier.id'))
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'))
    price = db.Column(db.Float, default=0.0)
    quantity = db.Column(db.Integer, default=1)
    total_price = db.Column(db.Float, default=0.0)
    purchase_date = db.Column(db.Date, default=lambda: now_utc().date())
    status = db.Column(db.String(20), default="unpaid")
    type = db.Column(db.String(20), default="fixed")
    created_at = db.Column(db.DateTime, default=now_utc)

    supplier = db.relationship('Supplier', backref='purchases')
    product = db.relationship('Product', backref='purchases')

# ========================
# 🚚 قسم النقل المحسّن
# ========================

class TransportCategory(db.Model):
    __tablename__ = 'transport_category'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    color = db.Column(db.String(7), default='#3B82F6')
    icon = db.Column(db.String(50), default='🚗')
    created_at = db.Column(db.DateTime, default=now_utc)

class TransportSubType(db.Model):
    __tablename__ = 'transport_sub_type'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey('transport_category.id'))
    created_at = db.Column(db.DateTime, default=now_utc)
    
    category = db.relationship('TransportCategory', backref='sub_types')

class TransportReceipt(db.Model):
    __tablename__ = 'transport_receipt'
    id = db.Column(db.Integer, primary_key=True)
    transport_id = db.Column(db.Integer, db.ForeignKey('transport.id'))
    filename = db.Column(db.String(255), nullable=False)
    original_filename = db.Column(db.String(255), nullable=False)
    file_size = db.Column(db.Integer)
    mime_type = db.Column(db.String(100))
    image_data = db.Column(db.LargeBinary)
    captured_at = db.Column(db.DateTime, default=now_utc)
    captured_by = db.Column(db.String(50), nullable=False)
    
    transport = db.relationship('Transport', backref='receipts')

class Transport(db.Model):
    __tablename__ = 'transport'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(40))
    address = db.Column(db.String(200))
    transport_amount = db.Column(db.Float, default=0.0)
    destination = db.Column(db.String(200))
    paid_amount = db.Column(db.Float, default=0.0)
    type = db.Column(db.String(20), default="inside")
    
    # الحقول الجديدة للنظام المحسّن
    category_id = db.Column(db.Integer, db.ForeignKey('transport_category.id'))
    sub_type_id = db.Column(db.Integer, db.ForeignKey('transport_sub_type.id'))
    transport_method = db.Column(db.String(50), default='car')
    purpose = db.Column(db.String(200))
    distance = db.Column(db.Float, default=0.0)
    notes = db.Column(db.Text)
    is_quick = db.Column(db.Boolean, default=False)
    recorded_by = db.Column(db.String(50), nullable=False)
    transport_date = db.Column(db.Date, default=lambda: now_utc().date())
    created_at = db.Column(db.DateTime, default=now_utc)

    category = db.relationship('TransportCategory', backref='transports')
    sub_type = db.relationship('TransportSubType', backref='transports')

    @property
    def remaining_amount(self):
        return round(self.transport_amount - self.paid_amount, 2)

# ========================
# 💸 قسم الديون المحسّن
# ========================

class Debt(db.Model):
    __tablename__ = 'debt'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(40))
    address = db.Column(db.String(200))
    debt_amount = db.Column(db.Float, default=0.0)
    paid_amount = db.Column(db.Float, default=0.0)
    start_date = db.Column(db.Date, default=lambda: now_utc().date())
    payment_date = db.Column(db.Date, nullable=True)
    status = db.Column(db.String(20), default="unpaid")
    created_at = db.Column(db.DateTime, default=now_utc)
    
    # الحقول الجديدة للنظام الذكي
    source_type = db.Column(db.String(50))  # 'expense', 'purchase', 'transport', 'manual'
    source_id = db.Column(db.Integer)  # معرف المصدر (expense_id, purchase_id, transport_id)
    description = db.Column(db.Text)  # وصف تفصيلي للدين
    recorded_by = db.Column(db.String(50))  # المستخدم الذي سجل الدين

    @property
    def remaining_amount(self):
        return round(self.debt_amount - self.paid_amount, 2)
    
    @property
    def source_info(self):
        """معلومات المصدر للعرض في الواجهة"""
        if self.source_type == 'expense':
            return f"مصروف - {self.description}"
        elif self.source_type == 'purchase':
            return f"مشتريات - {self.description}"
        elif self.source_type == 'transport':
            return f"نقل - {self.description}"
        else:
            return f"دين يدوي - {self.description}"

# ========================
# 👤 قسم المستخدمين
# ========================

class User(db.Model):
    __tablename__ = 'app_user'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=True)
    password = db.Column(db.String(200), nullable=False)
    full_name = db.Column(db.String(100))
    phone = db.Column(db.String(20))
    role = db.Column(db.String(20), default='user')
    permissions = db.Column(db.JSON, default=list)
    is_active = db.Column(db.Boolean, default=True)
    last_login = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=now_utc)

# ========================
# ⚙️ قسم الإعدادات
# ========================

class SystemSettings(db.Model):
    __tablename__ = 'system_settings'
    id = db.Column(db.Integer, primary_key=True)
    company_name = db.Column(db.String(100), default='SOFAZI')
    logo = db.Column(db.String(200))
    currency = db.Column(db.String(10), default='DZD')
    language = db.Column(db.String(10), default='ar')
    theme = db.Column(db.String(20), default='light')
    primary_color = db.Column(db.String(7), default='#3B82F6')
    rows_per_page = db.Column(db.Integer, default=25)
    compact_mode = db.Column(db.Boolean, default=False)
    two_factor = db.Column(db.Boolean, default=False)
    activity_logging = db.Column(db.Boolean, default=True)
    session_timeout = db.Column(db.Integer, default=30)
    password_strength = db.Column(db.String(20), default='medium')
    email_notifications = db.Column(db.Boolean, default=True)
    payment_notifications = db.Column(db.Boolean, default=True)
    inventory_notifications = db.Column(db.Boolean, default=True)
    notification_time = db.Column(db.String(20), default='instant')
    updated_at = db.Column(db.DateTime, default=now_utc, onupdate=now_utc)

# ========================
# 📸 قسم فواتير المصاريف
# ========================

class ExpenseReceipt(db.Model):
    __tablename__ = 'expense_receipt'
    id = db.Column(db.Integer, primary_key=True)
    expense_id = db.Column(db.Integer, db.ForeignKey('expense.id'))
    filename = db.Column(db.String(255), nullable=False)
    original_filename = db.Column(db.String(255), nullable=False)
    file_path = db.Column(db.String(500))
    file_size = db.Column(db.Integer)  # حجم الملف بالبايت
    mime_type = db.Column(db.String(100))
    image_data = db.Column(db.LargeBinary)  # تخزين الصورة كبيانات ثنائية
    captured_at = db.Column(db.DateTime, default=now_utc)
    captured_by = db.Column(db.String(50), nullable=False)
    
    expense = db.relationship('Expense', backref='receipts')

# ========================
# 🔔 نظام الإشعارات المحسن
# ========================

class AdminNotification(db.Model):
    __tablename__ = 'admin_notification'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('app_user.id'))
    title = db.Column(db.String(200), nullable=False)
    message = db.Column(db.Text, nullable=False)
    notification_type = db.Column(db.String(50))  # order, payment, maintenance, debt, salary
    priority = db.Column(db.String(20), default='normal')  # low, normal, high, urgent
    is_read = db.Column(db.Boolean, default=False)
    related_entity_type = db.Column(db.String(50))  # order, worker, debt, expense
    related_entity_id = db.Column(db.Integer)
    sound = db.Column(db.String(100))  # اسم الصوت للإشعار
    
    created_at = db.Column(db.DateTime, default=now_utc)
    user = db.relationship('User', backref='notifications')

# ========================
# 🤖 نظام الذكاء الاصطناعي
# ========================

class AIRecommendation(db.Model):
    __tablename__ = 'ai_recommendation'
    id = db.Column(db.Integer, primary_key=True)
    analysis_type = db.Column(db.String(100))  # orders, workers, expenses, profits
    insight = db.Column(db.Text)
    recommendation = db.Column(db.Text)
    confidence_score = db.Column(db.Float)
    impact_level = db.Column(db.String(20))  # low, medium, high
    is_applied = db.Column(db.Boolean, default=False)
    applied_at = db.Column(db.DateTime)
    
    created_at = db.Column(db.DateTime, default=now_utc)

# ========================
# 📊 نظام الإحصائيات المتقدم
# ========================

class AdvancedStatistic(db.Model):
    __tablename__ = 'advanced_statistic'
    id = db.Column(db.Integer, primary_key=True)
    stat_type = db.Column(db.String(100))  # weekly_profit, monthly_expenses, worker_performance
    period = db.Column(db.String(20))  # week, month, quarter, year
    value = db.Column(db.Float)
    data = db.Column(db.JSON)  # بيانات مفصلة
    trend = db.Column(db.String(20))  # up, down, stable
    trend_percentage = db.Column(db.Float)
    
    calculated_at = db.Column(db.DateTime, default=now_utc)