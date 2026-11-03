
import { useState } from "react";
import { api, getApiError } from "../services/api";
import "./ContinuityAIAnalysis.css";

interface EvidenceReference {
  kind: string;
  record_id?: number;
  relationship_id?: number;
  relation_type?: string;
  source_item?: { id: number; title: string };
  target_item?: { id: number; title: string };
  filename: string;
  locator: string;
  excerpt: string;
}

interface RiskExplanation {
  knowledge_item_id: number;
  title: string;
  explanation: string;
  potential_impact: string;
  recommended_checks: string[];
  uncertainties: string[];
  assigned_member: {
    name: string;
    membership_status: string;
  };
  work_status: string;
  attention_signals: string[];
  evidence: EvidenceReference[];
  review_status: string;
}

interface AnalysisResponse {
  project_id: number;
  model: string;
  potential_gaps_count: number;
  gaps_analyzed: number;
  analysis_limit: number;
  more_gaps_available: boolean;
  explanations: RiskExplanation[];
  message: string;
}

interface Props {
  projectId: number;
}

export default function ContinuityAIAnalysis({
  projectId,
}: Props) {
  const [result, setResult] =
    useState<AnalysisResponse | null>(null);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function generateAnalysis() {
    setLoading(true);
    setError("");
    setResult(null);

    try {
      const response = await api.post<AnalysisResponse>(
        `/api/projects/${projectId}/continuity/gaps/explain`
      );

      setResult(response.data);
    } catch (err) {
      setError(getApiError(err));
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="continuity-ai-panel">
      <div className="continuity-ai-header">
        <div>
          <span className="continuity-ai-eyebrow">
            RELAYMAP INTELLIGENCE
          </span>

          <h2>AI Continuity Analyst</h2>

          <p>
            Understand why unfinished work may be at risk
            and what your team should verify before handover.
          </p>
        </div>

        <div className="continuity-ai-icon">
          ✦
        </div>
      </div>

      <button
        type="button"
        className="continuity-ai-button"
        onClick={generateAnalysis}
        disabled={loading}
      >
        {loading
          ? "Analysing project evidence..."
          : "✦ Generate AI Risk Analysis"}
      </button>

      {error && (
        <div className="continuity-ai-error">
          {error}
        </div>
      )}

      {loading && (
        <div className="continuity-ai-loading">
          Analysing approved work items and their
          approved dependencies...
        </div>
      )}

      {result && (
        <div className="continuity-ai-results">
          <div className="continuity-ai-summary">
            <div>
              <strong>{result.gaps_analyzed}</strong>
              <span> gaps analysed</span>
            </div>

            <div>
              <strong>{result.potential_gaps_count}</strong>
              <span> potential gaps found</span>
            </div>
          </div>

          {result.explanations.length === 0 && (
            <p className="continuity-ai-empty">
              {result.message}
            </p>
          )}

          {result.explanations.map((item) => (
            <article
              className="continuity-ai-card"
              key={item.knowledge_item_id}
            >
              <div className="continuity-ai-card-top">
                <div>
                  <span className="continuity-ai-item-type">
                    {item.work_status.replace("_", " ")}
                  </span>

                  <h3>{item.title}</h3>

                  <p className="continuity-ai-owner">
                    Assigned to {item.assigned_member.name}
                    {" · "}
                    {item.assigned_member.membership_status}
                  </p>
                </div>

                <span className="continuity-ai-advisory">
                  AI advisory
                </span>
              </div>

              <div className="continuity-ai-section">
                <h4>Why was this flagged?</h4>
                <p>{item.explanation}</p>
              </div>

              <div className="continuity-ai-section">
                <h4>Potential downstream impact</h4>
                <p>{item.potential_impact}</p>
              </div>

              <div className="continuity-ai-section">
                <h4>Signals detected</h4>

                <ul>
                  {item.attention_signals.map(
                    (signal, index) => (
                      <li key={index}>{signal}</li>
                    )
                  )}
                </ul>
              </div>

              <div className="continuity-ai-section">
                <h4>Recommended reviewer checks</h4>

                <ul>
                  {item.recommended_checks.map(
                    (check, index) => (
                      <li key={index}>{check}</li>
                    )
                  )}
                </ul>
              </div>

              {item.uncertainties.length > 0 && (
                <div className="continuity-ai-section">
                  <h4>What remains uncertain?</h4>

                  <ul>
                    {item.uncertainties.map(
                      (uncertainty, index) => (
                        <li key={index}>
                          {uncertainty}
                        </li>
                      )
                    )}
                  </ul>
                </div>
              )}

              <div className="continuity-ai-evidence">
                <h4>Supporting evidence</h4>

                {item.evidence.map((evidence, index) => (
                  <div
                    className="continuity-ai-evidence-item"
                    key={`${evidence.kind}-${index}`}
                  >
                    <strong>
                      {evidence.kind === "approved_relationship"
                        ? `Approved relationship: ${evidence.relation_type}`
                        : "Approved knowledge record"}
                    </strong>

                    <span>
                      {evidence.filename}
                      {" · "}
                      {evidence.locator}
                    </span>

                    {evidence.source_item && (
                      <span>
                        {evidence.source_item.title}
                        {" → "}
                        {evidence.target_item?.title}
                      </span>
                    )}

                    <blockquote>
                      {evidence.excerpt}
                    </blockquote>
                  </div>
                ))}
              </div>
            </article>
          ))}

          {result.more_gaps_available && (
            <p className="continuity-ai-note">
              This request analysed the first{" "}
              {result.analysis_limit} gaps. More gaps are
              available for separate analysis.
            </p>
          )}

          <p className="continuity-ai-disclaimer">
            AI-generated explanations are advisory.
            Review the cited evidence before acting.
            No assignments or project statuses were changed.
          </p>
        </div>
      )}
    </section>
  );
}