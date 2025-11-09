# worker_history.py
from models import db, WorkerHistory
from datetime import datetime

class WorkerHistoryManager:
    @staticmethod
    def add_record(worker_id, change_type, details, amount=0.0):
        """إضافة سجل جديد للعامل"""
        try:
            history = WorkerHistory(
                worker_id=worker_id,
                change_type=change_type,
                details=details,
                amount=amount,
                timestamp=datetime.utcnow()
            )
            db.session.add(history)
            return True
        except Exception as e:
            print(f"Error adding history: {e}")
            return False