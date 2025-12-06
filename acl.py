# acl.py - Access Control Lists
# Location: /garage_manager/acl.py
# Description: Access control and permission management

from functools import wraps
from flask import request, abort
from flask_login import login_required, current_user
import utils
from extensions import login_manager

def attach_acl(
    bp,
    *,
    read_perm: str | None,
    write_perm: str | None,
    public_read: bool = False,
    exempt_prefixes: list[str] | None = None,
):
    if getattr(bp, "_acl_attached", False):
        return

    ex_list = list(exempt_prefixes or [])
    if "/static/" not in ex_list:
        ex_list.append("/static/")
    ex = tuple(ex_list)

    @bp.before_request
    def _guard():
        path = request.path or ""
        method = (request.method or "").upper()

        if method == "OPTIONS":
            return

        is_read = method in ("GET", "HEAD")
        if any(path.startswith(p) for p in ex):
            return
        if is_read and public_read:
            return

        if not getattr(current_user, "is_authenticated", False):
            if path.startswith("/api/") or request.accept_mimetypes.best == "application/json":
                abort(401)
            return login_manager.unauthorized()

        if utils.is_super():
            return

        if is_read:
            # Allow logged-in customers to read their own account statement
            try:
                if hasattr(current_user, "__tablename__") and current_user.__tablename__ == "customers":
                    if path.startswith("/customers/") and path.endswith("/account_statement"):
                        parts = path.split("/")
                        if len(parts) >= 4:
                            try:
                                cid = int(parts[2])
                            except Exception:
                                cid = None
                            if cid and getattr(current_user, "id", None) == cid:
                                return
                            abort(403)
            except Exception:
                pass
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
            if utils.is_super() or current_user.has_permission(perm):
                return f(*a, **kw)
            abort(403)
        return _w
    return deco
