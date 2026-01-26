"""Agent setup and configuration for appraisal processing"""

from __future__ import annotations

import sys
from pathlib import Path

# Add backend to path for imports
current_file = Path(__file__).resolve()
backend_path = Path("/app")
if not (backend_path / "app").exists():
    # Try to find backend in parent directories
    for parent in current_file.parents:
        candidate = parent / "backend"
        if candidate.exists():
            backend_path = candidate
            break

if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))

try:
    from langchain.agents import AgentExecutor, create_openai_tools_agent
    from langchain_openai import ChatOpenAI
    from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
    LANGCHAIN_AVAILABLE = True
except ImportError:
    LANGCHAIN_AVAILABLE = False
    # Create dummy classes for type hints
    class AgentExecutor:
        pass
    class ChatOpenAI:
        pass
    class ChatPromptTemplate:
        pass
    class MessagesPlaceholder:
        pass

from app.settings import get_settings
from .tools import get_appraisal_tools


def create_appraisal_agent(max_iterations: int = 50, max_execution_time: int = 300) -> AgentExecutor:
    """
    Create agent for appraisal processing using LangChain.
    
    Args:
        max_iterations: Maximum number of agent iterations (default from settings)
        max_execution_time: Maximum execution time in seconds (default from settings)
    
    Returns:
        AgentExecutor configured for appraisal processing
        
    Raises:
        ImportError: If LangChain dependencies are not installed
    """
    if not LANGCHAIN_AVAILABLE:
        raise ImportError(
            "LangChain is required for agentic mode. "
            "Install with: pip install langchain langchain-openai"
        )
    
    settings = get_settings()
    
    # Use settings values if not provided
    if max_iterations == 50:
        max_iterations = settings.agent_max_iterations
    if max_execution_time == 300:
        max_execution_time = settings.agent_execution_timeout_seconds
    
    # Initialize LLM with retry configuration
    llm = ChatOpenAI(
        model=settings.openai_text_model,
        temperature=0,
        api_key=settings.openai_api_key,
        max_retries=3,  # Retry rate limit errors
        request_timeout=settings.openai_request_timeout_seconds,
    )
    
    # Get tools
    tools = get_appraisal_tools()
    
    # Create prompt template
    prompt = ChatPromptTemplate.from_messages([
        ("system", """You are an AI assistant that processes vehicle appraisals.

Your goal: Determine if an appraisal is ready for decision or needs more evidence.

Available tools:
- extract_vision_from_photo(photo_url, photo_id): Analyze a photo to extract vehicle information (angle, odometer, VIN, damage). Results are automatically stored.
- check_evidence_completeness(): Check what evidence is missing based on photos analyzed so far. No parameters needed.
- retrieve_similar_appraisals(): Find similar historical appraisals to provide context for risk analysis. Call this BEFORE scan_for_risks() to enable pattern-based insights. No parameters needed.
- scan_for_risks(): Identify risks and inconsistencies based on all data collected. If retrieve_similar_appraisals() was called first, this will include historical context. No parameters needed.
- calculate_readiness_score(): Calculate final readiness score and determine decision status. No parameters needed.

Process systematically:
1. Extract information from ALL photos using extract_vision_from_photo (call once per photo with its URL and ID)
2. After processing ALL photos, check evidence completeness using check_evidence_completeness()
3. IMPORTANT: Call retrieve_similar_appraisals() to find similar historical cases for context
4. Scan for risks using scan_for_risks() (this will automatically use historical context from step 3)
5. Calculate readiness score using calculate_readiness_score()
6. Provide a clear recommendation with reasoning

Important guidelines:
- Process ALL photos before calling other tools (they need the vision data)
- ALWAYS call retrieve_similar_appraisals() before scan_for_risks() to enable data-driven analysis
- Always cite specific evidence (photo IDs, metadata fields, note sections, or historical patterns)
- Surface uncertainty explicitly if confidence is low
- Never suggest prices, valuations, or monetary amounts
- Never accuse anyone of fraud
- Only flag inconsistencies with evidence references

When historical context is available from similar appraisals, use it to:
- Compare patterns (e.g., "Similar vehicles typically have X")
- Validate expectations (e.g., "Mileage is normal for this vehicle age based on N similar cases")
- Identify anomalies (e.g., "This damage pattern is unusual compared to historical data")

Always explain your reasoning and cite evidence."""),
        ("human", "{input}"),
        MessagesPlaceholder(variable_name="agent_scratchpad"),
    ])
    
    # Create agent
    agent = create_openai_tools_agent(llm, tools, prompt)
    
    # Create executor with safeguards
    executor = AgentExecutor(
        agent=agent,
        tools=tools,
        verbose=False,  # Disable verbose to avoid callback warnings
        max_iterations=max_iterations,  # Prevent infinite loops
        max_execution_time=max_execution_time,  # Timeout protection
        return_intermediate_steps=True,  # Capture steps for ledger logging
    )
    
    return executor
