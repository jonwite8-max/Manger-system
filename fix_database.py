# fix_database.py
from app import app, db
from models import Product

with app.app_context():
    try:
        print("🔄 إصلاح قاعدة البيانات...")
        
        # إسقاط الجدول القديم وإعادة إنشائه
        db.drop_all()
        db.create_all()
        
        print("✅ تم إصلاح قاعدة البيانات بنجاح")
        
    except Exception as e:
        print(f"❌ خطأ في إصلاح قاعدة البيانات: {e}")