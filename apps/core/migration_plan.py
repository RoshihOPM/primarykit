"""Print Django app labels that require client-owned migration generation."""

from apps.core.module_registry import migration_apps


if __name__ == "__main__":
    print(" ".join(migration_apps()))
