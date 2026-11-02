
import { useEffect, useMemo, useState } from "react";
import {
  CheckCircle2,
  CircleAlert,
  Clock,
  FileText,
  RefreshCw,
  ShieldCheck,
  XCircle,
  HelpCircle,
  UserCheck,
} from "lucide-react";

import { api, getApiError } from "../services/api";
import "./KnowledgeReview.css";

interface KnowledgeItem {
  id: number;
  project_id: number;
  document_id: number;
  chunk_id: number;

  item_type: string;
  title: string;
  description: string;
  source_excerpt: string;

  source_locator: string;
  original_filename: string;

  candidate_owner_mention: string | null;
  assigned_to_user_id: number | null;

  work_status: string;
  review_status: string;

  reviewed_by_user_id: number | null;
  reviewed_at: string | null;
  review_notes: string | null;

  extraction_method: string;
  created_at: string;
}

interface ProjectMemberOption {
  user_id: number;
  full_name: string;
  role: string;
  membership_status?: string;
}

interface KnowledgeReviewProps {
  projectId: number;
  members: ProjectMemberOption[];
}

interface ReviewDraft {
  workStatus: string;
  assignedToUserId: string;
  notes: string;
}

type ReviewDecision =
  | "approved"
  | "rejected"
  | "needs_clarification";

const ITEM_TYPES = [
  "task",
  "decision",
  "responsibility",
  "dependency",
  "blocker",
  "question",
];

const WORK_STATUSES = [
  "unknown",
  "open",
  "in_progress",
  "completed",
  "blocked",
];

const REVIEW_STATUSES = [
  "pending",
  "approved",
  "rejected",
  "needs_clarification",
];

function KnowledgeReview({
  projectId,
  members,
}: KnowledgeReviewProps) {
  const [items, setItems] = useState<KnowledgeItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [reviewingId, setReviewingId] = useState<number | null>(null);

  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  const [typeFilter, setTypeFilter] = useState("all");
  const [statusFilter, setStatusFilter] = useState("pending");

  const [reviewerId, setReviewerId] = useState("");

  const [drafts, setDrafts] = useState<
    Record<number, ReviewDraft>
  >({});

  // Only active owners and admins can review records.
  const reviewers = useMemo(
    () =>
      members.filter(
        (member) =>
          ["owner", "admin"].includes(member.role) &&
          member.membership_status !== "departed"
      ),
    [members]
  );

  // Assign a default reviewer when the project members load.
  useEffect(() => {
    if (
      reviewerId &&
      reviewers.some(
        (member) => String(member.user_id) === reviewerId
      )
    ) {
      return;
    }

    const preferredReviewer =
      reviewers.find((member) => member.role === "owner") ??
      reviewers[0];

    setReviewerId(
      preferredReviewer ? String(preferredReviewer.user_id) : ""
    );
  }, [reviewers, reviewerId]);

  // Fetch knowledge records from FastAPI.
  async function loadKnowledge() {
    setLoading(true);
    setError("");

    try {
      const response = await api.get<KnowledgeItem[]>(
        `/api/projects/${projectId}/knowledge`
      );

      setItems(response.data);

      setDrafts((previous) => {
        const updated = { ...previous };

        for (const item of response.data) {
          if (!updated[item.id]) {
            updated[item.id] = {
              workStatus: item.work_status || "unknown",
              assignedToUserId: item.assigned_to_user_id
                ? String(item.assigned_to_user_id)
                : "",
              notes: item.review_notes || "",
            };
          }
        }

        return updated;
      });
    } catch (err) {
      setError(getApiError(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadKnowledge();
  }, [projectId]);

  // Update a draft for one knowledge record.
  function updateDraft(
  itemId: number,
  field: keyof ReviewDraft,
  value: string
) {
  setDrafts((previous) => {
    const currentDraft = previous[itemId] ?? {
      workStatus: "unknown",
      assignedToUserId: "",
      notes: "",
    };

    return {
      ...previous,
      [itemId]: {
        ...currentDraft,
        [field]: value,
      },
    };
  });
}

  // Submit a human review decision.
  async function handleReview(
    item: KnowledgeItem,
    decision: ReviewDecision
  ) {
    if (!reviewerId) {
      setError(
        "No eligible project owner or admin is available to review this record."
      );
      return;
    }

    const draft = drafts[item.id] ?? {
      workStatus: "unknown",
      assignedToUserId: "",
      notes: "",
    };

    setError("");
    setSuccess("");
    setReviewingId(item.id);

    const payload: {
      review_status: ReviewDecision;
      reviewed_by_user_id: number;
      review_notes: string | null;
      work_status?: string;
      assigned_to_user_id?: number | null;
    } = {
      review_status: decision,
      reviewed_by_user_id: Number(reviewerId),
      review_notes: draft.notes.trim() || null,
    };

    if (decision === "approved") {
      payload.work_status = draft.workStatus;
      payload.assigned_to_user_id = draft.assignedToUserId
        ? Number(draft.assignedToUserId)
        : null;
    }

    try {
      const response = await api.patch(
        `/api/projects/${projectId}/knowledge/${item.id}/review`,
        payload
      );

      const updated = response.data;

      setItems((previous) =>
        previous.map((existing) =>
          existing.id === item.id
            ? {
                ...existing,
                review_status: updated.review_status,
                work_status: updated.work_status,
                assigned_to_user_id: updated.assigned_to_user_id,
                reviewed_by_user_id: updated.reviewed_by_user_id,
                reviewed_at: updated.reviewed_at,
                review_notes: updated.review_notes,
              }
            : existing
        )
      );

      const decisionText = {
        approved: "approved",
        rejected: "rejected",
        needs_clarification: "marked for clarification",
      }[decision];

      setSuccess(`Knowledge item #${item.id} ${decisionText}.`);
    } catch (err) {
      setError(getApiError(err));
    } finally {
      setReviewingId(null);
    }
  }

  // Apply the selected filters.
  const filteredItems = useMemo(() => {
    return items.filter((item) => {
      const matchesType =
        typeFilter === "all" || item.item_type === typeFilter;

      const matchesStatus =
        statusFilter === "all" ||
        item.review_status === statusFilter;

      return matchesType && matchesStatus;
    });
  }, [items, typeFilter, statusFilter]);

  const pendingCount = items.filter(
    (item) => item.review_status === "pending"
  ).length;

  const approvedCount = items.filter(
    (item) => item.review_status === "approved"
  ).length;

  const clarificationCount = items.filter(
    (item) => item.review_status === "needs_clarification"
  ).length;

  const rejectedCount = items.filter(
    (item) => item.review_status === "rejected"
  ).length;

  return (
    <section className="knowledge-page">

      {/* PAGE INTRODUCTION */}

      <div className="knowledge-intro">
        <div>
          <div className="knowledge-eyebrow">
            <ShieldCheck size={15} />
            EVIDENCE VERIFICATION
          </div>

          <h2>Knowledge Review</h2>

          <p>
            Review extracted project information, inspect its evidence,
            and decide which records are ready to become verified
            project knowledge.
          </p>
        </div>

        <button
          type="button"
          className="knowledge-refresh"
          onClick={() => void loadKnowledge()}
          disabled={loading}
        >
          <RefreshCw
            size={16}
            className={loading ? "knowledge-spinning" : ""}
          />
          Refresh
        </button>
      </div>

      {/* SUMMARY CARDS */}

      <div className="knowledge-stats">

        <div className="knowledge-stat">
          <span>Pending Review</span>
          <strong>{pendingCount}</strong>
          <small>Awaiting human verification</small>
        </div>

        <div className="knowledge-stat">
          <span>Approved</span>
          <strong>{approvedCount}</strong>
          <small>Verified records</small>
        </div>

        <div className="knowledge-stat">
          <span>Needs Clarification</span>
          <strong>{clarificationCount}</strong>
          <small>Require more context</small>
        </div>

        <div className="knowledge-stat">
          <span>Rejected</span>
          <strong>{rejectedCount}</strong>
          <small>Not accepted as knowledge</small>
        </div>

      </div>

      {/* REVIEWER SELECTION */}

      <div className="reviewer-panel">
        <div className="reviewer-icon">
          <UserCheck size={20} />
        </div>

        <div className="reviewer-description">
          <strong>Current Reviewer</strong>
          <span>
            Only project owners and admins are eligible in this local
            review workflow.
          </span>
        </div>

        <select
          value={reviewerId}
          onChange={(event) => setReviewerId(event.target.value)}
          disabled={reviewers.length === 0}
        >
          <option value="">Select reviewer</option>

          {reviewers.map((member) => (
            <option
              key={member.user_id}
              value={member.user_id}
            >
              {member.full_name} — {member.role}
            </option>
          ))}
        </select>
      </div>

      {reviewers.length === 0 && (
        <div className="knowledge-error">
          No active project owner or admin is available to review records.
        </div>
      )}

      {/* ALERTS */}

      {error && (
        <div className="knowledge-error">
          <CircleAlert size={17} />
          <span>{error}</span>
        </div>
      )}

      {success && (
        <div className="knowledge-success">
          <CheckCircle2 size={17} />
          <span>{success}</span>
        </div>
      )}

      {/* FILTERS */}

      <div className="knowledge-filters">

        <div>
          <label htmlFor="knowledge-type-filter">
            Knowledge Category
          </label>

          <select
            id="knowledge-type-filter"
            value={typeFilter}
            onChange={(event) => setTypeFilter(event.target.value)}
          >
            <option value="all">All Categories</option>

            {ITEM_TYPES.map((type) => (
              <option key={type} value={type}>
                {type.charAt(0).toUpperCase() + type.slice(1)}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label htmlFor="knowledge-status-filter">
            Review Status
          </label>

          <select
            id="knowledge-status-filter"
            value={statusFilter}
            onChange={(event) => setStatusFilter(event.target.value)}
          >
            <option value="all">All Statuses</option>

            {REVIEW_STATUSES.map((status) => (
              <option key={status} value={status}>
                {status.replace("_", " ")}
              </option>
            ))}
          </select>
        </div>

        <div className="knowledge-result-count">
          {filteredItems.length} records shown
        </div>

      </div>

      {/* KNOWLEDGE RECORDS */}

      {loading ? (

        <div className="knowledge-empty">
          <RefreshCw size={27} className="knowledge-spinning" />
          <h3>Loading project knowledge...</h3>
        </div>

      ) : filteredItems.length === 0 ? (

        <div className="knowledge-empty">
          <FileText size={38} />

          <h3>No knowledge records found</h3>

          <p>
            Try changing the filters or extract knowledge from an uploaded
            document first.
          </p>
        </div>

      ) : (

        <div className="knowledge-list">

          {filteredItems.map((item) => {
            const draft = drafts[item.id] ?? {
              workStatus: item.work_status || "unknown",
              assignedToUserId: "",
              notes: item.review_notes || "",
            };

            const isReviewing = reviewingId === item.id;

            return (
              <article
                className="knowledge-card"
                key={item.id}
              >

                {/* RECORD HEADER */}

                <div className="knowledge-card-header">

                  <div className="knowledge-card-labels">

                    <span className={`knowledge-type type-${item.item_type}`}>
                      {item.item_type}
                    </span>

                    <span className={`knowledge-status status-${item.review_status}`}>
                      {item.review_status.replace("_", " ")}
                    </span>

                  </div>

                  <span className="knowledge-record-id">
                    Record #{item.id}
                  </span>

                </div>

                {/* RECORD CONTENT */}

                <h3>{item.title}</h3>

                <p className="knowledge-description">
                  {item.description}
                </p>

                {item.candidate_owner_mention && (
                  <div className="candidate-owner">
                    <strong>Candidate owner mention:</strong>{" "}
                    {item.candidate_owner_mention}
                    <small>
                      This is an unverified name extracted from the source.
                    </small>
                  </div>
                )}

                {/* EVIDENCE */}

                <div className="evidence-panel">

                  <div className="evidence-heading">
                    <FileText size={16} />
                    <strong>Supporting Evidence</strong>
                  </div>

                  <p>{item.source_excerpt}</p>

                  <div className="evidence-source">
                    <span>{item.original_filename}</span>
                    <span>{item.source_locator}</span>
                  </div>

                </div>

                {/* CURRENT REVIEW DETAILS */}

                {item.review_status !== "pending" && (
                  <div className="previous-review">
                    <Clock size={15} />

                    <span>
                      Reviewed:{" "}
                      {item.reviewed_at
                        ? new Date(item.reviewed_at).toLocaleString()
                        : "Date unavailable"}
                    </span>

                    <span>
                      Work status: {item.work_status.replace("_", " ")}
                    </span>
                  </div>
                )}

                {/* REVIEW ACTIONS */}

                {item.review_status === "pending" ? (

                  <div className="knowledge-review-form">

                    <div className="knowledge-field-grid">

                      <div>
                        <label htmlFor={`work-status-${item.id}`}>
                          Verified Work Status
                        </label>

                        <select
                          id={`work-status-${item.id}`}
                          value={draft.workStatus}
                          onChange={(event) =>
                            updateDraft(
                              item.id,
                              "workStatus",
                              event.target.value
                            )
                          }
                        >
                          {WORK_STATUSES.map((status) => (
                            <option key={status} value={status}>
                              {status.replace("_", " ")}
                            </option>
                          ))}
                        </select>
                      </div>

                      <div>
                        <label htmlFor={`assigned-user-${item.id}`}>
                          Verified Owner (optional)
                        </label>

                        <select
                          id={`assigned-user-${item.id}`}
                          value={draft.assignedToUserId}
                          onChange={(event) =>
                            updateDraft(
                              item.id,
                              "assignedToUserId",
                              event.target.value
                            )
                          }
                        >
                          <option value="">No verified owner</option>

                          {members
                            .filter(
                              (member) =>
                                ["owner", "admin", "member"].includes(
                                  member.role
                                ) &&
                                member.membership_status !== "departed"
                            )
                            .map((member) => (
                              <option
                                key={member.user_id}
                                value={member.user_id}
                              >
                                {member.full_name}
                              </option>
                            ))}
                        </select>
                      </div>

                    </div>

                    <label htmlFor={`review-notes-${item.id}`}>
                      Review Notes
                    </label>

                    <textarea
                      id={`review-notes-${item.id}`}
                      rows={2}
                      maxLength={5000}
                      value={draft.notes}
                      onChange={(event) =>
                        updateDraft(
                          item.id,
                          "notes",
                          event.target.value
                        )
                      }
                      placeholder="Explain why this record is accepted, rejected or needs clarification..."
                    />

                    <div className="knowledge-actions">

                      <button
                        type="button"
                        className="review-approve"
                        disabled={isReviewing || !reviewerId}
                        onClick={() =>
                          void handleReview(item, "approved")
                        }
                      >
                        <CheckCircle2 size={16} />
                        Approve
                      </button>

                      <button
                        type="button"
                        className="review-clarify"
                        disabled={isReviewing || !reviewerId}
                        onClick={() =>
                          void handleReview(
                            item,
                            "needs_clarification"
                          )
                        }
                      >
                        <HelpCircle size={16} />
                        Clarify
                      </button>

                      <button
                        type="button"
                        className="review-reject"
                        disabled={isReviewing || !reviewerId}
                        onClick={() =>
                          void handleReview(item, "rejected")
                        }
                      >
                        <XCircle size={16} />
                        Reject
                      </button>

                      {isReviewing && (
                        <span className="review-saving">
                          Saving review...
                        </span>
                      )}

                    </div>

                  </div>

                ) : (

                  <div className="review-completed">
                    <CheckCircle2 size={16} />

                    <span>
                      Review decision:{" "}
                      {item.review_status.replace("_", " ")}
                    </span>

                    {item.review_notes && (
                      <p>{item.review_notes}</p>
                    )}
                  </div>

                )}

              </article>
            );
          })}

        </div>

      )}

      <div className="knowledge-footer-note">
        Extracted records are candidates, not established facts. Approval
        records a human review decision; supporting evidence remains
        attached to every item.
      </div>

    </section>
  );
}

export default KnowledgeReview;