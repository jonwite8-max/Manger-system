# update_database.py
from app import app, db
from models import Order

with app.app_context():
    try:
        # محاولة إضافة العمود الجديد
        db.engine.execute('ALTER TABLE "order" ADD COLUMN is_paid BOOLEAN DEFAULT FALSE')
        print("✅ تم إضافة العمود is_paid بنجاح")
        
        # تحديث القيم الحالية بناءً على paid و total
        orders = Order.query.all()
        for order in orders:
            order.is_paid = (order.paid >= order.total)
        
        db.session.commit()
        print("✅ تم تحديث بيانات الطلبيات الحالية")
        
    except Exception as e:
        print(f"❌ خطأ في تحديث قاعدة البيانات: {e}")
        # إذا فشل التحديث، حاول إعادة إنشاء الجداول
        try:
            db.drop_all()
            db.create_all()
            print("✅ تم إعادة إنشاء الجداول بنجاح")
        except Exception as e2:
            print(f"❌ خطأ في إعادة إنشاء الجداول: {e2}")