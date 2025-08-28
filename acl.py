from functools import wraps
from flask import request, abort
from flask_login import login_required, current_user
from utils import is_super
from extensions import login_manager

def attach_acl(bp, *, read_perm: str | None, write_perm: str | None, public_read: bool = False, exempt_prefixes: list[str] | None = None):
    if getattr(bp, "_acl_attached", False):
        return
    ex = tuple(exempt_prefixes or ())
    @bp.before_request
    def _guard():
        path = request.path or ""
        method = (request.method or "").upper()
        is_read = method in ("GET", "HEAD", "OPTIONS")
        in_ex = any(path.startswith(p) for p in ex)
        if in_ex:
            return
        if is_read and public_read:
            return
        if not getattr(current_user, "is_authenticated", False):
            if path.startswith("/api/") or request.accept_mimetypes.best == "application/json":
                abort(401)
            return login_manager.unauthorized()
        if is_super():
            return
        if is_read:
            if read_perm and not current_user.has_permission(read_perm):
                abort(403)
        else:
            need = write_perm or read_perm
            if need and not current_user.has_permission(need):
                abort(403)
    bp._acl_attached = True

def require_perm(perm: str):
    def deco(f):
        @wraps(f)
        @login_required
        def _w(*a, **kw):
            if is_super() or current_user.has_permission(perm):
                return f(*a, **kw)
            abort(403)
        return _w
    return deco
