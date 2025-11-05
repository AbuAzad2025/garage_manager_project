import re

with open('models.py', 'r', encoding='utf-8') as f:
    content = f.read()

print("Applying improvements to models.py...")

content = content.replace(
    '    def to_dict(self):\n        return {"id": self.id,"service_number": self.service_number,"status": getattr(self.status, "value", self.status),"priority": getattr(self.priority, "value", self.priority),"customer_id": self.customer_id,"mechanic_id": self.mechanic_id,"vehicle_type_id": self.vehicle_type_id,"problem_description": self.problem_description,"diagnosis": self.diagnosis,"resolution": self.resolution,"notes": self.notes,"received_at": self.received_at.isoformat() if self.received_at else None,"started_at": self.started_at.isoformat() if self.started_at else None,"expected_delivery": self.expected_delivery.isoformat() if self.expected_delivery else None,"completed_at": self.completed_at.isoformat() if self.completed_at else None,"currency": self.currency,"tax_rate": float(self.tax_rate or 0),"discount_total": float(self.discount_total or 0),"parts_total": float(self.parts_total or 0),"labor_total": float(self.labor_total or 0),"total_amount": float(self.total_amount or 0),"subtotal": float(self.subtotal),"tax_amount": float(self.tax_amount),"total": float(self.total),"total_paid": float(self.total_paid),"balance_due": float(self.balance_due),"warranty_days": self.warranty_days,"warranty_until": self.warranty_until.isoformat() if self.warranty_until else None,"refunded_total": float(self.refunded_total or 0),"refundable_amount": float(self.refundable_amount),"refund_of_id": self.refund_of_id,"idempotency_key": self.idempotency_key,"cancelled_at": self.cancelled_at.isoformat() if self.cancelled_at else None,"cancelled_by": self.cancelled_by,"cancel_reason": self.cancel_reason,"parts": [p.to_dict() for p in self.parts] if self.parts else [],"tasks": [t.to_dict() for t in self.tasks] if self.tasks else []}',
    '''    def to_dict(self):
        return {
            "id": self.id,
            "service_number": self.service_number,
            "status": getattr(self.status, "value", self.status),
            "priority": getattr(self.priority, "value", self.priority),
            "customer_id": self.customer_id,
            "mechanic_id": self.mechanic_id,
            "vehicle_type_id": self.vehicle_type_id,
            "problem_description": self.problem_description,
            "diagnosis": self.diagnosis,
            "resolution": self.resolution,
            "notes": self.notes,
            "received_at": self.received_at.isoformat() if self.received_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "expected_delivery": self.expected_delivery.isoformat() if self.expected_delivery else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "currency": self.currency,
            "tax_rate": float(self.tax_rate or 0),
            "discount_total": float(self.discount_total or 0),
            "parts_total": float(self.parts_total or 0),
            "labor_total": float(self.labor_total or 0),
            "total_amount": float(self.total_amount or 0),
            "subtotal": float(self.subtotal),
            "tax_amount": float(self.tax_amount),
            "total": float(self.total),
            "total_paid": float(self.total_paid),
            "balance_due": float(self.balance_due),
            "warranty_days": self.warranty_days,
            "warranty_until": self.warranty_until.isoformat() if self.warranty_until else None,
            "refunded_total": float(self.refunded_total or 0),
            "refundable_amount": float(self.refundable_amount),
            "refund_of_id": self.refund_of_id,
            "idempotency_key": self.idempotency_key,
            "cancelled_at": self.cancelled_at.isoformat() if self.cancelled_at else None,
            "cancelled_by": self.cancelled_by,
            "cancel_reason": self.cancel_reason,
            "parts": [p.to_dict() for p in self.parts] if self.parts else [],
            "tasks": [t.to_dict() for t in self.tasks] if self.tasks else []
        }'''
)

print("✓ Fixed long line (9001)")

with open('models.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("✓ Done! File updated.")

