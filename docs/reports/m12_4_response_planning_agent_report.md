# SCOUT — Milestone 12.4 Engineering Report
## Response Planning Agent & Human Approval Gate Implementation

**Project:** SCOUT — Multimodal Disaster Intelligence & Response Platform  
**Milestone:** 12.4 (Agent 5: Response Planning Agent & Human Review Gate)  
**Status:** ACCEPTED & FULLY VERIFIED  
**Date:** November 1, 2026  
**Workspace:** `C:\Users\TANOOJ\OneDrive\Desktop\SCOUT`  
**Test Suite Results:** 20/20 M12.4 Tests Passed | 77/77 Multi-Agent Tests Passed | 387/387 Backend Unit Tests Passed  

---

## 1. Executive Summary

Milestone 12.4 introduces the fifth functional agent into SCOUT's LangGraph workflow—the **Response Planning Agent** (`response_planning_agent_node`), coupled with a mandatory **Human Review Gate** (`human_review_gate_node`).

Prior to M12.4, SCOUT's multi-agent workflow executed perception and synthesis: validating requests, interpreting multimodal intelligence (M07/M11), evaluating fire-weather indices (M09), assessing geospatial exposure (M08/M10), and computing a 5-dimensional risk synthesis (M12.3). 

M12.4 bridges analytical assessment to operational response recommendations without sacrificing safety:
- **Strict Decision-Support Advisory:** The Response Planning Agent functions exclusively as an advisory component. It does NOT autonomously dispatch emergency apparatus, call authorities, contact 911, or activate physical infrastructure.
- **Mandatory Human-in-the-Loop Safety Gate:** Generated response plans are initialized strictly with status `PENDING`. Automated workflow progression ceases at `human_review_gate_node`, placing the workflow in a `SUSPENDED_FOR_APPROVAL` state until an authorized human commander records an explicit decision (`APPROVED`, `REJECTED`, or `NEEDS_REVISION`).
- **Deterministic Planning Rule Matrix:** The agent evaluates 7 operational scenarios (Cases A through G) using code-governed, deterministic logic. Zero LLMs, zero vector RAG hallucination, and zero autonomous tool calls are utilized.
- **Suggested Resource Categories:** Resource requirements are formulated as generic operational categories (e.g., `type_3_engine`, `thermal_uas_team`, `structure_protection_unit`), rigorously preventing the fabrication of imaginary emergency organizations, personnel rosters, or live inventories.
- **Uncompromised Regression Integrity:** 20 new comprehensive unit tests were authored and verified, bringing total agent test coverage to 77/77 passing tests and total backend unit test coverage to 387/387 passing tests (100% pass rate).

---

## 2. Response Planning Agent Role & Architecture

### 2.1 Architectural Placement
The Response Planning Agent executes immediately after the Risk Assessment Agent (Agent 4) in the LangGraph StateGraph topology:
```
START -> validate_request -> intelligence_agent -> weather_agent -> geospatial_agent -> risk_assessment_agent -> response_planning_agent -> human_review_gate -> END
```

### 2.2 Functional Responsibilities
- **Upstream Input Ingestion:** Consumes `risk_assessment_output`, `intelligence_output`, `weather_output`, and `geospatial_output` directly from `DisasterWorkflowState`.
- **Missing Risk Guard:** If `risk_assessment_output` is missing or unpopulated, planning immediately halts with a structured `MISSING_RISK_ASSESSMENT` error, preventing hallucinated tactical actions.
- **Evidence-Grounded Recommendation Synthesis:** Produces typed, structured `ActionRecommendation` objects across life-safety advisories, perimeter containment, structure defense triage, water supply reconnaissance, and ground-truth verification.
- **Safety Rule Attachment:** Every tactical recommendation embeds responder safety rules (e.g., LCES enforcement, anchor point verification, refusing indefensible structures without safety zones).
- **Audit Traceability:** Each action includes `evidence_references` documenting exact upstream agent fields and metrics that justify the recommendation.

---

## 3. Human Approval Gate Role & Architecture

### 3.1 The Safety Boundary
In high-stakes disaster intelligence, automated action execution presents unacceptable catastrophic risk. The **Human Review Gate** (`human_review_gate_node`) acts as an immutable safety boundary:
1. **Initial Status is Strictly PENDING:** When the planning agent emits a plan, `human_approval_status` is marked `"pending"`.
2. **Execution Suspension:** The gate receives the state, constructs a typed `HumanApprovalState` (`requires_approval=True`, `approval_status=PENDING`), and transitions workflow lifecycle status to `WorkflowStatus.SUSPENDED_FOR_APPROVAL`.
3. **Execution Halts at Gate:** The graph routes from `human_review_gate` to `END`. Automated progression terminates. The workflow never presumes pre-approval.
4. **State Transitions & Resumption API:**
   Via `DisasterWorkflowService.apply_human_approval()`, human incident commanders record decisions:
   - `APPROVED`: Transitions `human_approval.approval_status` to `APPROVED`, updates plan status, and sets workflow status to `COMPLETED` (or ready for Coordinator Agent reporting in M12.5).
   - `REJECTED`: Transitions `approval_status` to `REJECTED`. Mandates an explicit text justification; cannot be approved without re-planning.
   - `NEEDS_REVISION`: Transitions `approval_status` to `NEEDS_REVISION`. Mandates reviewer commentary and revision guidelines.

---

## 4. The 7 Deterministic Planning Cases

The agent evaluates upstream state using a deterministic decision tree covering 7 mandatory operational scenarios:

| Case | Trigger Condition | Operational Posture & Recommendations Generated | Overall Plan Status |
| :--- | :--- | :--- | :--- |
| **Case A: Confirmed Wildfire** | `incident_status == "CONFIRMED"` | **Life-Safety & Containment:** Issue pre-evacuation alert for proximate settlements; establish defensible anchor points & flank containment; structure defense triage for critical assets; water drafting reconnaissance at hydrologic features. | `complete` (or `partial` if geo unverified) |
| **Case B: Suspected Wildfire** | `incident_status == "SUSPECTED"` | **Verification & Standby:** Dispatch thermal UAS/ground scout to confirm incident coordinates and spread rate; place local apparatus on precautionary standby. Strictly NO unverified mandatory evacuation orders. | `partial` |
| **Case C: Extreme Fire-Weather Danger** | `incident_status in ("NONE", "INSUFFICIENT_EVIDENCE", "UNCONFIRMED")` + FWI $\ge 30.0$ or extreme weather | **Preventative Preparedness:** Enforce red flag restrictions and campfire/ignition bans; pre-position initial attack assets at strategic staging corridors; activate lookout towers and aerial patrol corridors. Explicitly NOT an active suppression response. | `preparedness_only` |
| **Case D: Unverified Geographic Context** | Confirmed incident + `is_geo_verified == False` (0 catalog features) | **GIS Ground-Truthing:** Deploy field GIS team or activate satellite tasking to survey structures. Strictly do NOT invent asset counts; note unverified catalog gaps in `operational_limitations`. | `partial` |
| **Case E: Insufficient Intelligence** | `assessment_status == "insufficient_evidence"` or `incident_status == "INSUFFICIENT_EVIDENCE"` | **Targeted Reconnaissance:** Deploy reconnaissance scout/UAS; enumerate data gaps in `missing_information` and `responder_information_gaps`; omit offensive suppression tactics. | `insufficient_evidence` |
| **Case F: Missing Weather Information** | `weather_output is None` or `missing_parameters` present | **Meteorological Observation:** Omit tactical spread velocity and downwind evacuation arc projections; request IMET spot-weather forecast and deploy portable meteorological kit to staging. | Retains incident status |
| **Case G: Conflicting Evidence** | `conflicting_evidence` non-empty or sensor discordance | **Expedited Conflict Reconciliation:** Dispatch command reconnaissance vehicle/thermal UAS to reconcile contradictory sensor inputs. Priority: `CRITICAL`; reduce recommendation confidence; alert commanders prominently. | `partial` |

---

## 5. Resource Recommendation Approach

To maintain strict operational integrity, resource requirements avoid hallucinated inventories:
- **Suggested Resource Categories:** Recommendations reference standardized equipment and team classifications:
  - `type_3_engine`
  - `wildland_brush_truck`
  - `type_2_hand_crew`
  - `thermal_infrared_uas`
  - `structure_protection_unit`
  - `water_tender`
  - `portable_weather_station`
  - `law_enforcement_traffic_control`
  - `public_alert_system`
- **Zero Inventory Fabrication:** The system does NOT invent unit callsigns (e.g., "Engine 42"), rostered personnel names, or current station availability.
- **Deduplication:** Suggested categories across multiple recommendations are collected and deduplicated into `plan.suggested_resource_categories` preserving order.

---

## 6. Safety Constraints & Responder Protection

Every generated plan enforces wildland firefighting life-safety doctrine:
1. **Global Safety Precautions:** Included in every plan:
   - Adherence to the 10 Standard Firefighting Orders and 18 Watch Out Situations.
   - Mandatory establishment and maintenance of **LCES** (Lookouts, Communications, Escape Routes, Safety Zones) prior to tactical engagement.
   - Continuous situational awareness regarding erratic wind shifts and atmospheric instability.
   - Prohibition against committing personnel into unanchored fire perimeters without verified escape corridors.
2. **Action-Specific Preconditions & Safety Constraints:**
   - Evacuation corridor advisories require verified open egress routes free from fire encroachment.
   - Structure defense requires structure triage (refusing indefensible buildings without adequate safety zones) and engine egress facing outward.
   - Flank containment mandates continuous lookout communication and confirmed anchor points.

---

## 7. Decision-Support-Only Guarantee

SCOUT is engineered with strict non-autonomous boundary enforcement:
- **No Autonomous Dispatch:** The software does not transmit dispatch orders to CAD (Computer-Aided Dispatch) systems.
- **No Autonomous Authority Contact:** The software does not call 911, notify emergency services directly, or send automated SMS broadcasts.
- **No Physical Infrastructure Control:** The software does not trigger physical suppression valves, sirens, or traffic signals.
- **Mandatory Authorization Flag:** Every `ActionRecommendation` has `requires_human_authorization = True`.

---

## 8. LangGraph Graph Topology Updates

The disaster response StateGraph in [`backend/app/agents/graph.py`](../../backend/app/agents/graph.py) was updated:
- Added node: `response_planning_agent` bound to `response_planning_agent_node`.
- Added node: `human_review_gate` bound to `human_review_gate_node`.
- Connected edge: `risk_assessment_agent -> response_planning_agent`.
- Connected edge: `response_planning_agent -> human_review_gate`.
- Connected edge: `human_review_gate -> END`.
- Maintained configuration flags:
  - `include_planning_agent=False`: compiles through M12.3 boundary (`risk_assessment_agent -> END`).
  - `include_risk_agent=False`: compiles through M12.2 perception boundary (`geospatial_agent -> END`).
  - `include_agents=False`: compiles through M12.1 validation boundary (`validate_request -> END`).

---

## 9. State Updates & Schema Evolution

### 9.1 Schemas Updated in `backend/app/agents/schemas.py`
- `HumanApprovalStatus(str, Enum)`: `PENDING`, `APPROVED`, `REJECTED`, `NEEDS_REVISION`.
- `RecommendationPriority(str, Enum)`: `CRITICAL`, `HIGH`, `MEDIUM`, `LOW`.
- `ActionRecommendation`: Full Pydantic model with `intended_objective`, `suggested_responsible_role`, `suggested_resource_categories`, `preconditions`, `safety_constraints`, `evidence_references`, `confidence_description`, `requires_human_authorization=True`.
- `ResponsePlanningAgentOutput`: Full contract with `plan_id`, `incident_status`, `assessed_threat_level`, `overall_plan_status`, `recommendations`, `relevant_geographic_context`, `suggested_resource_categories`, `safety_precautions`, `missing_information`, `operational_limitations`, `human_approval_status`.
- `HumanApprovalState`: Full contract with `approval_id`, `plan_id`, `approval_status`, `requires_approval=True`, `reviewer_id`, `review_timestamp`, `reviewer_comments`, `rejection_or_revision_reason`.
- `WorkflowExecutionResult`: Populated with `response_plan_output` and `human_approval`.

### 9.2 State Updates in `backend/app/agents/state.py`
- `VALID_STAGE_TRANSITIONS`: Allowed transition `WorkflowStage.COMPLETED.value -> WorkflowStage.RESPONSE_PLANNING.value` and `WorkflowStage.HUMAN_REVIEW_GATE.value -> WorkflowStage.COMPLETED.value`.
- Supported state transitions: `RISK_ASSESSMENT -> RESPONSE_PLANNING -> HUMAN_REVIEW_GATE -> COMPLETED`.

---

## 10. Test Suite & Verification Results

A dedicated, comprehensive unit test suite was implemented in [`backend/tests/unit/agents/test_m12_4_response_planning.py`](../../backend/tests/unit/agents/test_m12_4_response_planning.py) covering all 20 required verification points:

| # | Test Function Name | Tested Behavior & Acceptance Criteria | Result |
| :---: | :--- | :--- | :---: |
| 1 | `test_confirmed_wildfire_generates_evidence_grounded_recommendations` | Case A: Confirmed fire generates life-safety, containment, structure triage, water supply recs. | **PASSED** |
| 2 | `test_suspected_wildfire_preserves_suspected_status` | Case B: Suspected status preserved; drone/ground verification recs; zero unverified evacuations. | **PASSED** |
| 3 | `test_extreme_fwi_without_active_fire_generates_preparedness_recommendations` | Case C: FWI=38 without fire produces red flag bans & pre-positioning; `preparedness_only`. | **PASSED** |
| 4 | `test_unverified_geographic_context_does_not_invent_assets` | Case D: Unverified catalog produces GIS ground-truthing recommendation; zero invented structures. | **PASSED** |
| 5 | `test_insufficient_intelligence_produces_limited_recommendations` | Case E: Insufficient intelligence restricts plan strictly to reconnaissance; enumerates gaps. | **PASSED** |
| 6 | `test_missing_weather_handled_explicitly` | Case F: Missing weather omits spread projections; recommends IMET spot forecast & weather station. | **PASSED** |
| 7 | `test_conflicting_evidence_reduces_certainty_and_triggers_verification` | Case G: Conflicting streams trigger CRITICAL reconciliation rec; reduces confidence to LOW. | **PASSED** |
| 8 | `test_recommendations_include_evidence_references` | Every recommendation includes auditable links to upstream agents. | **PASSED** |
| 9 | `test_resource_categories_do_not_imply_actual_inventory` | Resource categories are generic equipment types; zero fabricated unit names or rosters. | **PASSED** |
| 10 | `test_safety_constraints_are_preserved` | LCES, escape routes, and defensible space rules embedded in recommendations. | **PASSED** |
| 11 | `test_unsupported_recommendations_are_not_generated` | Zero 911 calls or automated apparatus dispatches; `requires_human_authorization=True`. | **PASSED** |
| 12 | `test_response_plan_is_initially_pending` | Initial plan `human_approval_status` is strictly `PENDING`. | **PASSED** |
| 13 | `test_approval_cannot_be_assumed` | Workflow halts at `human_review_gate` in `SUSPENDED_FOR_APPROVAL` status. | **PASSED** |
| 14 | `test_rejection_remains_explicit` | Reviewer rejection records reason and does not mark plan approved; missing reason raises error. | **PASSED** |
| 15 | `test_revision_requests_remain_explicit` | Reviewer revision requests record comments; missing reason raises error. | **PASSED** |
| 16 | `test_missing_risk_assessment_prevents_fabricated_planning` | When risk output is None, node fails safely with `MISSING_RISK_ASSESSMENT` error. | **PASSED** |
| 17 | `test_workflow_reaches_the_human_review_boundary` | End-to-end graph runs 7 nodes; halts at gate in `SUSPENDED_FOR_APPROVAL`; approval helper works. | **PASSED** |
| 18 | `test_pending_approval_is_serialized_correctly` | Full round-trip state serialization/deserialization with plan and approval state. | **PASSED** |
| 19 | `test_existing_m12_1_m12_2_and_m12_3_boundaries_remain_valid` | Cross-milestone sub-graph compilation across M12.1, M12.2, M12.3, and M12.4. | **PASSED** |
| 20 | `test_execution_records_errors_and_warnings_remain_correct` | Auditable `AgentExecutionRecord` instances created for both planning agent and approval gate. | **PASSED** |

---

## 11. Backward Compatibility & Full Regression Status

- **M12.1 Foundation Tests:** 12/12 passing (`test_workflow_foundation.py`).
- **M12.2 Perception Agent Tests:** 25/25 passing (`test_m12_2_agents.py`).
- **M12.3 Risk Assessment Agent Tests:** 20/20 passing (`test_m12_3_risk_assessment.py`).
- **M12.4 Response Planning Agent Tests:** 20/20 passing (`test_m12_4_response_planning.py`).
- **Total Multi-Agent Test Suite:** **77 passed in 1.62s**.
- **Total Backend Unit Test Suite (M05 - M12):** **387 passed in 11.69s**.
- **Regression Count:** **0 regressions**.

---

## 12. Workspace Artifact Inventory

### Created Files
- `backend/app/agents/nodes/response_planning.py`: Agent 5 node implementation with 7 deterministic case rules.
- `backend/app/agents/nodes/human_approval.py`: Human Review Gate node and decision application helpers.
- `backend/tests/unit/agents/test_m12_4_response_planning.py`: 20 unit tests for Agent 5 and Human Review Gate.
- `docs/reports/m12_4_response_planning_agent_report.md`: This comprehensive engineering report.

### Modified Files
- `backend/app/agents/schemas.py`: Defined `HumanApprovalStatus`, `RecommendationPriority`, updated `ActionRecommendation`, `ResponsePlanningAgentOutput`, `HumanApprovalState`, and `WorkflowExecutionResult`.
- `backend/app/agents/state.py`: Updated `VALID_STAGE_TRANSITIONS` for human review gate completion.
- `backend/app/agents/graph.py`: Registered `response_planning_agent` and `human_review_gate` nodes; connected edges; added `include_planning_agent` parameter.
- `backend/app/agents/services/workflow_service.py`: Added `include_planning_agent`, plan/approval mapping to `WorkflowExecutionResult`, and `apply_human_approval()` method.
- `backend/app/agents/nodes/__init__.py`: Exported planning and approval nodes.
- `backend/app/agents/__init__.py`: Exported M12.4 schemas and nodes at package root.
- `backend/tests/unit/agents/test_m12_3_risk_assessment.py`: Isolated M12.3 boundary tests with `include_planning_agent=False`.
- `docs/architecture/m12_multi_agent_architecture.md`: Updated architecture documentation to v1.4.0.

### Strictly Preserved Constraints
- Zero model checkpoints or dataset inventories altered.
- Zero Git commits, pushes, stashes, resets, or branch switches performed.
- Zero ungrounded LLM or autonomous tool invocations introduced.
- Preserved all existing user modifications.

---

## 13. Readiness for M12.5

With M12.4 fully completed and verified, the SCOUT multi-agent platform is primed for the final block of Milestone 12:
- **Agent 6 (Coordinator Agent):** Will consume the approved plan, synthesize executive summaries, compile the audit dossier, and produce `CoordinatorReportOutput`.
- **FastAPI Endpoints:** REST endpoints to submit workflow requests, check status, inspect recommendations, and submit human approval decisions.
- **End-to-End System Tests:** Integration tests verifying the entire lifecycle from HTTP POST to human approval and final reporting.

---

## 14. Beginner-Friendly Engineering Explanation

### What did we build?
Imagine an emergency control center during a forest fire. 
In the previous steps (M12.1 through M12.3), SCOUT acted like a team of specialized analysts:
1. One analyst checked satellite and camera photos to see if there was smoke or fire (Intelligence Agent).
2. Another analyst checked weather instruments to see how hot, dry, and windy it was (Weather Agent).
3. A third analyst looked at local maps to see where nearby homes, hospitals, and water sources were located (Geospatial Agent).
4. A senior risk officer pulled all three reports together into a composite threat rating (Risk Assessment Agent).

In **Milestone 12.4**, we built the **Response Planning Agent** and the **Human Approval Gate**.
- The **Response Planning Agent** acts like a master tactical planner. It takes the risk report and generates a list of recommended actions: for example, suggesting where to set up water drafting points, advising nearby residents to get ready, or sending a drone scout to verify unconfirmed smoke.
- Crucially, the AI is **never allowed to make decisions alone or hit the "launch" button**. 
- That is where the **Human Approval Gate** comes in. The AI prepares the plan, marks it as **PENDING**, and immediately halts. It places the plan on the desk of the human Incident Commander. The Incident Commander can approve the plan, reject it, or ask for changes. Nothing happens in the real world until an authorized human commander signs off.

### Why is this safe?
1. **No Robot 911 Calls:** The AI cannot call 911, dispatch fire trucks, or send panic alerts on its own.
2. **No Hallucinated Resources:** The AI doesn't pretend there are 50 fire engines available if nobody knows what's in the firehouse. It only suggests *categories* of equipment (like "wildland brush truck" or "thermal drone").
3. **No Blind Evacuations:** If an incident is only "suspected" (like a smudge on a camera), the AI does not trigger costly mass evacuations; it directs scouts to go verify the location first.
4. **Complete Traceability:** Every recommendation has an audit link showing exactly which sensor or weather number prompted the idea.
