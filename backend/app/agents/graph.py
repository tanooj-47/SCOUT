"""
backend/app/agents/graph.py
LangGraph StateGraph definition, conditional edges, and compilation for disaster response workflows.
Milestone 12.4: Integrates Intelligence, Weather, Geospatial, Risk Assessment, Response Planning, and Human Review Gate.
"""

import logging
from typing import Any, Dict, Optional
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.agents.nodes.coordinator import coordinator_agent_node
from app.agents.nodes.geospatial import geospatial_agent_node
from app.agents.nodes.human_approval import human_review_gate_node
from app.agents.nodes.intelligence import intelligence_agent_node
from app.agents.nodes.response_planning import response_planning_agent_node
from app.agents.nodes.risk_assessment import risk_assessment_agent_node
from app.agents.nodes.validation import validate_request_node
from app.agents.nodes.weather import weather_agent_node
from app.agents.schemas import WorkflowStatus, WorkflowStage
from app.agents.state import DisasterWorkflowState

logger = logging.getLogger(__name__)


def route_after_validation(state: DisasterWorkflowState) -> str:
    """
    Evaluates state after request validation to determine graph path.
    If validation fails or encounters errors, halts immediately by routing to END.
    If valid, routes to 'intelligence_agent'.
    """
    if state.get("status") == WorkflowStatus.FAILED.value or state.get("errors"):
        logger.info("Validation routing: errors detected; routing workflow %s to END.", state.get("workflow_id"))
        return END

    logger.info("Validation routing: request %s verified; routing to intelligence_agent.", state.get("workflow_id"))
    return "intelligence_agent"


def create_disaster_workflow_graph(
    include_agents: bool = True,
    include_risk_agent: bool = True,
    include_planning_agent: bool = True,
    include_coordinator: bool = True,
) -> StateGraph:
    """
    Assembles the LangGraph StateGraph definition for the disaster response workflow.
    Configured with DisasterWorkflowState and explicit node bindings.
    When include_agents=True, include_risk_agent=True, include_planning_agent=True, and include_coordinator=True (default), includes:
      - validate_request
      - intelligence_agent
      - weather_agent
      - geospatial_agent
      - risk_assessment_agent
      - response_planning_agent
      - human_review_gate
      - coordinator_agent
    When include_coordinator=False, builds through Human Review Gate (M12.4 boundary).
    When include_planning_agent=False, builds through Risk Assessment Agent (M12.3 boundary).
    When include_risk_agent=False, builds a perception-only graph (M12.2 boundary).
    When include_agents=False, builds a validation-only graph for foundation-level testing.
    """
    builder = StateGraph(DisasterWorkflowState)

    # 1. Register Validation Node
    builder.add_node("validate_request", validate_request_node)
    builder.add_edge(START, "validate_request")

    if not include_agents:
        def route_validation_only(state: DisasterWorkflowState) -> str:
            return END

        builder.add_conditional_edges(
            "validate_request",
            route_validation_only,
            {END: END},
        )
        return builder

    # 2. Register Perception Agents (M12.2)
    builder.add_node("intelligence_agent", intelligence_agent_node)
    builder.add_node("weather_agent", weather_agent_node)
    builder.add_node("geospatial_agent", geospatial_agent_node)

    # 3. Conditional Routing after Validation
    builder.add_conditional_edges(
        "validate_request",
        route_after_validation,
        {
            "intelligence_agent": "intelligence_agent",
            END: END,
        },
    )

    # 4. Perception Sequence: Intelligence -> Weather -> Geospatial
    builder.add_edge("intelligence_agent", "weather_agent")
    builder.add_edge("weather_agent", "geospatial_agent")

    if not include_risk_agent:
        builder.add_edge("geospatial_agent", END)
        return builder

    # 5. Register Risk Assessment Agent (M12.3)
    builder.add_node("risk_assessment_agent", risk_assessment_agent_node)
    builder.add_edge("geospatial_agent", "risk_assessment_agent")

    if not include_planning_agent:
        builder.add_edge("risk_assessment_agent", END)
        return builder

    # 6. Register Response Planning Agent & Human Review Gate (M12.4)
    builder.add_node("response_planning_agent", response_planning_agent_node)
    builder.add_node("human_review_gate", human_review_gate_node)
    builder.add_edge("risk_assessment_agent", "response_planning_agent")
    builder.add_edge("response_planning_agent", "human_review_gate")

    if not include_coordinator:
        builder.add_edge("human_review_gate", END)
        return builder

    # 7. Register Coordinator Agent (M12.5)
    builder.add_node("coordinator_agent", coordinator_agent_node)
    builder.add_edge("human_review_gate", "coordinator_agent")
    builder.add_edge("coordinator_agent", END)

    return builder


def compile_workflow_graph(
    checkpointer: Optional[Any] = None,
    include_agents: bool = True,
    include_risk_agent: bool = True,
    include_planning_agent: bool = True,
    include_coordinator: bool = True,
) -> CompiledStateGraph:
    """
    Compiles the disaster workflow StateGraph into an executable graph application.
    Supports optional LangGraph checkpointer for state persistence.
    """
    builder = create_disaster_workflow_graph(
        include_agents=include_agents,
        include_risk_agent=include_risk_agent,
        include_planning_agent=include_planning_agent,
        include_coordinator=include_coordinator,
    )
    return builder.compile(checkpointer=checkpointer)
