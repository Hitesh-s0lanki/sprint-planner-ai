from typing import Optional, List
from pydantic import BaseModel

class TeamMember(BaseModel):
    name: Optional[str] = None
    profession: Optional[str] = None
    role: Optional[str] = None
    description: Optional[str] = None
    domain_expertise: Optional[str] = None

class PreferredTechStack(BaseModel):
    frontend: Optional[str] = None
    backend: Optional[str] = None
    database: Optional[str] = None
    ai_models: Optional[str] = None
    cloud: Optional[str] = None

class IdeaState(BaseModel):
    # required
    session_id: str

    # stage_1_idea_summary (flattened, no "stage" prefix)
    idea_title: Optional[str] = None
    idea_summary_short: Optional[str] = None
    problem_statement: Optional[str] = None
    target_user: Optional[str] = None

    # stage_2_user_profile
    team: Optional[List[TeamMember]] = None
    execution_capacity: Optional[str] = None

    # stage_3_deep_idea_details
    idea_long_description: Optional[str] = None
    core_features_must_have: Optional[List[str]] = None
    optional_features_good_to_have: Optional[List[str]] = None
    is_product_needed: Optional[str] = None
    product_similar_to: Optional[str] = None

    # stage_4_market_competition
    market_size_assumption: Optional[str] = None
    primary_competitors: Optional[List[str]] = None
    competitive_advantage: Optional[str] = None
    user_pain_points_from_research: Optional[List[str]] = None
    validation_status: Optional[str] = None

    # stage_5_technology_implementation
    tech_required: Optional[List[str]] = None
    preferred_tech_stack: Optional[PreferredTechStack] = None
    integrations_needed: Optional[List[str]] = None
    data_needed_for_MVP: Optional[List[str]] = None
    constraints: Optional[List[str]] = None

    # stage_6_business_goals
    primary_goal_for_4_weeks: Optional[str] = None
    monetization_model: Optional[str] = None
    launch_channel: Optional[List[str]] = None
    KPI_for_success: Optional[List[str]] = None

    # stage_7_execution_preferences
    working_style: Optional[str] = None
    preferred_sprint_format: Optional[str] = None
    need_AI_assistance_for: Optional[List[str]] = None
    risk_tolerance: Optional[str] = None

    # stage_8_constraints
    budget_range: Optional[str] = None
    tools_they_already_use: Optional[List[str]] = None
    time_constraints: Optional[str] = None
    assets_available: Optional[List[str]] = None
