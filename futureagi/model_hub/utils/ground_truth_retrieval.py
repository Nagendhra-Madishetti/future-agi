"""
Ground truth embedding and retrieval service.

The GT row carries two related but distinct mappings on the
``EvalGroundTruth`` model:

- ``variable_mapping`` — ``{template_variable: GT_column}`` for every
  ``{{template_variable}}`` in the rule prompt. These ARE the inputs;
  the embedding is computed from these columns and the runtime query is
  built from the same shape so the two always line up.
- ``role_mapping`` — two reserved keys describing the labelled side
  of each row:

      {
          "output":      "<GT column with the eval's labelled output>",
          "explanation": "<optional GT column with the human reason>",
      }

  These are NOT embedded — they are the labels surfaced as few-shot
  examples when a retrieved row is shown to the LLM judge.

Stale-embedding signalling is handled by flipping ``embedding_status``
back to ``"pending"`` when either mapping changes, so the FE polls the
same status field it already uses.
"""

from __future__ import annotations

import re
from typing import Any

import numpy as np
import structlog

logger = structlog.get_logger(__name__)


# Embedding model identifiers as understood by ``ModelServingClient``.
EMBED_MODEL_TEXT = "text_embedding"
EMBED_MODEL_IMAGE_TEXT = "image_text_embedding"

# Modality detection — URL / data-URI extension heuristics. Audio + PDF
# are surfaced for the FE hint UX but currently embed via the text path
# (the joint image-text space CLIP exposes does not cover them).
_URL_PREFIX_RE = re.compile(r"^(https?://\S+|data:[\w/+.-]+;base64,)", re.IGNORECASE)
_IMAGE_EXT_RE = re.compile(r"\.(png|jpe?g|gif|webp|bmp|svg)(\?|$)", re.IGNORECASE)
_AUDIO_EXT_RE = re.compile(r"\.(mp3|wav|m4a|flac|ogg|aac)(\?|$)", re.IGNORECASE)
_PDF_EXT_RE = re.compile(r"\.pdf(\?|$)", re.IGNORECASE)


def detect_value_modality(value: Any) -> str:
    """Return ``"text" | "image" | "audio" | "pdf"`` for a single value.

    Recognises HTTP(S) URLs and ``data:`` URIs by extension / content-type.
    Anything else — including plain strings, numbers, JSON blobs — is
    treated as text.
    """
    if not isinstance(value, str):
        return "text"
    s = value.strip()
    if not _URL_PREFIX_RE.match(s):
        return "text"
    low = s.lower()
    if low.startswith("data:image"):
        return "image"
    if low.startswith("data:audio"):
        return "audio"
    if low.startswith("data:application/pdf"):
        return "pdf"
    if _IMAGE_EXT_RE.search(low):
        return "image"
    if _AUDIO_EXT_RE.search(low):
        return "audio"
    if _PDF_EXT_RE.search(low):
        return "pdf"
    return "text"


def _embed_one_value_multimodal(value: str) -> list[float]:
    """Embed a single value through the joint image-text model."""
    from agentic_eval.core.embeddings.serving_client import get_serving_client

    client = get_serving_client()
    return client.embed_image_text(value)


def _average_vectors(vectors: list[list[float]]) -> list[float] | None:
    if not vectors:
        return None
    arr = np.array(vectors, dtype=np.float32)
    return np.mean(arr, axis=0).tolist()


# =========================================================================
# Mapping helpers
# =========================================================================


def _collect_mapped_columns(variable_mapping: dict | None) -> list[str]:
    """GT column names referenced by ``variable_mapping``.

    Each entry's value may be a single column name (the common case) or
    a list (when a single template variable is sourced from multiple
    columns concatenated).
    """
    if not variable_mapping:
        return []
    cols: list[str] = []
    seen: set[str] = set()
    for value in variable_mapping.values():
        candidates = value if isinstance(value, list) else [value]
        for col in candidates:
            if col and col not in seen:
                seen.add(col)
                cols.append(col)
    return cols


def get_label_columns(role_mapping: dict | None) -> tuple[str, str]:
    """Return ``(output_column, explanation_column)`` from ``role_mapping``.

    Either may be ``""`` when not configured. Supports back-compat data
    where older keys ``"expected_output"`` / ``"reasoning"`` were used.
    """
    if not isinstance(role_mapping, dict):
        return "", ""

    def _first_str(*candidates: Any) -> str:
        for c in candidates:
            if isinstance(c, str) and c.strip():
                return c
            if isinstance(c, list) and c and isinstance(c[0], str) and c[0].strip():
                return c[0]
        return ""

    output_col = _first_str(
        role_mapping.get("output"), role_mapping.get("expected_output")
    )
    explanation_col = _first_str(
        role_mapping.get("explanation"),
        role_mapping.get("reasoning"),
        role_mapping.get("reason"),
    )
    return output_col, explanation_col


# =========================================================================
# Text Preparation
# =========================================================================


def prepare_embedding_text(row: dict, variable_mapping: dict | None) -> str:
    """Build the text to embed for a GT row.

    Embeds only the rule prompt's inputs — the columns mapped through
    ``variable_mapping``. The labelled output / explanation columns are
    never embedded; the query at eval time is the user's runtime input,
    so embedding the label would create a vector the query cannot
    semantically match.
    """
    cols = _collect_mapped_columns(variable_mapping)
    if cols:
        parts: list[str] = []
        for col in cols:
            val = (row or {}).get(col)
            if val is not None and str(val).strip():
                parts.append(f"{col}: {val}")
        if parts:
            return "\n".join(parts)

    parts = []
    for key, value in (row or {}).items():
        if value is not None and str(value).strip():
            parts.append(f"{key}: {value}")
    return "\n".join(parts)


def build_query_text(
    current_input: dict | str | None, variable_mapping: dict | None
) -> str:
    """Build the runtime query text used for similarity search.

    Mirrors :func:`prepare_embedding_text` so the stored vector and the
    query vector are produced from the same shape. Accepts a dict
    ``{template_variable: value}`` (standard runtime), a string (legacy
    single-text-box callers), or ``None`` (returns ``""``).
    """
    if isinstance(current_input, str):
        return current_input.strip()
    if not current_input:
        return ""

    parts: list[str] = []
    if variable_mapping:
        for tmpl_var, col in variable_mapping.items():
            target_cols = col if isinstance(col, list) else [col]
            value = current_input.get(tmpl_var)
            if value is None:
                for target in target_cols:
                    if target in current_input:
                        value = current_input[target]
                        break
            if value is None or not str(value).strip():
                continue
            for target in target_cols:
                parts.append(f"{target}: {value}")
        if parts:
            return "\n".join(parts)

    for key, value in current_input.items():
        if value is not None and str(value).strip():
            parts.append(f"{key}: {value}")
    return "\n".join(parts)


# =========================================================================
# Embedding Generation
# =========================================================================


def generate_embedding(text: str) -> list[float]:
    from agentic_eval.core.embeddings.serving_client import get_serving_client

    client = get_serving_client()
    return client.embed_text(text)


def generate_embeddings_batch(
    texts: list[str], batch_size: int = 32
) -> list[list[float] | None]:
    """Generate embeddings for a list of texts. ``None`` slots denote
    per-row failures so callers can skip without losing alignment."""
    from agentic_eval.core.embeddings.serving_client import get_serving_client

    client = get_serving_client()
    all_embeddings: list[list[float] | None] = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        for text in batch:
            try:
                all_embeddings.append(client.embed_text(text))
            except Exception as exc:
                logger.warning(
                    "embedding_failed_for_row", error=str(exc), batch_offset=i
                )
                all_embeddings.append(None)
    return all_embeddings


# =========================================================================
# Multimodal row + query embedding (CLIP-style joint space)
# =========================================================================


def detect_row_modality(
    row: dict, variable_mapping: dict | None
) -> str:
    """Return the dominant modality across the row's mapped input columns.

    ``"image"`` if any mapped column carries an image URL / data URI
    (use the joint image-text model). Otherwise ``"text"`` (use the
    plain text embedder — cheaper and more accurate for text-only).

    Audio + PDF stay in the text path for now; their dedicated
    embedders live in a different vector space.
    """
    for col in _collect_mapped_columns(variable_mapping):
        val = row.get(col)
        if detect_value_modality(val) == "image":
            return "image"
    return "text"


def compute_row_embedding(
    row: dict, variable_mapping: dict | None
) -> tuple[str, list[float] | None]:
    """Embed a GT row. Returns ``(model_name, vector)`` where
    ``vector`` may be ``None`` on failure.

    Image-bearing rows use ``embed_image_text`` per mapped column and
    average the resulting vectors so a single comparable vector lands
    in storage. Pure-text rows use ``embed_text`` over the concatenated
    text shape, matching legacy behaviour.
    """
    modality = detect_row_modality(row, variable_mapping)
    if modality == "image":
        per_col: list[list[float]] = []
        for col in _collect_mapped_columns(variable_mapping):
            val = row.get(col)
            if val is None or not str(val).strip():
                continue
            try:
                per_col.append(_embed_one_value_multimodal(str(val)))
            except Exception as exc:
                logger.warning(
                    "row_multimodal_value_embed_failed",
                    column=col,
                    error=str(exc),
                )
        return EMBED_MODEL_IMAGE_TEXT, _average_vectors(per_col)

    text = prepare_embedding_text(row, variable_mapping)
    if not text.strip():
        return EMBED_MODEL_TEXT, None
    try:
        return EMBED_MODEL_TEXT, generate_embedding(text)
    except Exception as exc:
        logger.warning("row_text_embed_failed", error=str(exc))
        return EMBED_MODEL_TEXT, None


def compute_query_embedding(
    current_input: dict | str | None,
    variable_mapping: dict | None,
    embedding_model: str,
) -> list[float] | None:
    """Embed a runtime query, matching whatever model was used at GT
    embed time (so the query and the stored vectors live in the same
    space).
    """
    if embedding_model == EMBED_MODEL_IMAGE_TEXT:
        per_col: list[list[float]] = []
        if isinstance(current_input, dict):
            for col in _collect_mapped_columns(variable_mapping):
                value = current_input.get(col)
                if value is None and variable_mapping:
                    for tmpl_var, mapped in variable_mapping.items():
                        targets = mapped if isinstance(mapped, list) else [mapped]
                        if col in targets and tmpl_var in current_input:
                            value = current_input[tmpl_var]
                            break
                if value is None or not str(value).strip():
                    continue
                try:
                    per_col.append(_embed_one_value_multimodal(str(value)))
                except Exception as exc:
                    logger.warning(
                        "query_multimodal_value_embed_failed",
                        column=col,
                        error=str(exc),
                    )
        elif isinstance(current_input, str) and current_input.strip():
            try:
                per_col.append(_embed_one_value_multimodal(current_input))
            except Exception as exc:
                logger.warning(
                    "query_multimodal_string_embed_failed", error=str(exc)
                )
        return _average_vectors(per_col)

    query_text = build_query_text(current_input, variable_mapping)
    if not query_text:
        return None
    try:
        return generate_embedding(query_text)
    except Exception as exc:
        logger.warning("query_text_embed_failed", error=str(exc))
        return None


# =========================================================================
# Similarity Search
# =========================================================================


def cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    """Cosine similarity in [0, 1]; 0 for any zero-norm input."""
    a = np.array(vec_a, dtype=np.float32)
    b = np.array(vec_b, dtype=np.float32)
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


def retrieve_similar_examples(
    ground_truth_id: str,
    query_embedding: list[float],
    max_examples: int = 3,
    similarity_threshold: float = 0.7,
) -> list[dict]:
    """Top-K most similar GT rows by cosine similarity.

    Returns ``[{"similarity": float, "row_data": dict, "row_index": int}, ...]``
    sorted by similarity descending. Rows below ``similarity_threshold``
    are dropped.
    """
    from model_hub.models.evals_metric import EvalGroundTruthEmbedding

    embeddings_qs = EvalGroundTruthEmbedding.objects.filter(
        ground_truth_id=ground_truth_id,
    ).values_list("embedding", "row_data", "row_index")

    scored = []
    for emb_vec, row_data, row_index in embeddings_qs:
        sim = cosine_similarity(query_embedding, emb_vec)
        if sim >= similarity_threshold:
            scored.append(
                {
                    "similarity": round(sim, 4),
                    "row_data": row_data,
                    "row_index": row_index,
                }
            )
    scored.sort(key=lambda x: x["similarity"], reverse=True)
    return scored[:max_examples]


# =========================================================================
# Ground Truth Loading (for eval execution)
# =========================================================================


def load_ground_truth_config(eval_template) -> dict | None:
    """Return the GT config dict from the template, or ``None``."""
    config = getattr(eval_template, "config", None) or {}
    gt_config = config.get("ground_truth")
    if not gt_config or not gt_config.get("enabled"):
        return None
    if not gt_config.get("ground_truth_id"):
        return None
    return gt_config


def get_ground_truth_few_shot_examples(
    gt_config: dict,
    current_input: dict | str | None,
) -> list[dict]:
    """Retrieve similar GT rows for few-shot injection.

    Query text is constructed via :func:`build_query_text` so it matches
    the shape stored at embed time.
    """
    from model_hub.models.evals_metric import EvalGroundTruth

    gt_id = gt_config.get("ground_truth_id")
    max_examples = gt_config.get("max_examples", 3)
    threshold = gt_config.get("similarity_threshold", 0.7)

    try:
        gt = EvalGroundTruth.objects.get(id=gt_id, deleted=False)
    except EvalGroundTruth.DoesNotExist:
        logger.warning("ground_truth_not_found", gt_id=gt_id)
        return []

    if gt.embedding_status != "completed":
        logger.warning(
            "ground_truth_embeddings_not_ready",
            gt_id=gt_id,
            status=gt.embedding_status,
        )
        return []

    # Defense-in-depth: even though `inject_ground_truth_context` already
    # short-circuits when there's no usable input, direct callers (the
    # search_ground_truth agent tool, the test-retrieval view) land here
    # too. Same skip rule keeps them consistent.
    if isinstance(current_input, dict) and not has_usable_inputs_for_gt(
        gt.variable_mapping, current_input
    ):
        return []

    query_embedding = compute_query_embedding(
        current_input, gt.variable_mapping, gt.embedding_model or EMBED_MODEL_TEXT
    )
    if not query_embedding:
        return []

    results = retrieve_similar_examples(
        ground_truth_id=gt_id,
        query_embedding=query_embedding,
        max_examples=max_examples,
        similarity_threshold=threshold,
    )
    return [r["row_data"] for r in results]


# =========================================================================
# Centralised eval-runner injection
# =========================================================================


_GT_DEBUG_LOG = "/tmp/gt_injection_debug.log"


def _log_gt_injection(event: str, **payload: Any) -> None:
    """Dual-sink debug logger for GT injection paths.

    Emits a structlog event AND appends the full payload (no truncation
    of the few-shot text or row_data) to ``/tmp/gt_injection_debug.log``
    inside the container so we can ``docker exec backend tail -f`` it
    while running an eval. Structured logs go to Loki via stdout; the
    file sink is for hands-on inspection during debugging.
    """
    logger.info(event, **payload)
    try:
        import datetime
        import json

        with open(_GT_DEBUG_LOG, "a", encoding="utf-8") as fp:
            fp.write(
                f"\n=== {datetime.datetime.utcnow().isoformat()}Z {event} ===\n"
            )
            for key, value in payload.items():
                fp.write(f"--- {key} ---\n")
                if isinstance(value, str):
                    fp.write(value + "\n")
                else:
                    fp.write(json.dumps(value, indent=2, default=str) + "\n")
    except Exception as exc:
        logger.warning("gt_injection_debug_log_write_failed", error=str(exc))


def _is_empty_value(value: Any) -> bool:
    """Should this runtime value be treated as "no signal" for GT retrieval?

    ``0``, ``False``, and other legitimate-but-falsy scalars are NOT
    empty — they're valid eval inputs. Empty means actually absent:
    ``None``, blank/whitespace string, empty list/tuple/set, empty dict.
    """
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, (list, tuple, set, dict)):
        return len(value) == 0
    return False


def has_usable_inputs_for_gt(
    variable_mapping: dict | None,
    runtime_inputs: dict | None,
) -> bool:
    """Decide whether GT retrieval/injection is worth running.

    Returns ``True`` only if at least one template variable is mapped to
    a GT column AND its runtime value is non-empty. This is the gate the
    eval runner uses to short-circuit GT for evals that have no template
    variables declared at all, haven't been mapped yet, or were invoked
    with all-empty inputs.

    Both keying conventions are accepted on the runtime side: the
    canonical ``{template_var: value}`` shape AND the legacy
    ``{gt_column: value}`` shape (some older callers pass GT column
    names through).
    """
    if not variable_mapping:
        return False
    if not runtime_inputs or not isinstance(runtime_inputs, dict):
        return False
    for tmpl_var, col in variable_mapping.items():
        if not _is_empty_value(runtime_inputs.get(tmpl_var)):
            return True
        targets = col if isinstance(col, list) else [col]
        for target in targets:
            if target and not _is_empty_value(runtime_inputs.get(target)):
                return True
    return False


def inject_ground_truth_context(
    mapped: dict, eval_template, eval_type_id: str = ""
) -> dict:
    """Mutate ``mapped`` with GT context when the template has GT enabled
    and ready, then return it.

    CustomPromptEvaluator path → inject ``ground_truth_few_shot`` (a
    formatted string of retrieved examples). Other (Agent) paths →
    inject ``ground_truth_config`` so the evaluator can expose the
    ``search_ground_truth`` tool.

    Skips entirely when there's no usable input to query against — see
    :func:`has_usable_inputs_for_gt` for the rule.
    """
    from model_hub.models.evals_metric import EvalGroundTruth

    gt_config = load_ground_truth_config(eval_template)
    if not gt_config:
        return mapped

    try:
        gt_obj = EvalGroundTruth.objects.filter(
            id=gt_config["ground_truth_id"], deleted=False
        ).first()
    except Exception:
        gt_obj = None

    if gt_obj is None:
        return mapped

    if not has_usable_inputs_for_gt(gt_obj.variable_mapping, mapped):
        _log_gt_injection(
            "ground_truth_skipped_no_usable_inputs",
            gt_id=str(gt_obj.id),
            eval_type_id=eval_type_id,
            template_id=str(getattr(eval_template, "id", "") or ""),
            variable_mapping=gt_obj.variable_mapping,
            runtime_inputs=mapped,
        )
        return mapped

    gt_config = dict(gt_config)
    gt_config["embedding_status"] = gt_obj.embedding_status

    if (
        eval_type_id == "CustomPromptEvaluator"
        and gt_obj.embedding_status == "completed"
    ):
        examples = get_ground_truth_few_shot_examples(gt_config, mapped)
        output_col, explanation_col = get_label_columns(gt_obj.role_mapping)
        few_shot_text = ""
        if examples:
            few_shot_text = format_few_shot_examples(
                examples,
                variable_mapping=gt_obj.variable_mapping,
                output_column=output_col,
                explanation_column=explanation_col,
                injection_format=gt_config.get("injection_format", "structured"),
            )
            mapped["ground_truth_few_shot"] = few_shot_text
        _log_gt_injection(
            "ground_truth_custom_prompt_injected",
            gt_id=str(gt_obj.id),
            template_id=str(getattr(eval_template, "id", "") or ""),
            variable_mapping=gt_obj.variable_mapping,
            role_mapping=gt_obj.role_mapping,
            output_column=output_col,
            explanation_column=explanation_col,
            runtime_inputs=mapped,
            examples_count=len(examples),
            examples_preview=examples[:3],
            injection_format=gt_config.get("injection_format", "structured"),
            few_shot_text=few_shot_text,
        )
        return mapped

    mapped["ground_truth_config"] = gt_config
    _log_gt_injection(
        "ground_truth_agent_config_injected",
        gt_id=str(gt_obj.id),
        template_id=str(getattr(eval_template, "id", "") or ""),
        eval_type_id=eval_type_id,
        variable_mapping=gt_obj.variable_mapping,
        role_mapping=gt_obj.role_mapping,
        runtime_inputs=mapped,
        ground_truth_config=gt_config,
    )
    return mapped


# =========================================================================
# Per-output-type validation
# =========================================================================


def _parse_score(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip()
    if not s:
        return None
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def validate_output_value(
    value: Any,
    output_type_normalized: str | None,
    choice_scores: dict | None = None,
    pass_threshold: float | None = None,
) -> tuple[bool, str | None]:
    """Validate a candidate eval-output value against a template's output
    type. Returns ``(ok, error_message)``."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return False, "Value is empty."

    out_type = (output_type_normalized or "").lower()
    if out_type == "pass_fail":
        allowed = {"pass", "fail", "true", "false", "0", "1", "yes", "no"}
        if str(value).strip().lower() not in allowed:
            return (
                False,
                "Expected one of: Pass / Fail / True / False / Yes / No.",
            )
        return True, None

    if out_type == "percentage":
        score = _parse_score(value)
        if score is None:
            return False, "Expected a numeric score between 0 and 1."
        if score < 0 or score > 1:
            return False, "Score must lie in the [0, 1] range."
        return True, None

    if out_type == "deterministic":
        if not isinstance(choice_scores, dict) or not choice_scores:
            return True, None
        canonical = {str(k).strip().lower(): k for k in choice_scores.keys()}
        if str(value).strip().lower() not in canonical:
            options = ", ".join(str(k) for k in choice_scores.keys())
            return False, f"Expected one of: {options}."
        return True, None

    return True, None


# =========================================================================
# Few-Shot Prompt Formatting
# =========================================================================


def format_few_shot_examples(
    examples: list[dict],
    *,
    variable_mapping: dict | None,
    output_column: str | None = None,
    explanation_column: str | None = None,
    injection_format: str = "structured",
) -> str:
    """Format GT examples for injection into the LLM judge prompt.

    Inputs render using the rule prompt's template variable names. Each
    example then surfaces the GT row's eval output and (optionally) the
    human's explanation.
    """
    if not examples:
        return ""
    if injection_format == "xml":
        return _format_xml(
            examples, variable_mapping, output_column, explanation_column
        )
    if injection_format == "conversational":
        return _format_conversational(
            examples, variable_mapping, output_column, explanation_column
        )
    return _format_structured(
        examples, variable_mapping, output_column, explanation_column
    )


def _iter_inputs(example: dict, variable_mapping: dict | None):
    """Yield ``(template_variable, gt_column, value)`` for the input side."""
    if not variable_mapping:
        for key, val in (example or {}).items():
            yield key, key, val
        return
    for tmpl_var, col in variable_mapping.items():
        targets = col if isinstance(col, list) else [col]
        for target in targets:
            if target in example:
                yield tmpl_var, target, example[target]


def _format_structured(examples, variable_mapping, output_column, explanation_column):
    lines = ["--- Reference Examples (scored by human experts) ---", ""]
    for i, example in enumerate(examples, 1):
        lines.append(f"Example {i}:")
        for tmpl_var, _target, val in _iter_inputs(example, variable_mapping):
            label = tmpl_var.replace("_", " ").title()
            lines.append(f"  {label}: {val}")
        if output_column and output_column in example:
            lines.append(f"  Eval Output: {example[output_column]}")
        if explanation_column and explanation_column in example:
            lines.append(f"  Eval Output Explanation: {example[explanation_column]}")
        lines.append("")
    lines.append("--- End Reference Examples ---")
    return "\n".join(lines)


def _format_conversational(
    examples, variable_mapping, output_column, explanation_column
):
    lines = []
    for i, example in enumerate(examples, 1):
        case_parts: list[str] = []
        for tmpl_var, _target, val in _iter_inputs(example, variable_mapping):
            case_parts.append(f"{tmpl_var.replace('_', ' ').title()}: {val}")
        if case_parts:
            lines.append(f"Example {i}: " + " | ".join(case_parts))
        judgement: list[str] = []
        if output_column and output_column in example:
            judgement.append(f"Eval Output: {example[output_column]}")
        if explanation_column and explanation_column in example:
            judgement.append(f"Explanation: {example[explanation_column]}")
        if judgement:
            lines.append("Expert judgment: " + " | ".join(judgement))
        lines.append("")
    return "\n".join(lines)


def _format_xml(examples, variable_mapping, output_column, explanation_column):
    lines = ["<reference_examples>"]
    for example in examples:
        attr = ""
        if output_column and output_column in example:
            attr = f' eval_output="{example[output_column]}"'
        lines.append(f"  <example{attr}>")
        for tmpl_var, _target, val in _iter_inputs(example, variable_mapping):
            lines.append(f"    <{tmpl_var}>{val}</{tmpl_var}>")
        if explanation_column and explanation_column in example:
            lines.append(
                f"    <eval_output_explanation>"
                f"{example[explanation_column]}"
                f"</eval_output_explanation>"
            )
        lines.append("  </example>")
    lines.append("</reference_examples>")
    return "\n".join(lines)
