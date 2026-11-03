
import { useEffect, useState, type FormEvent } from "react";
import {
  api,
  getApiError
} from "../services/api";
import "./WorkspaceManager.css";

interface Workspace {
  id: number;
  name: string;
  description: string | null;
  created_by: number;
  created_at: string;
  updated_at: string;
}

interface Invitation {
  id: number;
  invited_email: string;
  role: string;
  status: string;
  created_at: string;
  expires_at: string;
}

interface CreatedInvitation extends Invitation {
  invite_url: string;
}

interface IncomingInvitation {
  id: number;
  workspace_id: number;
  workspace_name: string;
  invited_email: string;
  role: string;
  status: string;
  created_at: string;
  expires_at: string;
}

interface InvitationAcceptance {
  message: string;
  workspace_id: number;
  workspace_name: string;
  role: string;
}

export default function WorkspaceManager() {
  const [open, setOpen] = useState(false);

  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [selectedWorkspaceId, setSelectedWorkspaceId] = useState<number | null>(null);

  const [invitations, setInvitations] = useState<Invitation[]>([]);
  const [latestInviteUrl, setLatestInviteUrl] = useState("");

  const [loading, setLoading] = useState(false);
  const [creating, setCreating] = useState(false);
  const [inviting, setInviting] = useState(false);

  const [name, setName] = useState("");
  const [description, setDescription] = useState("");

  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState("member");

  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  const [incomingInvitations, setIncomingInvitations] = useState<IncomingInvitation[]>([]);

  async function loadWorkspaces() {
    setLoading(true);
    setError("");

    try {
      const response = await api.get<Workspace[]>("/api/workspaces");
      setWorkspaces(response.data);
    } catch (err) {
      setError(getApiError(err));
    } finally {
      setLoading(false);
    }
  }

  async function loadIncomingInvitations() {
  try {
    const response = await api.get<IncomingInvitation[]>(
      "/api/workspaces/invitations/mine"
    );

    setIncomingInvitations(response.data);
  } catch (err) {
    setError(getApiError(err));
  }
}

  async function loadInvitations(workspaceId: number) {
    setError("");

    try {
      const response = await api.get<Invitation[]>(
        `/api/workspaces/${workspaceId}/invitations`
      );

      setInvitations(response.data);
    } catch (err) {
      setInvitations([]);
      setError(getApiError(err));
    }
  }

  async function handleAcceptIncomingInvitation(invitationId: number) {
  setError("");
  setSuccess("");

  try {
    const response = await api.post<InvitationAcceptance>(
      `/api/workspaces/invitations/${invitationId}/accept`
    );

    setSuccess(
      `Welcome! You joined ${response.data.workspace_name} as ${response.data.role}.`
    );

    setSelectedWorkspaceId(response.data.workspace_id);

    await Promise.all([
      loadWorkspaces(),
      loadIncomingInvitations()
    ]);

  } catch (err) {
    setError(getApiError(err));
  }
}

  useEffect(() => {
    void loadWorkspaces();
    void loadIncomingInvitations();
  }, []);

  function selectWorkspace(workspace: Workspace) {
    setSelectedWorkspaceId(workspace.id);
    setSuccess("");
    setLatestInviteUrl("");
    void loadInvitations(workspace.id);
  }

  async function handleCreateWorkspace(
    event: FormEvent<HTMLFormElement>
  ) {
    event.preventDefault();

    setError("");
    setSuccess("");
    setCreating(true);

    try {
      const response = await api.post<Workspace>("/api/workspaces", {
        name: name.trim(),
        description: description.trim() || null,
      });

      setWorkspaces((previous) => [
        response.data,
        ...previous,
      ]);

      setName("");
      setDescription("");
      setSuccess("Workspace created. You are its owner.");
      setSelectedWorkspaceId(response.data.id);
      setInvitations([]);
    } catch (err) {
      setError(getApiError(err));
    } finally {
      setCreating(false);
    }
  }

  async function handleCreateInvitation(
    event: FormEvent<HTMLFormElement>
  ) {
    event.preventDefault();

    if (selectedWorkspaceId === null) {
      setError("Please select a workspace first.");
      return;
    }

    setError("");
    setSuccess("");
    setLatestInviteUrl("");
    setInviting(true);

    try {
      const response = await api.post<CreatedInvitation>(
        `/api/workspaces/${selectedWorkspaceId}/invitations`,
        {
          invited_email: inviteEmail.trim(),
          role: inviteRole,
        }
      );

      setLatestInviteUrl(response.data.invite_url);
      setInviteEmail("");
      setInviteRole("member");

      setSuccess("Invitation created successfully.");

      await loadInvitations(selectedWorkspaceId);
    } catch (err) {
      setError(getApiError(err));
    } finally {
      setInviting(false);
    }
  }

  async function copyInvitationLink() {
    if (!latestInviteUrl) return;

    try {
      await navigator.clipboard.writeText(latestInviteUrl);
      setSuccess("Invitation link copied to clipboard.");
    } catch {
      setError(
        "Clipboard access failed. Select and copy the invitation link manually."
      );
    }
  }

  async function handleRevokeInvitation(invitationId: number) {
    if (selectedWorkspaceId === null) return;

    setError("");
    setSuccess("");

    try {
      await api.delete(
        `/api/workspaces/${selectedWorkspaceId}/invitations/${invitationId}`
      );

      setSuccess("Invitation revoked.");

      await loadInvitations(selectedWorkspaceId);
    } catch (err) {
      setError(getApiError(err));
    }
  }

  return (
    <>
      <button
        type="button"
        className="workspace-manager-trigger"
        onClick={() => {
          setOpen(true);
          setSuccess("");
          setError("");
          void loadWorkspaces();
            void loadIncomingInvitations();
        }}
      >
        <span className="workspace-manager-trigger-icon">▦</span>
        My Workspaces
        <span className="workspace-manager-count">
          {workspaces.length}
        </span>
        {incomingInvitations.length > 0 && (
  <span className="workspace-invitation-badge">
    {incomingInvitations.length} new
  </span>
)}
      </button>

      {open && (
        <div
          className="workspace-manager-overlay"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) {
              setOpen(false);
            }
          }}
        >
          <section
            className="workspace-manager-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="workspace-manager-title"
          >
            <header className="workspace-manager-header">
              <div>
                <span className="workspace-manager-eyebrow">
                  RELAYMAP WORKSPACE CENTER
                </span>

                <h2 id="workspace-manager-title">
                  Your Workspaces
                </h2>

                <p>
                  Organise projects and collaborate with your team.
                </p>
              </div>

              <button
                type="button"
                className="workspace-manager-close"
                onClick={() => setOpen(false)}
                aria-label="Close workspace manager"
              >
                ×
              </button>
            </header>

            {error && (
              <div className="workspace-manager-alert error">
                {error}
              </div>
            )}

            {success && (
              <div className="workspace-manager-alert success">
                {success}
              </div>
            )}

            {incomingInvitations.length > 0 && (
  <section className="workspace-inbox">
    <div className="workspace-inbox-heading">
      <div>
        <span className="workspace-manager-eyebrow">
          TEAM INVITATIONS
        </span>
        <h3>Invitations for you</h3>
        <p>
          You've been invited to collaborate in these workspaces.
        </p>
      </div>

      <span className="workspace-inbox-count">
        {incomingInvitations.length} pending
      </span>
    </div>

    <div className="workspace-inbox-list">
      {incomingInvitations.map((invitation) => (
        <article
          className="workspace-inbox-card"
          key={invitation.id}
        >
          <div className="workspace-inbox-icon">
            {invitation.workspace_name.charAt(0).toUpperCase()}
          </div>

          <div className="workspace-inbox-info">
            <strong>{invitation.workspace_name}</strong>
            <span>
              Invited as {invitation.role}
            </span>
            <small>
              Expires:{" "}
              {new Date(invitation.expires_at).toLocaleDateString()}
            </small>
          </div>

          <button
            type="button"
            className="workspace-inbox-accept"
            onClick={() =>
              void handleAcceptIncomingInvitation(invitation.id)
            }
          >
            Accept invitation
          </button>
        </article>
      ))}
    </div>
  </section>
)}

            <div className="workspace-manager-content">
              <div className="workspace-list-section">
                <div className="workspace-manager-section-heading">
                  <h3>Available workspaces</h3>

                  <button
                    type="button"
                    onClick={() => void loadWorkspaces()}
                    disabled={loading}
                  >
                    {loading ? "Refreshing..." : "Refresh"}
                  </button>
                </div>

                {loading ? (
                  <p className="workspace-manager-muted">
                    Loading workspaces...
                  </p>
                ) : workspaces.length === 0 ? (
                  <div className="workspace-manager-empty">
                    <span>▦</span>
                    <strong>No workspaces yet</strong>
                    <p>Create your first workspace to get started.</p>
                  </div>
                ) : (
                  <div className="workspace-manager-list">
                    {workspaces.map((workspace) => (
                      <button
                        type="button"
                        className={`workspace-manager-card workspace-select-card ${
                          selectedWorkspaceId === workspace.id
                            ? "selected"
                            : ""
                        }`}
                        key={workspace.id}
                        onClick={() => selectWorkspace(workspace)}
                      >
                        <div className="workspace-manager-card-icon">
                          {workspace.name.charAt(0).toUpperCase()}
                        </div>

                        <div className="workspace-manager-card-info">
                          <strong>{workspace.name}</strong>

                          <span>
                            {workspace.description ||
                              "No description provided"}
                          </span>

                          <small>
                            Workspace #{workspace.id}
                          </small>
                        </div>

                        <span className="workspace-manager-role">
                          {selectedWorkspaceId === workspace.id
                            ? "Selected"
                            : "Open"}
                        </span>
                      </button>
                    ))}
                  </div>
                )}

                <p className="workspace-manager-note">
                  Select a workspace to manage its invitations.
                </p>
              </div>

              <div className="workspace-manager-right">
                <form
                  className="workspace-create-form"
                  onSubmit={handleCreateWorkspace}
                >
                  <h3>Create a workspace</h3>

                  <p>
                    Start a new team space. You'll automatically become
                    its owner.
                  </p>

                  <label htmlFor="workspace-name">
                    Workspace name
                  </label>

                  <input
                    id="workspace-name"
                    value={name}
                    onChange={(event) => setName(event.target.value)}
                    placeholder="e.g. ABC Technologies"
                    minLength={2}
                    maxLength={150}
                    required
                  />

                  <label htmlFor="workspace-description">
                    Description
                  </label>

                  <textarea
                    id="workspace-description"
                    value={description}
                    onChange={(event) => setDescription(event.target.value)}
                    placeholder="What is this workspace for?"
                    rows={2}
                  />

                  <button
                    type="submit"
                    className="workspace-create-button"
                    disabled={creating}
                  >
                    {creating ? "Creating..." : "+ Create Workspace"}
                  </button>
                </form>

                <section className="workspace-invite-section">
                  <h3>Invite teammates</h3>

                  <p>
                    Invite someone to collaborate in the selected
                    workspace.
                  </p>

                  {selectedWorkspaceId === null ? (
                    <p className="workspace-manager-muted">
                      Select a workspace first.
                    </p>
                  ) : (
                    <>
                      <form
                        className="workspace-invite-form"
                        onSubmit={handleCreateInvitation}
                      >
                        <label htmlFor="invite-email">
                          Employee email
                        </label>

                        <input
                          id="invite-email"
                          type="email"
                          value={inviteEmail}
                          onChange={(event) =>
                            setInviteEmail(event.target.value)
                          }
                          placeholder="employee@company.com"
                          required
                        />

                        <label htmlFor="invite-role">
                          Workspace role
                        </label>

                        <select
                          id="invite-role"
                          value={inviteRole}
                          onChange={(event) =>
                            setInviteRole(event.target.value)
                          }
                        >
                          <option value="member">Member</option>
                          <option value="admin">Admin</option>
                          <option value="viewer">Viewer</option>
                        </select>

                        <button
                          type="submit"
                          className="workspace-create-button"
                          disabled={inviting}
                        >
                          {inviting ? "Creating invite..." : "Create invitation link"}
                        </button>
                      </form>

                      {latestInviteUrl && (
                        <div className="workspace-invite-created">
                          <strong>Invitation link created</strong>

                          <input
                            readOnly
                            value={latestInviteUrl}
                            onFocus={(event) => event.target.select()}
                          />

                          <button
                            type="button"
                            onClick={() => void copyInvitationLink()}
                          >
                            Copy invitation link
                          </button>

                          <small>
                            Share this link only with the invited email
                            address. It expires after seven days.
                          </small>
                        </div>
                      )}

                      <div className="workspace-manager-section-heading invitation-heading">
                        <h3>Invitations</h3>

                        <button
                          type="button"
                          onClick={() =>
                            void loadInvitations(selectedWorkspaceId)
                          }
                        >
                          Refresh
                        </button>
                      </div>

                      {invitations.length === 0 ? (
                        <p className="workspace-manager-muted">
                          No invitations available, or you do not have
                          permission to manage them.
                        </p>
                      ) : (
                        <div className="workspace-invitation-list">
                          {invitations.map((invitation) => (
                            <div
                              className="workspace-invitation-row"
                              key={invitation.id}
                            >
                              <div>
                                <strong>{invitation.invited_email}</strong>
                                <span>
                                  {invitation.role} · {invitation.status}
                                </span>
                              </div>

                              {invitation.status === "pending" && (
                                <button
                                  type="button"
                                  onClick={() =>
                                    void handleRevokeInvitation(invitation.id)
                                  }
                                >
                                  Revoke
                                </button>
                              )}
                            </div>
                          ))}
                        </div>
                      )}
                    </>
                  )}
                </section>
              </div>
            </div>
          </section>
        </div>
      )}
    </>
  );
}