"""Versioned source-only project profiles; never runtime dependencies."""

PRESETS = {
    "minimal": {
        "description": "JWT, accounts, notifications and health checks only",
        "apps": (),
    },
    "crm": {
        "description": "Company and branch access, audit, files, metrics and background jobs",
        "apps": (
            "organizations",
            "rbac",
            "audit",
            "storage",
            "statistics",
            "tasks",
            "outbox",
            "kanban",
            "leads",
        ),
    },
    "marketplace": {
        "description": "Classifieds scaffolding; client owns listing, chat and commerce models",
        "apps": (
            "organizations",
            "storage",
            "listings",
            "search",
            "audit",
            "statistics",
            "tasks",
            "outbox",
            "webhooks",
            "rate_limit",
        ),
    },
    "saas": {
        "description": "Tenant baseline with audit, storage, quotas left to each business",
        "apps": (
            "organizations",
            "rbac",
            "audit",
            "storage",
            "statistics",
            "api_keys",
            "rate_limit",
        ),
    },
    "commerce": {
        "description": "Personal demo commerce only: no verified payments or automatic stock deduction",
        "apps": ("catalog", "inventory", "orders", "sales", "payments", "audit", "statistics"),
    },
}
