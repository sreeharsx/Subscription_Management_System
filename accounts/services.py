from .models import AuditLog


def log_activity(actor, action: str, obj=None, details: str = ''):
    """
    Record an activity/audit event.
    Safe helper: catches exceptions so audit logging never fails the main transaction.
    """
    try:
        model_name = obj.__class__.__name__ if obj else "System"
        object_id = str(getattr(obj, 'pk', '')) if obj else ""
        object_repr = str(obj) if obj else ""
        return AuditLog.objects.create(
            actor=actor if actor and actor.is_authenticated else None,
            action=action,
            model_name=model_name,
            object_id=object_id,
            object_repr=object_repr,
            details=details,
        )
    except Exception:
        return None

