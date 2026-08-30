import { useParams } from "react-router-dom";
import { TraceDetail } from "../components/trace/TraceDetail";
import { TraceSessionList } from "../components/trace/TraceSessionList";

export default function TracePage() {
  const { sessionId } = useParams();
  return sessionId ? <TraceDetail sessionId={Number(sessionId)} /> : <TraceSessionList />;
}
