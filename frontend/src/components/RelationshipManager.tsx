
import { useCallback, useEffect, useState, type FormEvent } from "react";

import {
  CheckCircle2,
  CircleAlert,
  Clock,
  FileText,
  GitBranch,
  RefreshCw,
  XCircle,
} from "lucide-react";

import { api, getApiError } from "../services/api";
import "./RelationshipManager.css";

interface KnowledgeItem {
  id: number;
  project_id: number;
  document_id: number;
  chunk_id: number;
  item_type: string;
  title: string;
  review_status: string;
}

interface ProjectDocument {
  id: number;
  original_filename: string;
}

interface DocumentChunk {
  id: number;
  document_id: number;
  chunk_index: number;
  source_locator: string;
  chunk_text: string;
}

interface EvidenceOption extends DocumentChunk {
  original_filename: string;
}

interface ProjectMemberOption {
  user_id: number;
  full_name: string;
  role: string;
  membership_status: string;
}

interface Relationship {
  id: number;
  project_id: number;
  source_item_id: number;
  source_item_title: string;
  target_item_id: number;
  target_item_title: string;
  relation_type: string;
  evidence_chunk_id: number;
  evidence_excerpt: string;
  evidence_locator: string;
  original_filename: string;
  review_status: string;
  review_notes: string | null;
}

interface RelationshipManagerProps {
  projectId: number;
  onChanged: () => void;
}

const RELATION_TYPES = [
  {
    value: "depends_on",
    label: "Depends on",
    description: "The source item needs the target item first.",
  },
  {
    value: "blocks",
    label: "Blocks",
    description: "The source item blocks progress on the target.",
  },
  {
    value: "related_to",
    label: "Related to",
    description: "The two items are connected in the project.",
  },
  {
    value: "supports",
    label: "Supports",
    description: "The source item supports the target item.",
  },
  {
    value: "informs",
    label: "Informs",
    description: "The source item provides information for the target.",
  },
];

function RelationshipManager({
  projectId,
  onChanged,
}: RelationshipManagerProps) {
  const [knowledgeItems, setKnowledgeItems] = useState<KnowledgeItem[]>([]);
  const [evidenceChunks, setEvidenceChunks] = useState<EvidenceOption[]>([]);
  const [members, setMembers] = useState<ProjectMemberOption[]>([]);

  const [pendingRelationships, setPendingRelationships] =
    useState<Relationship[]>([]);

  const [approvedRelationships, setApprovedRelationships] =
    useState<Relationship[]>([]);

  const [sourceItemId, setSourceItemId] = useState("");
  const [targetItemId, setTargetItemId] = useState("");
  const [relationType, setRelationType] = useState("depends_on");
  const [evidenceChunkId, setEvidenceChunkId] = useState("");
  const [reviewerId, setReviewerId] = useState("");

  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [suggesting, setSuggesting] = useState(false);
  const [reviewingId, setReviewingId] = useState<number | null>(null);

  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  const reviewers = members.filter(
    (member) =>
      ["owner", "admin"].includes(member.role) &&
      member.membership_status === "active"
  );

  const selectedChunk = evidenceChunks.find(
    (chunk) => String(chunk.id) === evidenceChunkId
  );

  const availableTargets = knowledgeItems.filter(
    (item) => String(item.id) !== sourceItemId
  );

  // --------------------------------------------------
  // LOAD PROJECT KNOWLEDGE, EVIDENCE AND RELATIONSHIPS
  // --------------------------------------------------

  const loadData = useCallback(async () => {
    setLoading(true);
    setError("");

    try {
      const [
        knowledgeResponse,
        documentsResponse,
        membersResponse,
        pendingResponse,
        approvedResponse,
      ] = await Promise.all([
        api.get<KnowledgeItem[]>(
          `/api/projects/${projectId}/knowledge?review_status=approved`
        ),
        api.get<ProjectDocument[]>(
          `/api/projects/${projectId}/documents`
        ),
        api.get<ProjectMemberOption[]>(
          `/api/projects/${projectId}/members`
        ),
        api.get<Relationship[]>(
          `/api/projects/${projectId}/relationships?review_status=pending`
        ),
        api.get<Relationship[]>(
          `/api/projects/${projectId}/relationships?review_status=approved`
        ),
      ]);

      const documents = documentsResponse.data;

      // Retrieve evidence chunks for every project document.
      const chunkResults = await Promise.all(
        documents.map(async (document) => {
          try {
            const response = await api.get<DocumentChunk[]>(
              `/api/projects/${projectId}/documents/${document.id}/chunks`
            );

            return response.data.map((chunk) => ({
              ...chunk,
              original_filename: document.original_filename,
            }));
          } catch {
            // One document's missing chunks should not hide other evidence.
            return [];
          }
        })
      );

      const allChunks = chunkResults.flat();

      setKnowledgeItems(knowledgeResponse.data);
      setEvidenceChunks(allChunks);
      setMembers(membersResponse.data);
      setPendingRelationships(pendingResponse.data);
      setApprovedRelationships(approvedResponse.data);

      setSourceItemId((current) =>
        current || (
          knowledgeResponse.data[0]
            ? String(knowledgeResponse.data[0].id)
            : ""
        )
      );

      setEvidenceChunkId((current) =>
        current || (
          allChunks[0] ? String(allChunks[0].id) : ""
        )
      );

      setReviewerId((current) => {
        if (
          current &&
          membersResponse.data.some(
            (member) =>
              String(member.user_id) === current &&
              ["owner", "admin"].includes(member.role) &&
              member.membership_status === "active"
          )
        ) {
          return current;
        }

        const owner =
          membersResponse.data.find(
            (member) =>
              member.role === "owner" &&
              member.membership_status === "active"
          ) ??
          membersResponse.data.find(
            (member) =>
              member.role === "admin" &&
              member.membership_status === "active"
          );

        return owner ? String(owner.user_id) : "";
      });

    } catch (err) {
      setError(getApiError(err));
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  // --------------------------------------------------
// AUTOMATIC RELATIONSHIP SUGGESTIONS
// --------------------------------------------------

async function handleSuggestRelationships() {
  setError("");
  setSuccess("");
  setSuggesting(true);

  try {
    const response = await api.post<{
      project_id: number;
      approved_knowledge_items: number;
      chunks_scanned: number;
      candidates_detected: number;
      suggestions_created: number;
      duplicates_skipped: number;
      message: string;
    }>(
      `/api/projects/${projectId}/relationships/suggest`
    );

    const result = response.data;

    setSuccess(
      `${result.suggestions_created} new suggestions created. ` +
      `${result.duplicates_skipped} duplicates skipped. ` +
      `${result.chunks_scanned} document chunks scanned.`
    );

    // Reload pending and approved relationships.
    await loadData();

    // Notify the parent to refresh the Knowledge Map.
    onChanged();

  } catch (err) {
    setError(getApiError(err));
  } finally {
    setSuggesting(false);
  }
}

  // --------------------------------------------------
  // CREATE RELATIONSHIP CANDIDATE
  // --------------------------------------------------

  async function createRelationship(
    event: FormEvent<HTMLFormElement>
  ) {
    event.preventDefault();

    setError("");
    setSuccess("");

    if (!sourceItemId || !targetItemId || !evidenceChunkId) {
      setError("Select two knowledge items and an evidence chunk.");
      return;
    }

    if (sourceItemId === targetItemId) {
      setError("Choose two different knowledge items.");
      return;
    }

    if (!reviewerId) {
      setError("An active project owner or admin is required.");
      return;
    }

    if (!selectedChunk) {
      setError("The selected evidence chunk could not be found.");
      return;
    }

    setSubmitting(true);

    try {
      await api.post(
        `/api/projects/${projectId}/relationships`,
        {
          source_item_id: Number(sourceItemId),
          target_item_id: Number(targetItemId),
          relation_type: relationType,
          evidence_chunk_id: selectedChunk.id,
          evidence_excerpt: selectedChunk.chunk_text,
          created_by_user_id: Number(reviewerId),
        }
      );

      setSuccess(
        "Relationship candidate created. It is awaiting human review."
      );

      await loadData();

    } catch (err) {
      setError(getApiError(err));
    } finally {
      setSubmitting(false);
    }
  }

  // --------------------------------------------------
  // APPROVE OR REJECT RELATIONSHIP
  // --------------------------------------------------

  async function reviewRelationship(
    relationship: Relationship,
    decision: "approved" | "rejected"
  ) {
    if (!reviewerId) {
      setError("Select an active project owner or admin.");
      return;
    }

    setError("");
    setSuccess("");
    setReviewingId(relationship.id);

    try {
      await api.patch(
        `/api/projects/${projectId}/relationships/${relationship.id}/review`,
        {
          review_status: decision,
          reviewed_by_user_id: Number(reviewerId),
          review_notes:
            decision === "approved"
              ? "Relationship verified against the cited source evidence."
              : "Relationship rejected during human verification.",
        }
      );

      setSuccess(
        decision === "approved"
          ? "Relationship approved and added to the Knowledge Map."
          : "Relationship rejected."
      );

      await loadData();

      if (decision === "approved") {
        onChanged();
      }

    } catch (err) {
      setError(getApiError(err));
    } finally {
      setReviewingId(null);
    }
  }

  const selectedRelation = RELATION_TYPES.find(
    (relation) => relation.value === relationType
  );

  // --------------------------------------------------
  // RENDER
  // --------------------------------------------------

  return (
    <section className="relationship-manager">

      <div className="relationship-manager-heading">
  <div>
    <div className="relationship-eyebrow">
      <GitBranch size={15} />
      RELATIONSHIP MANAGEMENT
    </div>

    <h3>Build Knowledge Connections</h3>

    <p>
      Connect approved knowledge records using exact source
      evidence. Automatically discover potential connections
      and review them before adding them to the graph.
    </p>
  </div>

  <div className="relationship-heading-actions">

    <button
      type="button"
      className="relationship-suggest-button"
      onClick={() => void handleSuggestRelationships()}
      disabled={
        suggesting ||
        loading ||
        knowledgeItems.length < 2 ||
        evidenceChunks.length === 0
      }
    >
      <GitBranch size={15} />
      {suggesting ? "Scanning Documents..." : "Suggest Relationships"}
    </button>

    <button
      type="button"
      className="relationship-refresh"
      onClick={() => void loadData()}
      disabled={loading || suggesting}
    >
      <RefreshCw size={15} />
      Refresh
    </button>

  </div>
</div>

      {/* ALERTS */}

      {error && (
        <div className="relationship-alert relationship-error">
          <CircleAlert size={16} />
          {error}
        </div>
      )}

      {success && (
        <div className="relationship-alert relationship-success">
          <CheckCircle2 size={16} />
          {success}
        </div>
      )}

      {/* CONNECTION SUMMARY */}

      <div className="relationship-summary">
        <div>
          <span>Approved connections</span>
          <strong>{approvedRelationships.length}</strong>
        </div>

        <div>
          <span>Pending review</span>
          <strong>{pendingRelationships.length}</strong>
        </div>

        <div>
          <span>Approved knowledge</span>
          <strong>{knowledgeItems.length}</strong>
        </div>
      </div>

      {/* CREATION FORM */}

      <div className="relationship-form-card">

        <div className="relationship-section-title">
          <GitBranch size={19} />
          <div>
            <h4>Create a Relationship</h4>
            <p>
              Select the two approved records that you want to connect.
            </p>
          </div>
        </div>

        {loading ? (

          <p className="relationship-muted">Loading project evidence...</p>

        ) : knowledgeItems.length < 2 ? (

          <div className="relationship-empty">
            <FileText size={27} />
            <strong>At least two approved knowledge records are required.</strong>
            <span>Approve additional items in Knowledge Review first.</span>
          </div>

        ) : evidenceChunks.length === 0 ? (

          <div className="relationship-empty">
            <FileText size={27} />
            <strong>No evidence chunks available.</strong>
            <span>Check that your uploaded documents have been chunked.</span>
          </div>

        ) : (

          <form
            className="relationship-form"
            onSubmit={createRelationship}
          >

            <div className="relationship-fields">

              <div>
                <label htmlFor="relationship-source">
                  Source Knowledge Item
                </label>

                <select
                  id="relationship-source"
                  value={sourceItemId}
                  onChange={(event) =>
                    setSourceItemId(event.target.value)
                  }
                  required
                >
                  <option value="">Select source item</option>

                  {knowledgeItems.map((item) => (
                    <option key={item.id} value={item.id}>
                      #{item.id} · {item.title}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label htmlFor="relationship-type">
                  Relationship Type
                </label>

                <select
                  id="relationship-type"
                  value={relationType}
                  onChange={(event) =>
                    setRelationType(event.target.value)
                  }
                >
                  {RELATION_TYPES.map((relation) => (
                    <option
                      key={relation.value}
                      value={relation.value}
                    >
                      {relation.label}
                    </option>
                  ))}
                </select>

                {selectedRelation && (
                  <small>{selectedRelation.description}</small>
                )}
              </div>

              <div>
                <label htmlFor="relationship-target">
                  Target Knowledge Item
                </label>

                <select
                  id="relationship-target"
                  value={targetItemId}
                  onChange={(event) =>
                    setTargetItemId(event.target.value)
                  }
                  required
                >
                  <option value="">Select target item</option>

                  {availableTargets.map((item) => (
                    <option key={item.id} value={item.id}>
                      #{item.id} · {item.title}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label htmlFor="relationship-evidence">
                  Supporting Evidence
                </label>

                <select
                  id="relationship-evidence"
                  value={evidenceChunkId}
                  onChange={(event) =>
                    setEvidenceChunkId(event.target.value)
                  }
                  required
                >
                  <option value="">Select evidence passage</option>

                  {evidenceChunks.map((chunk) => (
                    <option key={chunk.id} value={chunk.id}>
                      {chunk.original_filename} · {chunk.source_locator}
                    </option>
                  ))}
                </select>
              </div>

            </div>

            {selectedChunk && (
              <div className="relationship-evidence">

                <div className="relationship-evidence-heading">
                  <FileText size={15} />
                  <strong>Exact supporting source text</strong>
                </div>

                <p>{selectedChunk.chunk_text}</p>

                <div className="relationship-evidence-source">
                  {selectedChunk.original_filename}
                  {" · "}
                  {selectedChunk.source_locator}
                </div>

                <small>
                  This exact chunk text will be attached to the
                  relationship. Confirm that it genuinely supports
                  the selected connection.
                </small>

              </div>
            )}

            <div>
              <label htmlFor="relationship-reviewer">
                Created By / Reviewer
              </label>

              <select
                id="relationship-reviewer"
                value={reviewerId}
                onChange={(event) =>
                  setReviewerId(event.target.value)
                }
                required
              >
                <option value="">Select owner or admin</option>

                {reviewers.map((member) => (
                  <option
                    key={member.user_id}
                    value={member.user_id}
                  >
                    {member.full_name} · {member.role}
                  </option>
                ))}
              </select>
            </div>

            <button
              type="submit"
              className="relationship-create-button"
              disabled={
                submitting ||
                !sourceItemId ||
                !targetItemId ||
                !evidenceChunkId ||
                !reviewerId ||
                knowledgeItems.length < 2
              }
            >
              <GitBranch size={16} />
              {submitting
                ? "Creating..."
                : "Create Pending Relationship"}
            </button>

          </form>

        )}

      </div>

      {/* PENDING RELATIONSHIPS */}

      <div className="relationship-list-section">

        <div className="relationship-section-title">
          <Clock size={19} />

          <div>
            <h4>Pending Relationship Review</h4>
            <p>Verify each proposed connection before it enters the graph.</p>
          </div>
        </div>

        {loading ? (

          <p className="relationship-muted">Loading relationships...</p>

        ) : pendingRelationships.length === 0 ? (

          <div className="relationship-empty">
            <CheckCircle2 size={27} />
            <strong>No pending relationships.</strong>
            <span>Create a relationship above to begin.</span>
          </div>

        ) : (

          <div className="relationship-list">

            {pendingRelationships.map((relationship) => {

              const isReviewing =
                reviewingId === relationship.id;

              return (
                <article
                  className="relationship-card"
                  key={relationship.id}
                >

                  <div className="relationship-card-label">
                    <span>{relationship.relation_type.replaceAll("_", " ")}</span>
                    <small>Relationship #{relationship.id}</small>
                  </div>

                  <div className="relationship-pair">
                    <strong>{relationship.source_item_title}</strong>
                    <GitBranch size={17} />
                    <strong>{relationship.target_item_title}</strong>
                  </div>

                  <div className="relationship-card-evidence">
                    <p>{relationship.evidence_excerpt}</p>

                    <span>
                      {relationship.original_filename}
                      {" · "}
                      {relationship.evidence_locator}
                    </span>
                  </div>

                  <div className="relationship-card-actions">

                    <button
                      type="button"
                      className="relationship-approve"
                      disabled={isReviewing || !reviewerId}
                      onClick={() =>
                        void reviewRelationship(
                          relationship,
                          "approved"
                        )
                      }
                    >
                      <CheckCircle2 size={15} />
                      Approve
                    </button>

                    <button
                      type="button"
                      className="relationship-reject"
                      disabled={isReviewing || !reviewerId}
                      onClick={() =>
                        void reviewRelationship(
                          relationship,
                          "rejected"
                        )
                      }
                    >
                      <XCircle size={15} />
                      Reject
                    </button>

                    {isReviewing && (
                      <span>Saving...</span>
                    )}

                  </div>

                </article>
              );
            })}

          </div>

        )}

      </div>

      {/* APPROVED CONNECTIONS */}

      <div className="relationship-list-section">

        <div className="relationship-section-title">
          <CheckCircle2 size={19} />

          <div>
            <h4>Approved Connections</h4>
            <p>Verified relationships currently included in the graph.</p>
          </div>
        </div>

        {approvedRelationships.length === 0 ? (

          <div className="relationship-empty">
            No approved connections yet.
          </div>

        ) : (

          <div className="relationship-list">

            {approvedRelationships.map((relationship) => (

              <div
                className="relationship-approved-card"
                key={relationship.id}
              >
                <CheckCircle2 size={16} />

                <div>
                  <strong>
                    {relationship.source_item_title}
                    {" → "}
                    {relationship.target_item_title}
                  </strong>

                  <span>
                    {relationship.relation_type.replaceAll("_", " ")}
                    {" · "}
                    {relationship.original_filename}
                    {" · "}
                    {relationship.evidence_locator}
                  </span>
                </div>

              </div>

            ))}

          </div>

        )}

      </div>

      <div className="relationship-note">
        <strong>Evidence-first rule:</strong> a connection only appears
        in the Knowledge Map after approval. Selecting a source passage
        does not prove the relationship by itself; a human must verify
        that the passage supports the connection.
      </div>

    </section>
  );
}

export default RelationshipManager;