from rest_framework.permissions import BasePermission, SAFE_METHODS


def _get_role(user) -> str | None:
    """Безопасно возвращает роль пользователя из профиля."""
    if not user or not user.is_authenticated:
        return None
    try:
        return user.profile.role
    except AttributeError:
        return None


class IsAdminRole(BasePermission):
    """Доступ только для администраторов."""

    message = "Доступ разрешён только администраторам"

    def has_permission(self, request, view) -> bool:
        return _get_role(request.user) == "admin"


class IsManagerOrAdmin(BasePermission):
    """Доступ для менеджеров и администраторов."""

    message = "Доступ разрешён только менеджерам и администраторам"

    def has_permission(self, request, view) -> bool:
        return _get_role(request.user) in ("admin", "manager")


class IsOwnerOrManagerAdmin(BasePermission):
    """Доступ для владельца объекта, менеджера или администратора."""

    message = "Доступ разрешён только владельцу, менеджеру или администратору"

    def has_object_permission(self, request, view, obj) -> bool:
        role = _get_role(request.user)
        if role in ("admin", "manager"):
            return True
        if hasattr(obj, "user"):
            return obj.user == request.user
        return False


class ReadOnlyOrManagerAdmin(BasePermission):
    """Чтение для всех, запись только для менеджеров/администраторов."""

    def has_permission(self, request, view) -> bool:
        if request.method in SAFE_METHODS:
            return True
        return _get_role(request.user) in ("admin", "manager")
