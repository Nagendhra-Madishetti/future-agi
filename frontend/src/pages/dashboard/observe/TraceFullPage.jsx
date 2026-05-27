import React, { useCallback, useEffect, useRef } from "react";
import { useLocation, useNavigate, useParams } from "react-router";
import { Helmet } from "react-helmet-async";
import TraceDetailDrawerV2 from "src/components/traceDetail/TraceDetailDrawerV2";
import { useRecordActivationEvent } from "src/sections/onboarding-home/hooks/useRecordActivationEvent";

export default function TraceFullPage() {
  const { observeId, traceId } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const { mutate: recordActivationEvent } = useRecordActivationEvent();
  const recordedTraceRef = useRef(null);
  const isSampleTrace =
    new URLSearchParams(location.search).get("sample") === "true";

  const handleClose = useCallback(() => {
    if (window.history.length > 1) {
      navigate(-1);
    } else if (observeId) {
      navigate(`/dashboard/observe/${observeId}/llm-tracing`);
    } else {
      window.close();
    }
  }, [navigate, observeId]);

  useEffect(() => {
    if (!observeId || !traceId) return;

    const recordKey = `${observeId}:${traceId}`;
    if (recordedTraceRef.current === recordKey) return;
    recordedTraceRef.current = recordKey;

    recordActivationEvent({
      eventName: isSampleTrace
        ? "sample_trace_detail_opened"
        : "trace_detail_opened",
      primaryPath: isSampleTrace ? "sample" : "observe",
      stage: "review_first_trace",
      source: isSampleTrace ? "sample_trace_full_page" : "trace_full_page",
      artifactType: "trace",
      artifactId: traceId,
      projectId: observeId,
      isSample: isSampleTrace,
      metadata: {
        entry: "trace_full_page",
        is_sample_route: isSampleTrace,
      },
    });
  }, [isSampleTrace, observeId, recordActivationEvent, traceId]);

  return (
    <>
      <Helmet>
        <title>Trace — {traceId?.substring(0, 8) || "..."}</title>
      </Helmet>
      <TraceDetailDrawerV2
        open
        traceId={traceId}
        projectId={observeId}
        onClose={handleClose}
        hasPrev={false}
        hasNext={false}
        initialFullscreen
      />
    </>
  );
}
