from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable, Dict

from upstash_redis import Redis
from upstash_vector import Index

try:
    from backend.services.agent_registry import AgentRegistryService
    from backend.services.database import DatabaseService, SentenceTransformerEmbeddingProvider
    from backend.services.discussion_service import DiscussionService
    from backend.services.llm_service import LLMService
    from backend.services.observability import ObservabilityService
    from backend.services.session_service import SessionService
    from backend.services.turn_workflow import TurnWorkflowService
except ModuleNotFoundError:
    from services.agent_registry import AgentRegistryService
    from services.database import DatabaseService, SentenceTransformerEmbeddingProvider
    from services.discussion_service import DiscussionService
    from services.llm_service import LLMService
    from services.observability import ObservabilityService
    from services.session_service import SessionService
    from services.turn_workflow import TurnWorkflowService


def build_runtime_services(
    *,
    upstash_redis_rest_url: str,
    upstash_redis_rest_token: str,
    upstash_vector_rest_url: str,
    upstash_vector_rest_token: str,
    llm_api_base_url: str,
    llm_api_key: str,
    llm_model_id: str,
    llm_429_max_retries: int,
    llm_request_throttle_seconds: float,
    agent_registry_cache_ttl_seconds: float,
    agent_config_cache_ttl_seconds: float,
    decode_redis_value: Callable[[Any], str],
    parse_agent_payload: Callable[[str, str], Any],
    run_blocking_io: Callable[..., Any],
    calculate_entropy: Callable[..., Any],
    execution_metrics_model: Callable[..., Any],
    extract_execution_metrics: Callable[..., Any],
    build_stream_execution_metrics: Callable[..., Any],
    telemetry_model: Callable[..., Any],
    vector_telemetry_model: Callable[..., Any],
    process_turn_response_model: Callable[..., Any],
    process_turn_stream_chunk_model: Callable[..., Any],
    process_turn_stream_status_model: Callable[..., Any],
    process_turn_stream_final_model: Callable[..., Any],
    generate_response_model: Callable[..., Any],
    streaming_response_factory: Callable[..., Any],
    export_session_pdf: Callable[..., Any],
    logger: Any,
) -> Dict[str, Any]:
    redis_client = Redis(url=upstash_redis_rest_url, token=upstash_redis_rest_token)
    vector_client = Index(url=upstash_vector_rest_url, token=upstash_vector_rest_token)
    database = DatabaseService(
        redis_client=redis_client,
        vector_index=vector_client,
        embedding_provider=SentenceTransformerEmbeddingProvider(),
    )
    agent_registry = AgentRegistryService(
        redis_client=redis_client,
        decode_value=decode_redis_value,
        parse_agent_payload=parse_agent_payload,
        run_blocking_io=run_blocking_io,
        registry_ttl_seconds=agent_registry_cache_ttl_seconds,
        config_ttl_seconds=agent_config_cache_ttl_seconds,
    )
    observability = ObservabilityService(
        redis_client=redis_client,
        vector_index=vector_client,
        decode_value=decode_redis_value,
        run_blocking_io=run_blocking_io,
        execution_metrics_model=execution_metrics_model,
        llm_api_base_url=llm_api_base_url,
        llm_api_key=llm_api_key,
        logger=logger,
    )
    session = SessionService(
        redis_client=redis_client,
        database_service=database,
        run_blocking_io=run_blocking_io,
        decode_value=decode_redis_value,
        export_session_pdf=export_session_pdf,
        logger=logger,
    )
    llm = LLMService(
        api_base_url=llm_api_base_url,
        api_key=llm_api_key,
        model_id=llm_model_id,
        max_retries=llm_429_max_retries,
        throttle_seconds=llm_request_throttle_seconds,
        execution_metrics_builder=execution_metrics_model,
        extract_execution_metrics=extract_execution_metrics,
        build_stream_execution_metrics=build_stream_execution_metrics,
        logger=logger,
    )
    turn_workflow = TurnWorkflowService(
        fetch_agent_config=agent_registry.fetch_agent_config,
        fetch_context_messages=session.fetch_context_messages,
        get_agent_context_matches=session.get_agent_context_matches,
        sanitize_generated_message=session.sanitize_generated_message,
        save_latest_execution_metrics=observability.save_latest_execution_metrics_async,
        persist_session_telemetry=session.persist_session_telemetry_async,
        save_message_to_storage=session.save_message_to_storage,
        calculate_entropy=calculate_entropy,
        build_telemetry=telemetry_model,
    )
    discussion = DiscussionService(
        turn_workflow_service=turn_workflow,
        session_service=session,
        llm_service=llm,
        fetch_agent_config=agent_registry.fetch_agent_config,
        save_latest_execution_metrics=observability.save_latest_execution_metrics_async,
        process_turn_response_model=process_turn_response_model,
        process_turn_stream_chunk_model=process_turn_stream_chunk_model,
        process_turn_stream_status_model=process_turn_stream_status_model,
        process_turn_stream_final_model=process_turn_stream_final_model,
        generate_response_model=generate_response_model,
        streaming_response_factory=streaming_response_factory,
        vector_telemetry_model=vector_telemetry_model,
        logger=logger,
        utcnow=lambda: datetime.now(timezone.utc),
    )
    return {
        "redis": redis_client,
        "vector_index": vector_client,
        "database_service": database,
        "agent_registry_service": agent_registry,
        "observability_service": observability,
        "session_service": session,
        "llm_service": llm,
        "turn_workflow_service": turn_workflow,
        "discussion_service": discussion,
    }
