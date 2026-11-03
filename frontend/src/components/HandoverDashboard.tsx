
import { useEffect, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  Clock,
  Download,
  FileText,
  Network,
  RefreshCw,
  ShieldCheck,
  Sparkles,
  Users,
  XCircle,
} from "lucide-react";

import { api, getApiError } from "../services/api";
import "./HandoverDashboard.css";

type HandoverReport = {
  id: number;
  project_id: number;
  recipient_user_id: number | null;
  generated_by_user_id: number;
  title: string;
  report_data: any;
  status: "draft" | "approved" | "rejected";
  reviewed_by_user_id: number | null;
  reviewed_at: string | null;
  review_notes: string | null;
  created_at: string;
};

type Props = {
  projectId: number;
};

type ProjectMemberOption = {
  user_id: number;
  full_name: string;
  role: string;
  membership_status: string;
};

const formatDate = (value?: string | null) => {
  if (!value) return "Not available";

  const date = new Date(value);

  return Number.isNaN(date.getTime())
    ? value
    : date.toLocaleString();
};

const formatStatus = (value?: string) => {
  if (!value) return "Unknown";

  return value
    .replaceAll("_", " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
};

export default function HandoverDashboard({ projectId }: Props) {
  const [reports, setReports] = useState<HandoverReport[]>([]);
  const [selectedReportId, setSelectedReportId] = useState<number | null>(
    null
  );

  // Project members for the recipient dropdown.
  const [members, setMembers] = useState<ProjectMemberOption[]>([]);
  const [recipientId, setRecipientId] = useState("");

  // Review notes.
  const [reviewNotes, setReviewNotes] = useState("");

  // Loading states.
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [reviewing, setReviewing] = useState(false);

  // Messages.
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  const selectedReport = reports.find(
    (report) => report.id === selectedReportId
  );

  const reportData = selectedReport?.report_data ?? {};
  const summary = reportData.summary ?? {};

  const approvedKnowledge = Array.isArray(reportData.approved_knowledge)
    ? reportData.approved_knowledge
    : [];

  const openWorkItems = Array.isArray(reportData.open_work_items)
    ? reportData.open_work_items
    : [];

  const continuityGaps = Array.isArray(reportData.continuity_gaps)
    ? reportData.continuity_gaps
    : [];

  const teamSnapshot = Array.isArray(reportData.team_snapshot)
    ? reportData.team_snapshot
    : [];

  const relationships = Array.isArray(reportData.approved_relationships)
    ? reportData.approved_relationships
    : [];

  const questions = Array.isArray(reportData.unresolved_questions)
    ? reportData.unresolved_questions
    : [];

  const nextSteps = Array.isArray(reportData.recommended_next_steps)
    ? reportData.recommended_next_steps
    : [];

  const qualityNotes = Array.isArray(reportData.quality_and_limitations)
    ? reportData.quality_and_limitations
    : [];

  // --------------------------------------------------
  // LOAD SAVED HANDOVER REPORTS
  // --------------------------------------------------

  async function loadReports() {
    if (!projectId) return;

    setLoading(true);
    setError("");

    try {
      const response = await api.get(
        `/api/projects/${projectId}/handovers`
      );

      const data: HandoverReport[] = Array.isArray(response.data)
        ? response.data
        : [];

      setReports(data);

      setSelectedReportId((currentId) => {
        if (currentId && data.some((report) => report.id === currentId)) {
          return currentId;
        }

        return data.length > 0 ? data[0].id : null;
      });
    } catch (err) {
      setError(getApiError(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadReports();
  }, [projectId]);

  // --------------------------------------------------
  // LOAD ACTIVE PROJECT MEMBERS
  // --------------------------------------------------

  useEffect(() => {
    let active = true;

    async function loadProjectMembers() {
      setMembers([]);
      setRecipientId("");

      if (!projectId) return;

      try {
        const response = await api.get<ProjectMemberOption[]>(
          `/api/projects/${projectId}/members`
        );

        if (!active) return;

        const data: ProjectMemberOption[] = Array.isArray(response.data)
          ? response.data
          : [];

        // Only active project members can receive handovers.
        setMembers(
          data.filter(
            (member) => member.membership_status === "active"
          )
        );
      } catch (err) {
        if (active) {
          setMembers([]);
          setError(getApiError(err));
        }
      }
    }

    void loadProjectMembers();

    return () => {
      active = false;
    };
  }, [projectId]);

  // --------------------------------------------------
  // GENERATE HANDOVER DRAFT
  // --------------------------------------------------

  async function generateReport() {
    setError("");
    setMessage("");
    setGenerating(true);

    const recipient = recipientId
      ? Number(recipientId)
      : null;

    try {
      const response = await api.post(
        `/api/projects/${projectId}/handovers`,
        {
          recipient_user_id: recipient,
        }
      );

      const newReport: HandoverReport = response.data;

      setSelectedReportId(newReport.id);
      setMessage("Handover draft generated successfully!");

      await loadReports();

      setSelectedReportId(newReport.id);

    } catch (err) {
      setError(getApiError(err));
    } finally {
      setGenerating(false);
    }
  }

  // --------------------------------------------------
  // APPROVE OR REJECT HANDOVER
  // --------------------------------------------------

  async function reviewReport(
    decision: "approved" | "rejected"
  ) {
    if (!selectedReport) return;

    setError("");
    setMessage("");
    setReviewing(true);

    try {
      await api.patch(
        `/api/projects/${projectId}/handovers/${selectedReport.id}/review`,
        {
          decision,
          review_notes: reviewNotes.trim() || null,
        }
      );

      setMessage(
        decision === "approved"
          ? "Handover report approved successfully."
          : "Handover report rejected."
      );

      setReviewNotes("");

      await loadReports();

    } catch (err) {
      setError(getApiError(err));
    } finally {
      setReviewing(false);
    }
  }

  // --------------------------------------------------
  // EXPORT HANDOVER AS MARKDOWN
  // --------------------------------------------------

  function downloadMarkdown() {
    if (!selectedReport) return;

    const lines: string[] = [];

    const addSection = (
      heading: string,
      body: string[]
    ) => {
      lines.push(`## ${heading}`, "", ...body, "");
    };

    lines.push(
      `# ${selectedReport.title}`,
      "",
      `**Status:** ${formatStatus(selectedReport.status)}`,
      "",
      `**Generated:** ${formatDate(reportData.generated_at)}`,
      "",
      `**Project:** ${reportData.project?.name ?? `Project ${projectId}`}`,
      "",
      `**Recipient:** ${reportData.recipient?.name ?? "Not specified"}`,
      ""
    );

    addSection("Summary", [
      `- Team members: ${summary.team_members ?? 0}`,
      `- Source documents referenced: ${summary.source_documents_referenced ?? 0}`,
      `- Approved knowledge items: ${summary.approved_knowledge_items ?? 0}`,
      `- Approved relationships: ${summary.approved_relationships ?? 0}`,
      `- Unfinished work items: ${summary.unfinished_work_items ?? 0}`,
      `- Continuity gaps: ${summary.continuity_gaps ?? 0}`,
      `- Unresolved questions: ${summary.unresolved_questions ?? 0}`,
    ]);

    addSection(
      "Team",
      teamSnapshot.length
        ? teamSnapshot.map(
            (member: any) =>
              `- ${member.name} — ${formatStatus(member.role)} — ${formatStatus(member.membership_status)}`
          )
        : ["No team records available."]
    );

    addSection(
      "Continuity gaps",
      continuityGaps.length
        ? continuityGaps.map(
            (item: any) =>
              `- **${item.title}** — ${item.assigned_to ?? "Unassigned"} — ${formatStatus(item.work_status)}`
          )
        : ["No approved continuity gaps found."]
    );

    addSection(
      "Unfinished work",
      openWorkItems.length
        ? openWorkItems.map(
            (item: any) =>
              `- **${item.title}** — ${item.assigned_to ?? "Unassigned"} — ${formatStatus(item.work_status)}`
          )
        : ["No unfinished work items found."]
    );

    addSection(
      "Approved knowledge",
      approvedKnowledge.length
        ? approvedKnowledge.map((item: any) => {
            const evidence = item.evidence ?? {};

            return [
              `### ${item.title}`,
              `- Type: ${formatStatus(item.type)}`,
              `- Status: ${formatStatus(item.work_status)}`,
              `- Assigned to: ${item.assigned_to ?? "Unassigned"}`,
              `- Source: ${evidence.document_name ?? "Not available"}`,
              `- Location: ${evidence.source_locator ?? "Not available"}`,
              `- Evidence: ${evidence.excerpt ?? "No excerpt available"}`,
            ].join("\n");
          })
        : ["No approved knowledge items found."]
    );

    addSection(
      "Approved relationships",
      relationships.length
        ? relationships.map(
            (item: any) =>
              `- ${item.source_title} → ${formatStatus(item.relationship_type)} → ${item.target_title}`
          )
        : ["No approved relationships found."]
    );

    addSection(
      "Unresolved questions",
      questions.length
        ? questions.map(
            (item: any) => `- ${item.title}`
          )
        : ["No unresolved questions found."]
    );

    addSection(
      "Recommended next steps",
      nextSteps.map(
        (step: string) => `- ${step}`
      )
    );

    addSection(
      "Quality and limitations",
      qualityNotes.map(
        (note: string) => `- ${note}`
      )
    );

    if (selectedReport.review_notes) {
      addSection(
        "Review notes",
        [selectedReport.review_notes]
      );
    }

    lines.push(
      "---",
      "",
      "*This report contains approved project records and evidence references. Recommendations are suggestions, not verified project facts.*"
    );

    const blob = new Blob(
      [lines.join("\n")],
      {
        type: "text/markdown;charset=utf-8",
      }
    );

    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");

    link.href = url;
    link.download = `relaymap-handover-${selectedReport.id}.md`;

    document.body.appendChild(link);
    link.click();
    link.remove();

    URL.revokeObjectURL(url);
  }

  // --------------------------------------------------
  // RENDER
  // --------------------------------------------------

  return (
    <div className="handover-page">

      {/* HEADER */}

      <div className="handover-header">
        <div>
          <div className="handover-eyebrow">
            <Sparkles size={15} />
            PROJECT CONTINUITY
          </div>

          <h1>Handover Center</h1>

          <p>
            Turn verified project knowledge into a structured handover
            for the next team member.
          </p>
        </div>

        <button
          className="handover-refresh-button"
          onClick={() => void loadReports()}
          disabled={loading}
        >
          <RefreshCw size={16} />
          Refresh
        </button>
      </div>

      {/* ALERTS */}

      {error && (
        <div className="handover-alert error">
          <AlertTriangle size={17} />
          {error}
        </div>
      )}

      {message && (
        <div className="handover-alert success">
          <CheckCircle2 size={17} />
          {message}
        </div>
      )}

      <div className="handover-layout">

        {/* LEFT SIDEBAR */}

        <aside className="handover-sidebar">

          {/* GENERATE HANDOVER */}

          <section className="handover-panel generate-panel">

            <div className="handover-panel-title">
              <Sparkles size={18} />
              <h2>Generate a handover</h2>
            </div>

            <p className="handover-muted">
              Create a new evidence-backed draft for this project.
            </p>

            {/* AUTOMATIC GENERATOR */}

            <div className="handover-automatic-user">
              <ShieldCheck size={16} />

              <span>
                Generated by your signed-in account automatically.
              </span>
            </div>

            {/* RECIPIENT DROPDOWN */}

            <label htmlFor="handover-recipient">
              Handover recipient
              <span>Optional</span>
            </label>

            <select
              id="handover-recipient"
              value={recipientId}
              onChange={(event) => setRecipientId(event.target.value)}
              disabled={members.length === 0}
            >
              <option value="">
                No recipient selected
              </option>

              {members.map((member) => (
                <option
                  key={member.user_id}
                  value={member.user_id}
                >
                  {member.full_name} — {formatStatus(member.role)}
                </option>
              ))}
            </select>

            {members.length === 0 && (
              <small className="handover-muted">
                No active project members are available for selection.
              </small>
            )}

            {/* GENERATE BUTTON */}

            <button
              className="handover-primary-button"
              onClick={() => void generateReport()}
              disabled={generating || loading}
            >
              {generating ? (
                <RefreshCw className="handover-spin" size={17} />
              ) : (
                <Sparkles size={17} />
              )}

              {generating
                ? "Generating..."
                : "Generate Draft"}
            </button>

            <div className="handover-safety-note">
              <ShieldCheck size={16} />

              <span>
                Generated reports remain drafts until reviewed and approved.
              </span>
            </div>

          </section>

          {/* SAVED REPORTS */}

          <section className="handover-panel report-list-panel">

            <div className="handover-panel-title">
              <FileText size={18} />

              <h2>Saved reports</h2>

              <span className="handover-count">
                {reports.length}
              </span>
            </div>

            {loading ? (
              <p className="handover-muted">
                Loading reports...
              </p>
            ) : reports.length === 0 ? (
              <div className="handover-empty-small">
                <FileText size={25} />

                <p>No handover reports yet.</p>

                <span>
                  Generate your first draft above.
                </span>
              </div>
            ) : (
              <div className="handover-report-list">

                {reports.map((report) => (
                  <button
                    key={report.id}
                    className={`handover-report-option ${
                      selectedReportId === report.id
                        ? "selected"
                        : ""
                    }`}
                    onClick={() => {
                      setSelectedReportId(report.id);
                      setReviewNotes("");
                    }}
                  >
                    <div className="handover-report-option-top">
                      <FileText size={17} />

                      <span
                        className={`handover-status ${report.status}`}
                      >
                        {formatStatus(report.status)}
                      </span>
                    </div>

                    <strong>{report.title}</strong>

                    <small>
                      {formatDate(report.created_at)}
                    </small>
                  </button>
                ))}

              </div>
            )}

          </section>

        </aside>

        {/* MAIN REPORT PREVIEW */}

        <main className="handover-main">

          {!selectedReport ? (

            <section className="handover-panel handover-empty">
              <FileText size={45} />

              <h2>Your handover preview will appear here</h2>

              <p>
                Generate a report to see approved project knowledge,
                unfinished work, evidence, and continuity gaps.
              </p>
            </section>

          ) : (

            <>

              {/* REPORT HEADER */}

              <section className="handover-panel report-preview">

                <div className="report-preview-header">
                  <div>
                    <div className="handover-eyebrow">
                      REPORT #{selectedReport.id}
                    </div>

                    <h2>{selectedReport.title}</h2>

                    <p className="handover-muted">
                      Generated {formatDate(reportData.generated_at)}
                    </p>
                  </div>

                  <span
                    className={`handover-status large ${selectedReport.status}`}
                  >
                    {selectedReport.status === "draft" && (
                      <Clock size={14} />
                    )}

                    {selectedReport.status === "approved" && (
                      <CheckCircle2 size={14} />
                    )}

                    {selectedReport.status === "rejected" && (
                      <XCircle size={14} />
                    )}

                    {formatStatus(selectedReport.status)}
                  </span>
                </div>

                {/* REPORT METADATA */}

                <div className="handover-meta">

                  <div>
                    <span>Project</span>

                    <strong>
                      {reportData.project?.name ??
                        `Project ${projectId}`}
                    </strong>
                  </div>

                  <div>
                    <span>Generated by</span>

                    <strong>
                      {reportData.generated_by?.name ??
                        `User #${selectedReport.generated_by_user_id}`}
                    </strong>
                  </div>

                  <div>
                    <span>Recipient</span>

                    <strong>
                      {reportData.recipient?.name ??
                        "Not specified"}
                    </strong>
                  </div>

                </div>

                <button
                  className="handover-export-button"
                  onClick={downloadMarkdown}
                >
                  <Download size={16} />
                  Export Markdown
                </button>

              </section>

              {/* REPORT STATISTICS */}

              <section className="handover-stats-grid">

                <div className="handover-stat-card">
                  <Users size={19} />

                  <strong>
                    {summary.team_members ?? 0}
                  </strong>

                  <span>Team members</span>
                </div>

                <div className="handover-stat-card">
                  <FileText size={19} />

                  <strong>
                    {summary.approved_knowledge_items ?? 0}
                  </strong>

                  <span>Verified knowledge</span>
                </div>

                <div className="handover-stat-card warning">
                  <AlertTriangle size={19} />

                  <strong>
                    {summary.continuity_gaps ?? 0}
                  </strong>

                  <span>Continuity gaps</span>
                </div>

                <div className="handover-stat-card">
                  <Network size={19} />

                  <strong>
                    {summary.approved_relationships ?? 0}
                  </strong>

                  <span>Relationships</span>
                </div>

              </section>

              {/* TEAM SNAPSHOT */}

              <section className="handover-panel">

                <div className="handover-section-heading">
                  <Users size={19} />
                  <h3>Team snapshot</h3>
                </div>

                {teamSnapshot.length === 0 ? (
                  <p className="handover-muted">
                    No team members available.
                  </p>
                ) : (
                  <div className="handover-team-list">

                    {teamSnapshot.map((member: any) => (
                      <div
                        className="handover-team-member"
                        key={member.user_id}
                      >
                        <div className="handover-avatar">
                          {String(member.name ?? "?")
                            .charAt(0)
                            .toUpperCase()}
                        </div>

                        <div>
                          <strong>{member.name}</strong>

                          <span>
                            {formatStatus(member.role)} ·{" "}
                            {formatStatus(member.membership_status)}
                          </span>
                        </div>
                      </div>
                    ))}

                  </div>
                )}

              </section>

              {/* CONTINUITY GAPS */}

              <section className="handover-panel">

                <div className="handover-section-heading">
                  <AlertTriangle size={19} />

                  <h3>Continuity gaps</h3>

                  <span className="handover-count">
                    {continuityGaps.length}
                  </span>
                </div>

                <p className="handover-muted">
                  Approved unfinished work assigned to departing or
                  departed members.
                </p>

                {continuityGaps.length === 0 ? (
                  <p className="handover-empty-inline">
                    No approved continuity gaps were found in this snapshot.
                  </p>
                ) : (
                  <div className="handover-item-list">

                    {continuityGaps.map((item: any) => (
                      <article
                        className="handover-knowledge-item gap-item"
                        key={item.id}
                      >
                        <div className="handover-item-heading">
                          <strong>{item.title}</strong>

                          <span className="handover-status warning">
                            {formatStatus(item.work_status)}
                          </span>
                        </div>

                        <p>
                          {item.description ||
                            "No description recorded."}
                        </p>

                        <small>
                          Assigned to: {item.assigned_to ?? "Unknown"}
                        </small>

                        {item.evidence?.excerpt && (
                          <blockquote>
                            “{item.evidence.excerpt}”
                          </blockquote>
                        )}

                        <small>
                          Source:{" "}
                          {item.evidence?.document_name ?? "Unavailable"}

                          {item.evidence?.source_locator
                            ? ` · ${item.evidence.source_locator}`
                            : ""}
                        </small>
                      </article>
                    ))}

                  </div>
                )}

              </section>

              {/* OTHER UNFINISHED WORK */}

              <section className="handover-panel">

                <div className="handover-section-heading">
                  <Clock size={19} />

                  <h3>Other unfinished work</h3>

                  <span className="handover-count">
                    {openWorkItems.length}
                  </span>
                </div>

                {openWorkItems.length === 0 ? (
                  <p className="handover-empty-inline">
                    No approved unfinished work items found.
                  </p>
                ) : (
                  <div className="handover-item-list">

                    {openWorkItems.map((item: any) => (
                      <article
                        className="handover-knowledge-item"
                        key={item.id}
                      >
                        <div className="handover-item-heading">
                          <strong>{item.title}</strong>

                          <span className="handover-status warning">
                            {formatStatus(item.work_status)}
                          </span>
                        </div>

                        <p>
                          {item.description ||
                            "No description recorded."}
                        </p>

                        <small>
                          Owner: {item.assigned_to ?? "Unassigned"}
                        </small>
                      </article>
                    ))}

                  </div>
                )}

              </section>

              {/* APPROVED PROJECT KNOWLEDGE */}

              <section className="handover-panel">

                <div className="handover-section-heading">
                  <ShieldCheck size={19} />

                  <h3>Approved project knowledge</h3>

                  <span className="handover-count">
                    {approvedKnowledge.length}
                  </span>
                </div>

                {approvedKnowledge.length === 0 ? (
                  <p className="handover-empty-inline">
                    No approved knowledge items were available for this report.
                  </p>
                ) : (
                  <div className="handover-item-list">

                    {approvedKnowledge.map((item: any) => (
                      <article
                        className="handover-knowledge-item"
                        key={item.id}
                      >
                        <div className="handover-item-heading">
                          <strong>{item.title}</strong>

                          <span className="handover-type">
                            {formatStatus(item.type)}
                          </span>
                        </div>

                        <p>
                          {item.description ||
                            "No description recorded."}
                        </p>

                        <div className="handover-evidence">
                          <strong>Source evidence</strong>

                          <blockquote>
                            {item.evidence?.excerpt ||
                              "No source excerpt available."}
                          </blockquote>

                          <small>
                            {item.evidence?.document_name ??
                              "Source document unavailable"}

                            {item.evidence?.source_locator
                              ? ` · ${item.evidence.source_locator}`
                              : ""}
                          </small>
                        </div>
                      </article>
                    ))}

                  </div>
                )}

              </section>

              {/* APPROVED RELATIONSHIPS */}

              <section className="handover-panel">

                <div className="handover-section-heading">
                  <Network size={19} />

                  <h3>Approved relationships</h3>

                  <span className="handover-count">
                    {relationships.length}
                  </span>
                </div>

                {relationships.length === 0 ? (
                  <p className="handover-empty-inline">
                    No approved relationships available.
                  </p>
                ) : (
                  <div className="handover-relationship-list">

                    {relationships.map((relationship: any) => (
                      <div
                        className="handover-relationship"
                        key={relationship.id}
                      >
                        <strong>
                          {relationship.source_title}
                        </strong>

                        <span>
                          {formatStatus(relationship.relationship_type)}
                        </span>

                        <strong>
                          {relationship.target_title}
                        </strong>
                      </div>
                    ))}

                  </div>
                )}

              </section>

              {/* UNRESOLVED QUESTIONS */}

              <section className="handover-panel">

                <div className="handover-section-heading">
                  <FileText size={19} />
                  <h3>Unresolved questions</h3>
                </div>

                {questions.length === 0 ? (
                  <p className="handover-empty-inline">
                    No approved question records found.
                  </p>
                ) : (
                  <ul className="handover-simple-list">

                    {questions.map((question: any) => (
                      <li key={question.id}>
                        {question.title}
                      </li>
                    ))}

                  </ul>
                )}

              </section>

              {/* RECOMMENDED NEXT STEPS */}

              <section className="handover-panel">

                <div className="handover-section-heading">
                  <CheckCircle2 size={19} />
                  <h3>Recommended next steps</h3>
                </div>

                <ol className="handover-simple-list ordered">
                  {nextSteps.map((step: string, index: number) => (
                    <li key={index}>{step}</li>
                  ))}
                </ol>

              </section>

              {/* QUALITY AND LIMITATIONS */}

              <section className="handover-panel quality-panel">

                <div className="handover-section-heading">
                  <AlertTriangle size={19} />
                  <h3>Quality and limitations</h3>
                </div>

                <ul className="handover-simple-list">
                  {qualityNotes.map((note: string, index: number) => (
                    <li key={index}>{note}</li>
                  ))}
                </ul>

                <div className="handover-review-counts">
                  <span>
                    Pending: {summary.pending_knowledge_records ?? 0}
                  </span>

                  <span>
                    Needs clarification:{" "}
                    {summary.needs_clarification_records ?? 0}
                  </span>

                  <span>
                    Rejected: {summary.rejected_knowledge_records ?? 0}
                  </span>
                </div>

              </section>

              {/* HUMAN REVIEW */}

              {selectedReport.status === "draft" && (
                <section className="handover-panel review-panel">

                  <div className="handover-section-heading">
                    <ShieldCheck size={19} />
                    <h3>Human review required</h3>
                  </div>

                  <p className="handover-muted">
                    Review the source evidence and report content before
                    approving this handover.
                  </p>

                  {/* AUTOMATIC REVIEWER */}

                  <div className="handover-automatic-user">
                    <ShieldCheck size={16} />

                    <span>
                      Reviewer identity is taken from your signed-in account.
                    </span>
                  </div>

                  <label htmlFor="handover-review-notes">
                    Review notes
                  </label>

                  <textarea
                    id="handover-review-notes"
                    value={reviewNotes}
                    onChange={(event) => setReviewNotes(event.target.value)}
                    placeholder="Add your review comments..."
                    rows={3}
                  />

                  <div className="handover-review-actions">

                    <button
                      className="handover-approve-button"
                      onClick={() => void reviewReport("approved")}
                      disabled={reviewing}
                    >
                      <CheckCircle2 size={16} />
                      Approve Handover
                    </button>

                    <button
                      className="handover-reject-button"
                      onClick={() => void reviewReport("rejected")}
                      disabled={reviewing}
                    >
                      <XCircle size={16} />
                      Reject Draft
                    </button>

                  </div>

                </section>
              )}

              {/* REVIEWED REPORT */}

              {selectedReport.status !== "draft" && (
                <section className="handover-panel reviewed-panel">

                  <div className="handover-section-heading">
                    {selectedReport.status === "approved" ? (
                      <CheckCircle2 size={19} />
                    ) : (
                      <XCircle size={19} />
                    )}

                    <h3>
                      Handover {formatStatus(selectedReport.status)}
                    </h3>
                  </div>

                  <p>
                    Reviewed by user #{selectedReport.reviewed_by_user_id}
                    {" · "}
                    {formatDate(selectedReport.reviewed_at)}
                  </p>

                  {selectedReport.review_notes && (
                    <blockquote>
                      {selectedReport.review_notes}
                    </blockquote>
                  )}

                </section>
              )}

            </>
          )}

        </main>
      </div>
    </div>
  );
}