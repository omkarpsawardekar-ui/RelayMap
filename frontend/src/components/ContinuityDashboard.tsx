import { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  Clock,
  FileText,
  GitBranch,
  RefreshCw,
  RotateCcw,
  UserRound,
  UserRoundX,
} from "lucide-react";

import { api, getApiError } from "../services/api";
import "./ContinuityDashboard.css";

interface ContinuityMember {
  id: number;
  project_id: number;
  user_id: number;
  full_name: string;
  email?: string;
  role: string;
  responsibility?: string | null;
  membership_status?: "active" | "departing" | "departed";
}

interface ContinuityGap {
  knowledge_item_id: number;
  item_type: string;
  title: string;
  work_status: string;
  assigned_member_user_id: number;
  assigned_member_name: string;
  membership_status: "departing" | "departed";
  document_id: number;
  original_filename: string;
  source_locator: string;
  source_excerpt: string;
  reason: string;
}

interface ContinuityGapReport {
  project_id: number;
  departing_members_count: number;
  potential_gaps_count: number;
  gaps: ContinuityGap[];
}

interface ContinuityDashboardProps {
  projectId: number;
}

function statusLabel(status: string | undefined): string {
  if (!status) return "active";
  return status.replace("_", " ");
}

function ContinuityDashboard({ projectId }: ContinuityDashboardProps) {
  const [members, setMembers] = useState<ContinuityMember[]>([]);
  const [report, setReport] = useState<ContinuityGapReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [updatingUserId, setUpdatingUserId] = useState<number | null>(null);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  const activeCount = useMemo(
    () => members.filter((member) => (member.membership_status ?? "active") === "active").length,
    [members]
  );
  const departingCount = useMemo(
    () => members.filter((member) => member.membership_status === "departing").length,
    [members]
  );
  const departedCount = useMemo(
    () => members.filter((member) => member.membership_status === "departed").length,
    [members]
  );

  const loadDashboard = useCallback(async () => {
    setLoading(true);
    setError("");

    try {
      const [membersResponse, gapsResponse] = await Promise.all([
        api.get<ContinuityMember[]>(`/api/projects/${projectId}/members`),
        api.get<ContinuityGapReport>(`/api/projects/${projectId}/continuity/gaps`),
      ]);

      setMembers(membersResponse.data);
      setReport(gapsResponse.data);
    } catch (err) {
      setError(getApiError(err));
      setReport(null);
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    void loadDashboard();
  }, [loadDashboard]);

  async function updateMemberStatus(
    userId: number,
    membershipStatus: "active" | "departing" | "departed"
  ) {
    setUpdatingUserId(userId);
    setError("");
    setSuccess("");

    try {
      await api.patch(
        `/api/projects/${projectId}/continuity/members/${userId}/status`,
        { membership_status: membershipStatus }
      );

      setSuccess(`Member status updated to "${membershipStatus}".`);
      await loadDashboard();
    } catch (err) {
      setError(getApiError(err));
    } finally {
      setUpdatingUserId(null);
    }
  }

  return (
    <section className="continuity-page">
      <div className="continuity-intro">
        <div>
          <div className="continuity-eyebrow">
            <GitBranch size={15} />
            CONTINUITY INTELLIGENCE
          </div>
          <h2>Continuity Dashboard</h2>
          <p>
            Identify approved, unfinished work that may lose its owner when a
            project member leaves. RelayMap flags potential gaps; people decide
            how the work should be reassigned.
          </p>
        </div>

        <button
          type="button"
          className="continuity-refresh"
          onClick={() => void loadDashboard()}
          disabled={loading}
        >
          <RefreshCw size={16} className={loading ? "continuity-spinning" : ""} />
          Refresh
        </button>
      </div>

      {error && <div className="continuity-alert continuity-alert-error">{error}</div>}
      {success && <div className="continuity-alert continuity-alert-success">{success}</div>}

      <div className="continuity-stats">
        <div className="continuity-stat">
          <span>Active members</span>
          <strong>{activeCount}</strong>
          <small>Currently active in this project</small>
        </div>
        <div className="continuity-stat">
          <span>Departing</span>
          <strong>{departingCount}</strong>
          <small>Transition in progress</small>
        </div>
        <div className="continuity-stat">
          <span>Departed</span>
          <strong>{departedCount}</strong>
          <small>No longer active in the project</small>
        </div>
        <div className="continuity-stat continuity-stat-risk">
          <span>Potential ownership gaps</span>
          <strong>{report?.potential_gaps_count ?? 0}</strong>
          <small>Approved unfinished items flagged</small>
        </div>
      </div>

      <section className="continuity-panel">
        <div className="continuity-panel-heading">
          <div className="continuity-panel-icon"><UserRound size={19} /></div>
          <div>
            <h3>Project Members</h3>
            <p>Mark a member as departing to run a continuity check.</p>
          </div>
        </div>

        {loading ? (
          <div className="continuity-empty">Loading project members...</div>
        ) : members.length === 0 ? (
          <div className="continuity-empty">No project members were found.</div>
        ) : (
          <div className="continuity-member-list">
            {members.map((member) => {
              const memberStatus = member.membership_status ?? "active";
              const isUpdating = updatingUserId === member.user_id;

              return (
                <div className="continuity-member" key={member.user_id}>
                  <div className="continuity-avatar">
                    {member.full_name.charAt(0).toUpperCase()}
                  </div>

                  <div className="continuity-member-info">
                    <strong>{member.full_name}</strong>
                    <span>
                      {member.role}
                      {member.responsibility ? ` Â· ${member.responsibility}` : ""}
                    </span>
                  </div>

                  <span className={`continuity-status status-${memberStatus}`}>
                    {statusLabel(memberStatus)}
                  </span>

                  <div className="continuity-member-actions">
                    {memberStatus === "active" && (
                      <button
                        type="button"
                        className="continuity-action continuity-action-departing"
                        disabled={isUpdating}
                        onClick={() => void updateMemberStatus(member.user_id, "departing")}
                      >
                        <UserRoundX size={14} />
                        {isUpdating ? "Saving..." : "Mark departing"}
                      </button>
                    )}

                    {memberStatus === "departing" && (
                      <>
                        <button
                          type="button"
                          className="continuity-action continuity-action-departed"
                          disabled={isUpdating}
                          onClick={() => void updateMemberStatus(member.user_id, "departed")}
                        >
                          {isUpdating ? "Saving..." : "Mark departed"}
                        </button>
                        <button
                          type="button"
                          className="continuity-action continuity-action-restore"
                          disabled={isUpdating}
                          onClick={() => void updateMemberStatus(member.user_id, "active")}
                        >
                          <RotateCcw size={13} /> Restore
                        </button>
                      </>
                    )}

                    {memberStatus === "departed" && (
                      <button
                        type="button"
                        className="continuity-action continuity-action-restore"
                        disabled={isUpdating}
                        onClick={() => void updateMemberStatus(member.user_id, "active")}
                      >
                        <RotateCcw size={13} />
                        {isUpdating ? "Saving..." : "Restore active"}
                      </button>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </section>

      <section className="continuity-panel">
        <div className="continuity-panel-heading">
          <div className="continuity-panel-icon continuity-risk-icon">
            <AlertTriangle size={19} />
          </div>
          <div>
            <h3>Potential Ownership Gaps</h3>
            <p>
              Only approved knowledge items with open, in-progress or blocked
              status and an assigned departing member are included.
            </p>
          </div>
        </div>

        {loading ? (
          <div className="continuity-empty">Checking for potential gaps...</div>
        ) : !report || report.gaps.length === 0 ? (
          <div className="continuity-empty">
            <CheckCircle2 size={30} />
            <strong>No potential ownership gaps detected.</strong>
            <span>
              This means no matching approved unfinished items were found for
              departing or departed members. It does not prove that all project
              work is fully documented.
            </span>
          </div>
        ) : (
          <div className="continuity-gap-list">
            {report.gaps.map((gap) => (
              <article className="continuity-gap-card" key={gap.knowledge_item_id}>
                <div className="continuity-gap-topline">
                  <span className="continuity-gap-type">{gap.item_type}</span>
                  <span className={`continuity-status status-${gap.membership_status}`}>
                    Member {gap.membership_status}
                  </span>
                </div>

                <h4>{gap.title}</h4>

                <div className="continuity-gap-meta">
                  <span><UserRound size={14} /> {gap.assigned_member_name}</span>
                  <span><Clock size={14} /> {gap.work_status.replace("_", " ")}</span>
                </div>

                <div className="continuity-evidence">
                  <div className="continuity-evidence-heading">
                    <FileText size={14} /> Source evidence
                  </div>
                  <p>{gap.source_excerpt}</p>
                  <div className="continuity-source-location">
                    {gap.original_filename} Â· {gap.source_locator}
                  </div>
                </div>

                <div className="continuity-gap-reason">
                  <AlertTriangle size={14} />
                  <span>{gap.reason}</span>
                </div>

                <div className="continuity-gap-footer">
                  Knowledge record #{gap.knowledge_item_id} Â· No automatic reassignment
                </div>
              </article>
            ))}
          </div>
        )}
      </section>

      <div className="continuity-note">
        <strong>Human decision required.</strong> This report identifies
        potential ownership gaps from approved records only. It does not
        automatically reassign tasks or establish that undocumented work does
        not exist.
      </div>
    </section>
  );
}

export default ContinuityDashboard;