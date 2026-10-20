from django.apps import AppConfig


class CrmPipelineConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.crm_pipeline"

    def ready(self):
        from apps.deals.services import deal_stage_transitioned
        from apps.kanban.services import before_card_move

        from .handlers import guard_mapped_card_move, project_deal_stage

        deal_stage_transitioned.connect(
            project_deal_stage, dispatch_uid="crm_pipeline.deal_stage", weak=False
        )
        before_card_move.connect(
            guard_mapped_card_move, dispatch_uid="crm_pipeline.card_move", weak=False
        )
