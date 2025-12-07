from pydantic import BaseModel
from typing import Optional, List

# Import nested models from other states
from src.states.team_profile_agent_state import TeamMember

class GlobalIdeaState(BaseModel):
    """
    Global state that aggregates all agent states.
    Contains all fields from all agent states in the workflow.
    """
    
    # ========== Idea Evaluation Agent Fields ==========
    idea_title: Optional[str] = None
    problem_statement: Optional[str] = None
    target_user: Optional[str] = None
    idea_summary_short: Optional[str] = None
    
    # ========== Deep Idea Analysis Agent Fields ==========
    idea_long_description: Optional[str] = None
    core_features_must_have: Optional[List[str]] = None
    optional_features_good_to_have: Optional[List[str]] = None
    is_product_needed: Optional[str] = None
    product_similar_to: Optional[str] = None
    
    # ========== Team Profile Agent Fields ==========
    team: Optional[List[TeamMember]] = None
    execution_capacity: Optional[str] = None
    
    # ========== Business Goals Agent Fields ==========
    primary_goal_for_4_weeks: Optional[str] = None
    monetization_model: Optional[str] = None
    launch_channel: Optional[List[str]] = None
    KPI_for_success: Optional[List[str]] = None
    
    # ========== Market Competition Agent Fields ==========
    market_size_assumption: Optional[str] = None
    primary_competitors: Optional[List[str]] = None
    competitive_advantage: Optional[str] = None
    user_pain_points_from_research: Optional[List[str]] = None
    validation_status: Optional[str] = None
    
    # ========== Constraint Analysis Agent Fields ==========
    budget_range: Optional[str] = None
    tools_they_already_use: Optional[List[str]] = None
    time_constraints: Optional[str] = None
    assets_available: Optional[List[str]] = None
    
    # ========== Execution Preferences Agent Fields ==========
    working_style: Optional[str] = None
    preferred_sprint_format: Optional[str] = None
    need_AI_assistance_for: Optional[List[str]] = None
    risk_tolerance: Optional[str] = None
    
    # ========== Technology Implementation Agent Fields ==========
    tech_required: Optional[List[str]] = None
    preferred_frontend: Optional[str] = None
    preferred_backend: Optional[str] = None
    preferred_database: Optional[str] = None
    ai_models: Optional[str] = None
    cloud: Optional[str] = None
    integrations_needed: Optional[List[str]] = None
    data_needed_for_MVP: Optional[List[str]] = None
    constraints: Optional[List[str]] = None
