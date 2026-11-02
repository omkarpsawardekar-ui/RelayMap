import {
  useEffect,
  useState,
  type ChangeEvent,
  type FormEvent,
} from "react";

import {
  Activity,
  ArrowUpRight,
  CheckCircle2,
  ChevronRight,
  CircleAlert,
  Database,
  FileText,
  GitBranch,
  FolderKanban,
  Plus,
  RefreshCw,
  ShieldCheck,
  Upload,
  Users,
  UserPlus,
  X,
  Network,
  Sparkles,
} from "lucide-react";

import { api, getApiError } from "./services/api";

import KnowledgeReview from "./components/KnowledgeReview";
import ContinuityDashboard from "./components/ContinuityDashboard";
import KnowledgeMap from "./components/KnowledgeMap";
import HandoverDashboard from "./components/HandoverDashboard";

import type {
  User,
  Project,
  ProjectMember,
} from "./types";

import "./App.css";

type Page =
  | "overview"
  | "team"
  | "sources"
  | "knowledge"
  | "continuity"
  | "map"
  | "handover";

interface ProjectDocument {
  id: number;
  project_id: number;
  original_filename: string;
  file_type: string;
  mime_type: string | null;
  size_bytes: number;
  sha256: string;
  extraction_status: string;
  uploaded_at: string;
}

const MAX_FILE_SIZE = 20 * 1024 * 1024;

const ALLOWED_EXTENSIONS = [".pdf", ".docx", ".md", ".csv"];

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;

  if (bytes < 1024 * 1024) {
    return `${(bytes / 1024).toFixed(1)} KB`;
  }

  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

function App() {
  // =====================================================
  // APPLICATION STATE
  // =====================================================

  const [users, setUsers] = useState<User[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [members, setMembers] = useState<ProjectMember[]>([]);
  const [documents, setDocuments] = useState<ProjectDocument[]>([]);

  const [selectedProjectId, setSelectedProjectId] =
    useState<number | null>(null);

  const [activePage, setActivePage] = useState<Page>("overview");

  const [apiStatus, setApiStatus] = useState("Checking");
  const [dbStatus, setDbStatus] = useState("Checking");

  const [loading, setLoading] = useState(true);
  const [memberLoading, setMemberLoading] = useState(false);
  const [documentLoading, setDocumentLoading] = useState(false);

  const [submitting, setSubmitting] = useState(false);
  const [uploading, setUploading] = useState(false);

  // Extraction state
  const [extractingDocumentId, setExtractingDocumentId] =
    useState<number | null>(null);

  const [extractionMessages, setExtractionMessages] =
    useState<Record<number, string>>({});

  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  // =====================================================
  // FORM VISIBILITY
  // =====================================================

  const [showUserForm, setShowUserForm] = useState(false);
  const [showProjectForm, setShowProjectForm] = useState(false);
  const [showMemberForm, setShowMemberForm] = useState(false);

  // =====================================================
  // USER FORM
  // =====================================================

  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");

  // =====================================================
  // PROJECT FORM
  // =====================================================

  const [projectName, setProjectName] = useState("");
  const [projectDescription, setProjectDescription] = useState("");
  const [projectOwner, setProjectOwner] = useState("");

  // =====================================================
  // MEMBER FORM
  // =====================================================

  const [memberUserId, setMemberUserId] = useState("");
  const [memberRole, setMemberRole] = useState("member");
  const [responsibility, setResponsibility] = useState("");

  // =====================================================
  // DOCUMENT UPLOAD
  // =====================================================

  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);

  // =====================================================
  // SELECTED PROJECT
  // =====================================================

  const selectedProject = projects.find(
    (project) => project.id === selectedProjectId
  );

  const availableUsers = users.filter(
    (user) =>
      user.is_active &&
      !members.some((member) => member.user_id === user.id)
  );

  // =====================================================
  // INITIAL DATA LOADING
  // =====================================================

  useEffect(() => {
    let active = true;

    async function initialize() {
      try {
        const results = await Promise.allSettled([
          api.get("/api/health"),
          api.get("/api/health/db"),
          api.get<User[]>("/api/users"),
          api.get<Project[]>("/api/projects"),
        ]);

        if (!active) return;

        const [apiResult, dbResult, usersResult, projectsResult] =
          results;

        setApiStatus(
          apiResult.status === "fulfilled"
            ? "Connected"
            : "Disconnected"
        );

        setDbStatus(
          dbResult.status === "fulfilled"
            ? "Connected"
            : "Disconnected"
        );

        if (usersResult.status === "fulfilled") {
          setUsers(usersResult.value.data);
        }

        if (projectsResult.status === "fulfilled") {
          setProjects(projectsResult.value.data);

          if (projectsResult.value.data.length > 0) {
            setSelectedProjectId(projectsResult.value.data[0].id);
          }
        }

        if (
          usersResult.status === "rejected" ||
          projectsResult.status === "rejected"
        ) {
          setError("Could not load project information.");
        }
      } catch (err) {
        if (active) setError(getApiError(err));
      } finally {
        if (active) setLoading(false);
      }
    }

    void initialize();

    return () => {
      active = false;
    };
  }, []);

  // =====================================================
  // LOAD MEMBERS WHEN PROJECT CHANGES
  // =====================================================

  useEffect(() => {
    let active = true;

    async function loadMembers() {
      if (selectedProjectId === null) {
        setMembers([]);
        return;
      }

      setMemberLoading(true);

      try {
        const response = await api.get<ProjectMember[]>(
          `/api/projects/${selectedProjectId}/members`
        );

        if (active) {
          setMembers(response.data);
        }
      } catch (err) {
        if (active) setError(getApiError(err));
      } finally {
        if (active) setMemberLoading(false);
      }
    }

    void loadMembers();

    return () => {
      active = false;
    };
  }, [selectedProjectId]);

  // =====================================================
  // LOAD DOCUMENTS WHEN PROJECT CHANGES
  // =====================================================

  useEffect(() => {
    let active = true;

    async function loadDocuments() {
      if (selectedProjectId === null) {
        setDocuments([]);
        return;
      }

      setDocumentLoading(true);

      try {
        const response = await api.get<ProjectDocument[]>(
          `/api/projects/${selectedProjectId}/documents`
        );

        if (active) {
          setDocuments(response.data);
          setExtractionMessages({});
        }
      } catch (err) {
        if (active) {
          setError(`Could not load documents: ${getApiError(err)}`);
        }
      } finally {
        if (active) setDocumentLoading(false);
      }
    }

    void loadDocuments();

    return () => {
      active = false;
    };
  }, [selectedProjectId]);

  // =====================================================
  // NAVIGATION
  // =====================================================

  function navigateTo(page: Page) {
    setActivePage(page);

    setError("");
    setSuccess("");

    setShowUserForm(false);
    setShowProjectForm(false);
    setShowMemberForm(false);
  }

  // =====================================================
  // REGISTER USER
  // =====================================================

  async function handleCreateUser(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    setError("");
    setSuccess("");
    setSubmitting(true);

    try {
      const response = await api.post<User>("/api/users", {
        full_name: fullName.trim(),
        email: email.trim(),
      });

      setUsers((previous) => [...previous, response.data]);

      setFullName("");
      setEmail("");
      setShowUserForm(false);

      setSuccess(`${response.data.full_name} was registered successfully.`);
    } catch (err) {
      setError(getApiError(err));
    } finally {
      setSubmitting(false);
    }
  }

  // =====================================================
  // CREATE PROJECT
  // =====================================================

  async function handleCreateProject(
    event: FormEvent<HTMLFormElement>
  ) {
    event.preventDefault();

    if (!projectOwner) {
      setError("Please select a project owner.");
      return;
    }

    setError("");
    setSuccess("");
    setSubmitting(true);

    try {
      const response = await api.post<Project>("/api/projects", {
        name: projectName.trim(),
        description: projectDescription.trim() || null,
        created_by: Number(projectOwner),
      });

      setProjects((previous) => [response.data, ...previous]);
      setSelectedProjectId(response.data.id);

      setProjectName("");
      setProjectDescription("");
      setProjectOwner("");

      setShowProjectForm(false);
      setSuccess("Project created successfully.");
    } catch (err) {
      setError(getApiError(err));
    } finally {
      setSubmitting(false);
    }
  }

  // =====================================================
  // ADD PROJECT MEMBER
  // =====================================================

  async function handleAddMember(
    event: FormEvent<HTMLFormElement>
  ) {
    event.preventDefault();

    if (selectedProjectId === null) return;

    setError("");
    setSuccess("");
    setSubmitting(true);

    try {
      await api.post(
        `/api/projects/${selectedProjectId}/members`,
        {
          user_id: Number(memberUserId),
          role: memberRole,
          responsibility: responsibility.trim() || null,
        }
      );

      const response = await api.get<ProjectMember[]>(
        `/api/projects/${selectedProjectId}/members`
      );

      setMembers(response.data);

      const addedUser = users.find(
        (user) => user.id === Number(memberUserId)
      );

      setMemberUserId("");
      setMemberRole("member");
      setResponsibility("");
      setShowMemberForm(false);

      setSuccess(
        `${addedUser?.full_name ?? "Member"} added successfully.`
      );
    } catch (err) {
      setError(getApiError(err));
    } finally {
      setSubmitting(false);
    }
  }

  // =====================================================
  // VALIDATE SELECTED FILES
  // =====================================================

  function handleFileSelection(
    event: ChangeEvent<HTMLInputElement>
  ) {
    const files = Array.from(event.target.files ?? []);

    const validFiles: File[] = [];
    const rejectedFiles: string[] = [];

    for (const file of files) {
      const extension = file.name
        .slice(file.name.lastIndexOf("."))
        .toLowerCase();

      if (!ALLOWED_EXTENSIONS.includes(extension)) {
        rejectedFiles.push(`${file.name}: unsupported format`);
        continue;
      }

      if (file.size === 0) {
        rejectedFiles.push(`${file.name}: empty file`);
        continue;
      }

      if (file.size > MAX_FILE_SIZE) {
        rejectedFiles.push(`${file.name}: exceeds 20 MB`);
        continue;
      }

      validFiles.push(file);
    }

    setSelectedFiles(validFiles);

    setError(
      rejectedFiles.length > 0
        ? rejectedFiles.join("; ")
        : ""
    );
  }

  // =====================================================
  // UPLOAD FILES TO FASTAPI
  // =====================================================

  async function handleUploadDocuments() {
    if (selectedProjectId === null) {
      setError("Please select a project first.");
      return;
    }

    if (selectedFiles.length === 0) {
      setError("Please select at least one document.");
      return;
    }

    setError("");
    setSuccess("");
    setUploading(true);

    const filesToUpload = [...selectedFiles];
    const failedFiles: File[] = [];
    const failureMessages: string[] = [];

    let uploadedCount = 0;

    try {
      // Upload sequentially because the backend accepts one file per request.
      for (const file of filesToUpload) {
        const formData = new FormData();
        formData.append("file", file);

        try {
          await api.post<ProjectDocument>(
            `/api/projects/${selectedProjectId}/documents`,
            formData
          );

          uploadedCount++;
        } catch (err) {
          failedFiles.push(file);

          failureMessages.push(
            `${file.name}: ${getApiError(err)}`
          );
        }
      }

      // Fetch the authoritative document list from the backend.
      try {
        const response = await api.get<ProjectDocument[]>(
          `/api/projects/${selectedProjectId}/documents`
        );

        setDocuments(response.data);
        setExtractionMessages({});
      } catch (err) {
        setError(
          `Upload finished, but the document list could not be refreshed: ${getApiError(err)}`
        );
      }

      // Keep files that failed so the user can retry them.
      setSelectedFiles(failedFiles);

      const fileInput = document.getElementById(
        "project-files"
      ) as HTMLInputElement | null;

      if (fileInput) fileInput.value = "";

      if (failureMessages.length > 0) {
        setError(
          `Uploaded ${uploadedCount} of ${filesToUpload.length} files. ` +
          failureMessages.join(" | ")
        );
      } else if (uploadedCount > 0) {
        setSuccess(
          `Successfully uploaded ${uploadedCount} document(s). You can now click Extract Knowledge on each document.`
        );
      }
    } finally {
      setUploading(false);
    }
  }

  // =====================================================
  // EXTRACT KNOWLEDGE FROM A DOCUMENT
  // =====================================================

  async function handleExtractKnowledge(document: ProjectDocument) {
    if (selectedProjectId === null) {
      setError("Please select a project first.");
      return;
    }

    setError("");
    setSuccess("");

    setExtractionMessages((previous) => ({
      ...previous,
      [document.id]: "",
    }));

    setExtractingDocumentId(document.id);

    try {
      const response = await api.post(
        `/api/projects/${selectedProjectId}/documents/${document.id}/extract`
      );

      const result = response.data;

      let extractionMessage =
        "Knowledge extraction completed successfully. Review the generated candidates in Knowledge Review.";

      if (typeof result?.candidates_created === "number") {
        extractionMessage =
          `${result.candidates_created} knowledge candidate(s) created. Open Knowledge Review to inspect them.`;
      } else if (typeof result?.created_items === "number") {
        extractionMessage =
          `${result.created_items} knowledge candidate(s) created. Open Knowledge Review to inspect them.`;
      } else if (typeof result?.created_count === "number") {
        extractionMessage =
          `${result.created_count} knowledge candidate(s) created. Open Knowledge Review to inspect them.`;
      }

      setExtractionMessages((previous) => ({
        ...previous,
        [document.id]: extractionMessage,
      }));

      setSuccess(
        `Knowledge extraction completed for ${document.original_filename}.`
      );
    } catch (err) {
      const errorMessage = getApiError(err);

      setExtractionMessages((previous) => ({
        ...previous,
        [document.id]: `Extraction failed: ${errorMessage}`,
      }));

      setError(
        `Could not extract knowledge from ${document.original_filename}: ${errorMessage}`
      );
    } finally {
      setExtractingDocumentId(null);
    }
  }

  // =====================================================
  // CLEAR SELECTED FILES
  // =====================================================

  function clearSelectedFiles() {
    setSelectedFiles([]);

    const fileInput = document.getElementById(
      "project-files"
    ) as HTMLInputElement | null;

    if (fileInput) fileInput.value = "";
  }

  // =====================================================
  // REFRESH WORKSPACE
  // =====================================================

  async function refreshWorkspace() {
    setError("");
    setSuccess("");

    try {
      const [usersResponse, projectsResponse] = await Promise.all([
        api.get<User[]>("/api/users"),
        api.get<Project[]>("/api/projects"),
      ]);

      setUsers(usersResponse.data);
      setProjects(projectsResponse.data);

      const [healthResult, dbResult] = await Promise.allSettled([
        api.get("/api/health"),
        api.get("/api/health/db"),
      ]);

      setApiStatus(
        healthResult.status === "fulfilled"
          ? "Connected"
          : "Disconnected"
      );

      setDbStatus(
        dbResult.status === "fulfilled"
          ? "Connected"
          : "Disconnected"
      );

      setSuccess("Workspace information refreshed.");
    } catch (err) {
      setError(getApiError(err));
    }
  }

  // =====================================================
  // REUSABLE MEMBER FORM
  // =====================================================

  function renderAddMemberForm() {
    return (
      <form className="member-form" onSubmit={handleAddMember}>
        <label>Select User</label>

        <select
          value={memberUserId}
          onChange={(e) => setMemberUserId(e.target.value)}
          required
        >
          <option value="">Choose a user</option>

          {availableUsers.map((user) => (
            <option key={user.id} value={user.id}>
              {user.full_name}
            </option>
          ))}
        </select>

        <label>Project Role</label>

        <select
          value={memberRole}
          onChange={(e) => setMemberRole(e.target.value)}
        >
          <option value="member">Member</option>
          <option value="admin">Admin</option>
          <option value="viewer">Viewer</option>
        </select>

        <label>Responsibility</label>

        <input
          value={responsibility}
          onChange={(e) => setResponsibility(e.target.value)}
          placeholder="e.g. Backend Development"
          maxLength={160}
        />

        <button
          className="primary-button"
          disabled={submitting || availableUsers.length === 0}
        >
          {submitting ? "Adding..." : "Add Member"}
        </button>

        {availableUsers.length === 0 && (
          <p className="form-hint">
            All registered users are already members.
          </p>
        )}
      </form>
    );
  }

  // =====================================================
  // REUSABLE MEMBER LIST
  // =====================================================

  function renderMemberList() {
    if (memberLoading) {
      return <p className="muted-text">Loading members...</p>;
    }

    if (members.length === 0) {
      return <p className="muted-text">No members found.</p>;
    }

    return members.map((member) => (
      <div className="member-item" key={member.id}>
        <div className="member-avatar">
          {member.full_name.charAt(0).toUpperCase()}
        </div>

        <div className="member-info">
          <strong>{member.full_name}</strong>
          <span>
            {member.responsibility || "No responsibility assigned"}
          </span>
        </div>

        <span className="member-role">{member.role}</span>
      </div>
    ));
  }

  // =====================================================
  // MAIN APPLICATION
  // =====================================================

  return (
    <div className="app-shell">

      {/* SIDEBAR */}

      <aside className="sidebar">

        <div className="brand">
          <div className="brand-icon">
            <Activity size={24} />
          </div>

          <div>
            <h2>RelayMap</h2>
            <span>PROJECT CONTINUITY</span>
          </div>
        </div>

        <div className="sidebar-label">WORKSPACE</div>

        <nav className="sidebar-nav">

          <button
            type="button"
            className={`nav-item ${activePage === "overview" ? "active" : ""}`}
            onClick={() => navigateTo("overview")}
          >
            <FolderKanban size={19} />
            Overview
          </button>

          <button
            type="button"
            className={`nav-item ${activePage === "team" ? "active" : ""}`}
            onClick={() => navigateTo("team")}
          >
            <Users size={19} />
            Team Members
          </button>

          <button
            type="button"
            className={`nav-item ${activePage === "sources" ? "active" : ""}`}
            onClick={() => navigateTo("sources")}
          >
            <Database size={19} />
            Data Sources
          </button>

          <button
            type="button"
            className={`nav-item ${activePage === "knowledge" ? "active" : ""}`}
            onClick={() => navigateTo("knowledge")}
          >
            <ShieldCheck size={19} />
            Knowledge Review
          </button>

          <button
            type="button"
            className={`nav-item ${activePage === "continuity" ? "active" : ""}`}
            onClick={() => navigateTo("continuity")}
          >
            <GitBranch size={19} />
            Continuity Dashboard
          </button>

          <button
            type="button"
            className={`nav-item ${activePage === "map" ? "active" : ""}`}
            onClick={() => navigateTo("map")}
          >
            <Network size={19} />
            Knowledge Map
          </button>

          <button
            type="button"
            className={`nav-item ${activePage === "handover" ? "active" : ""}`}
            onClick={() => navigateTo("handover")}
          >
            <FileText size={19} />
            Handover Center
          </button>

        </nav>

        <div className="sidebar-bottom">
          <div className="sidebar-status">
            <span className="status-dot" />
            Development Environment
          </div>

          <span className="sidebar-version">RelayMap v0.1.0</span>
        </div>

      </aside>

      {/* MAIN CONTENT */}

      <main className="main-content">

        {/* HEADER */}

        <header className="topbar">
          <div>
            <span className="breadcrumb">
              Workspace /{" "}
              {activePage === "overview"
                ? "Overview"
                : activePage === "team"
                ? "Team Members"
                : activePage === "sources"
                ? "Data Sources"
                : activePage === "knowledge"
                ? "Knowledge Review"
                : activePage === "continuity"
                ? "Continuity Dashboard"
                : activePage === "map"
                ? "Knowledge Map"
                : "Handover Center"}
            </span>

            <h1>
              {activePage === "overview"
                ? "Project Overview"
                : activePage === "team"
                ? "Team Members"
                : activePage === "sources"
                ? "Data Sources"
                : activePage === "knowledge"
                ? "Knowledge Review"
                : activePage === "continuity"
                ? "Continuity Dashboard"
                : activePage === "map"
                ? "Knowledge Map"
                : "Handover Center"}
            </h1>

            <p>
              {activePage === "overview"
                ? "Manage your projects and preserve team knowledge."
                : activePage === "team"
                ? "Manage project members and their responsibilities."
                : activePage === "sources"
                ? "Upload documents and reconstruct project knowledge."
                : activePage === "knowledge"
                ? "Verify extracted information against original evidence."
                : activePage === "continuity"
                ? "Identify potential ownership gaps before a team member leaves."
                : activePage === "map"
                ? "Explore connections across your project knowledge."
                : "Generate, review and approve evidence-backed handovers."}
            </p>
          </div>

          <button
            type="button"
            className="refresh-button"
            onClick={refreshWorkspace}
            title="Refresh workspace"
          >
            <RefreshCw size={17} />
          </button>
        </header>

        {/* CONNECTION STATUS */}

        <section className="connection-status">

          <div className="connection-item">
            <CheckCircle2 size={17} />
            <span>Backend API</span>

            <strong className={apiStatus === "Connected" ? "connected" : "disconnected"}>
              {apiStatus}
            </strong>
          </div>

          <div className="connection-divider" />

          <div className="connection-item">
            <Database size={17} />
            <span>PostgreSQL</span>

            <strong className={dbStatus === "Connected" ? "connected" : "disconnected"}>
              {dbStatus}
            </strong>
          </div>

        </section>

        {/* ALERTS */}

        {error && (
          <div className="alert error-alert">
            <CircleAlert size={18} />
            <span>{error}</span>

            <button
              type="button"
              onClick={() => setError("")}
              aria-label="Dismiss error"
            >
              <X size={17} />
            </button>
          </div>
        )}

        {success && (
          <div className="alert success-alert">
            <CheckCircle2 size={18} />
            <span>{success}</span>

            <button
              type="button"
              onClick={() => setSuccess("")}
              aria-label="Dismiss success"
            >
              <X size={17} />
            </button>
          </div>
        )}

        {/* ======================================
            OVERVIEW PAGE
        ====================================== */}

        {activePage === "overview" && (
          <>

            <section className="stats-grid">

              <div className="stat-card">
                <div className="stat-icon purple">
                  <FolderKanban size={21} />
                </div>

                <span>Total Projects</span>
                <h2>{projects.length}</h2>
                <small>Registered workspaces</small>
              </div>

              <div className="stat-card">
                <div className="stat-icon teal">
                  <Users size={21} />
                </div>

                <span>Team Members</span>
                <h2>{users.length}</h2>
                <small>Registered users</small>
              </div>

              <div className="stat-card">
                <div className="stat-icon blue">
                  <Activity size={21} />
                </div>

                <span>Active Projects</span>

                <h2>
                  {projects.filter((p) => p.status === "active").length}
                </h2>

                <small>Currently active workspaces</small>
              </div>

            </section>

            <section className="section-heading">

              <div>
                <h2>Your Projects</h2>
                <p>Create and manage your project workspaces.</p>
              </div>

              <div className="action-buttons">

                <button
                  type="button"
                  className="secondary-button"
                  onClick={() => {
                    setShowUserForm(!showUserForm);
                    setShowProjectForm(false);
                    setShowMemberForm(false);
                  }}
                >
                  <UserPlus size={17} />
                  Add User
                </button>

                <button
                  type="button"
                  className="primary-button"
                  onClick={() => {
                    setShowProjectForm(!showProjectForm);
                    setShowUserForm(false);
                    setShowMemberForm(false);
                  }}
                >
                  <Plus size={18} />
                  New Project
                </button>

              </div>

            </section>

            {/* REGISTER USER */}

            {showUserForm && (
              <form className="form-card" onSubmit={handleCreateUser}>

                <div className="form-title">
                  <h3>Register Team Member</h3>

                  <button
                    type="button"
                    onClick={() => setShowUserForm(false)}
                    aria-label="Close form"
                  >
                    <X size={19} />
                  </button>
                </div>

                <label>Full Name</label>

                <input
                  value={fullName}
                  onChange={(e) => setFullName(e.target.value)}
                  placeholder="Enter full name"
                  minLength={2}
                  maxLength={120}
                  required
                />

                <label>Email Address</label>

                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="name@example.com"
                  required
                />

                <button className="primary-button" disabled={submitting}>
                  {submitting ? "Adding..." : "Register User"}
                </button>

              </form>
            )}

            {/* CREATE PROJECT */}

            {showProjectForm && (
              <form className="form-card" onSubmit={handleCreateProject}>

                <div className="form-title">
                  <h3>Create New Project</h3>

                  <button
                    type="button"
                    onClick={() => setShowProjectForm(false)}
                    aria-label="Close form"
                  >
                    <X size={19} />
                  </button>
                </div>

                <label>Project Name</label>

                <input
                  value={projectName}
                  onChange={(e) => setProjectName(e.target.value)}
                  placeholder="e.g. AI Detection System"
                  minLength={2}
                  maxLength={150}
                  required
                />

                <label>Description</label>

                <textarea
                  value={projectDescription}
                  onChange={(e) => setProjectDescription(e.target.value)}
                  placeholder="Describe your project..."
                  rows={3}
                />

                <label>Project Owner</label>

                <select
                  value={projectOwner}
                  onChange={(e) => setProjectOwner(e.target.value)}
                  required
                >
                  <option value="">Select project owner</option>

                  {users.filter((user) => user.is_active).map((user) => (
                    <option key={user.id} value={user.id}>
                      {user.full_name} — {user.email}
                    </option>
                  ))}
                </select>

                <button
                  className="primary-button"
                  disabled={submitting || users.length === 0}
                >
                  {submitting ? "Creating..." : "Create Project"}
                </button>

              </form>
            )}

            {/* PROJECT LIST AND DETAILS */}

            <section className="workspace-grid">

              <div className="projects-panel">

                {loading ? (
                  <div className="empty-state">Loading projects...</div>
                ) : projects.length === 0 ? (

                  <div className="empty-state">
                    <FolderKanban size={38} />
                    <h3>No projects yet</h3>
                    <p>Create your first project workspace.</p>

                    <button
                      type="button"
                      className="primary-button"
                      onClick={() => setShowProjectForm(true)}
                    >
                      <Plus size={17} />
                      Create First Project
                    </button>
                  </div>

                ) : (

                  <div className="project-list">

                    {projects.map((project) => (

                      <button
                        type="button"
                        key={project.id}
                        className={
                          selectedProjectId === project.id
                            ? "project-card selected"
                            : "project-card"
                        }
                        onClick={() => setSelectedProjectId(project.id)}
                      >

                        <div className="project-card-top">
                          <div className="project-icon">
                            <FolderKanban size={22} />
                          </div>

                          <span className="project-status">
                            <span className="status-dot" />
                            {project.status}
                          </span>
                        </div>

                        <h3>{project.name}</h3>

                        <p>
                          {project.description || "No description provided."}
                        </p>

                        <div className="project-card-footer">
                          <span>Project #{project.id}</span>
                          <ChevronRight size={18} />
                        </div>

                      </button>

                    ))}

                  </div>

                )}

              </div>

              <aside className="details-panel">

                {selectedProject ? (
                  <>

                    <div className="details-heading">
                      <div>
                        <span className="breadcrumb">SELECTED PROJECT</span>
                        <h2>{selectedProject.name}</h2>
                      </div>

                      <ArrowUpRight size={20} />
                    </div>

                    <p className="details-description">
                      {selectedProject.description ||
                        "No project description provided."}
                    </p>

                    <div className="details-divider" />

                    <div className="member-heading">
                      <div>
                        <h3>Project Members</h3>
                        <span>{members.length} registered members</span>
                      </div>

                      <button
                        type="button"
                        className="add-member-button"
                        onClick={() => setShowMemberForm(!showMemberForm)}
                        title="Add member"
                      >
                        <Plus size={18} />
                      </button>
                    </div>

                    {showMemberForm && renderAddMemberForm()}

                    <div className="member-list">
                      {renderMemberList()}
                    </div>

                    <div className="details-divider" />

                    <h3>Project Documents</h3>

                    <p className="muted-text">
                      {documents.length} documents uploaded
                    </p>

                    <button
                      type="button"
                      className="secondary-button"
                      onClick={() => navigateTo("sources")}
                    >
                      <Database size={17} />
                      Open Data Sources
                    </button>

                  </>
                ) : (

                  <div className="empty-state details-empty">
                    <FolderKanban size={36} />
                    <h3>Select a project</h3>
                    <p>Choose a project to view its details.</p>
                  </div>

                )}

              </aside>

            </section>

          </>
        )}

        {/* ======================================
            TEAM MEMBERS PAGE
        ====================================== */}

        {activePage === "team" && (

          <section className="workspace-grid">

            <div className="projects-panel">

              <div className="section-heading">
                <div>
                  <h2>Project Team</h2>
                  <p>Manage members and their responsibilities.</p>
                </div>
              </div>

              {selectedProject ? (
                <>

                  <div className="form-card">
                    <h3>{selectedProject.name}</h3>

                    <p className="form-hint">
                      {members.length} registered members
                    </p>

                    <div className="details-divider" />

                    <div className="member-heading">
                      <div>
                        <h3>Team Directory</h3>
                        <span>Current project members</span>
                      </div>

                      <button
                        type="button"
                        className="add-member-button"
                        onClick={() => setShowMemberForm(!showMemberForm)}
                      >
                        <Plus size={18} />
                      </button>
                    </div>

                    {showMemberForm && renderAddMemberForm()}

                    <div className="member-list">
                      {renderMemberList()}
                    </div>
                  </div>

                  <div className="form-card">
                    <h3>Switch Project</h3>

                    <label>Select Workspace</label>

                    <select
                      value={selectedProjectId ?? ""}
                      onChange={(e) =>
                        setSelectedProjectId(Number(e.target.value))
                      }
                    >
                      {projects.map((project) => (
                        <option key={project.id} value={project.id}>
                          {project.name}
                        </option>
                      ))}
                    </select>
                  </div>

                </>
              ) : (

                <div className="empty-state">
                  <Users size={38} />
                  <h3>No project selected</h3>
                  <p>Create or select a project first.</p>

                  <button
                    type="button"
                    className="primary-button"
                    onClick={() => navigateTo("overview")}
                  >
                    Go to Overview
                  </button>
                </div>

              )}

            </div>

            <aside className="details-panel">
              <h3>Team Responsibilities</h3>

              <p>
                Every project member can have an assigned role
                and responsibility.
              </p>

              <div className="details-divider" />

              <h3>Why this matters</h3>

              <p>
                RelayMap uses ownership information to identify
                responsibilities that may become unassigned when
                a team member departs.
              </p>

              <div className="details-divider" />

              <h3>Registered Users</h3>
              <h2>{users.length}</h2>

            </aside>

          </section>

        )}

        {/* ======================================
            DATA SOURCES PAGE
        ====================================== */}

        {activePage === "sources" && (

          <section className="workspace-grid">

            <div className="projects-panel">

              <div className="section-heading">
                <div>
                  <h2>Project Documents</h2>

                  <p>
                    Upload project documents and build a unified
                    knowledge base.
                  </p>
                </div>
              </div>

              {selectedProject ? (
                <>

                  {/* PROJECT SELECTOR */}

                  <div className="form-card">

                    <h3>Selected Workspace</h3>

                    <label>Select Project</label>

                    <select
                      value={selectedProjectId ?? ""}
                      onChange={(e) =>
                        setSelectedProjectId(Number(e.target.value))
                      }
                    >
                      {projects.map((project) => (
                        <option key={project.id} value={project.id}>
                          {project.name}
                        </option>
                      ))}
                    </select>

                    <p className="form-hint">
                      Uploaded documents will belong to this project.
                    </p>

                  </div>

                  {/* UPLOAD FORM */}

                  <div className="form-card">

                    <div className="form-title">
                      <h3>Upload Project Documents</h3>
                      <Upload size={21} />
                    </div>

                    <p>Select project files from your computer.</p>

                    <label htmlFor="project-files">
                      Choose Project Files
                    </label>

                    <input
                      id="project-files"
                      type="file"
                      multiple
                      accept=".pdf,.docx,.md,.csv"
                      onChange={handleFileSelection}
                    />

                    <p className="form-hint">
                      PDF, DOCX, Markdown and CSV. Maximum 20 MB per file.
                    </p>

                    <div className="details-divider" />

                    <div className="member-heading">
                      <div>
                        <h3>Selected Files</h3>
                        <span>{selectedFiles.length} files selected</span>
                      </div>

                      <FileText size={20} />
                    </div>

                    {selectedFiles.length === 0 ? (

                      <div className="empty-state">
                        <Database size={34} />
                        <h3>No documents selected</h3>
                        <p>Choose files to upload them to RelayMap.</p>
                      </div>

                    ) : (

                      <div className="member-list">

                        {selectedFiles.map((file, index) => (

                          <div
                            className="member-item"
                            key={`${file.name}-${file.size}-${index}`}
                          >
                            <div className="member-avatar">
                              <FileText size={18} />
                            </div>

                            <div className="member-info">
                              <strong>{file.name}</strong>
                              <span>{formatFileSize(file.size)}</span>
                            </div>
                          </div>

                        ))}

                      </div>

                    )}

                    <div className="action-buttons">

                      <button
                        type="button"
                        className="primary-button"
                        onClick={() => void handleUploadDocuments()}
                        disabled={
                          uploading || selectedFiles.length === 0
                        }
                      >
                        <Upload size={17} />
                        {uploading ? "Uploading..." : "Upload Documents"}
                      </button>

                      <button
                        type="button"
                        className="secondary-button"
                        onClick={clearSelectedFiles}
                        disabled={uploading || selectedFiles.length === 0}
                      >
                        <X size={17} />
                        Clear
                      </button>

                    </div>

                  </div>

                  {/* UPLOADED DOCUMENT LIBRARY */}

                  <div className="form-card">

                    <div className="member-heading">
                      <div>
                        <h3>Uploaded Documents</h3>
                        <span>
                          {documents.length} documents in this project
                        </span>
                      </div>

                      <button
                        type="button"
                        className="refresh-button"
                        title="Refresh document list"
                        onClick={async () => {
                          if (selectedProjectId === null) return;

                          setDocumentLoading(true);

                          try {
                            const response =
                              await api.get<ProjectDocument[]>(
                                `/api/projects/${selectedProjectId}/documents`
                              );

                            setDocuments(response.data);
                            setSuccess("Document list refreshed.");
                          } catch (err) {
                            setError(getApiError(err));
                          } finally {
                            setDocumentLoading(false);
                          }
                        }}
                      >
                        <RefreshCw size={17} />
                      </button>
                    </div>

                    {documentLoading ? (

                      <p className="muted-text">
                        Loading uploaded documents...
                      </p>

                    ) : documents.length === 0 ? (

                      <div className="empty-state">
                        <FileText size={34} />
                        <h3>No uploaded documents yet</h3>
                        <p>Your uploaded files will appear here.</p>
                      </div>

                    ) : (

                      <div className="member-list">

                        {documents.map((document) => (

                          <div className="member-item" key={document.id}>

                            <div className="member-avatar">
                              <FileText size={18} />
                            </div>

                            <div className="member-info">
                              <strong>
                                {document.original_filename}
                              </strong>

                              <span>
                                {document.file_type.toUpperCase()} ·{" "}
                                {formatFileSize(document.size_bytes)}
                              </span>

                              <span>
                                Uploaded:{" "}
                                {new Date(
                                  document.uploaded_at
                                ).toLocaleString()}
                              </span>

                              {/* NEW: EXTRACT KNOWLEDGE BUTTON */}

                              <button
                                type="button"
                                className="secondary-button"
                                style={{
                                  marginTop: "10px",
                                  padding: "8px 12px",
                                  fontSize: "12px",
                                  width: "fit-content",
                                }}
                                onClick={() =>
                                  void handleExtractKnowledge(document)
                                }
                                disabled={
                                  extractingDocumentId !== null
                                }
                              >
                                <Sparkles size={15} />

                                {extractingDocumentId === document.id
                                  ? "Extracting Knowledge..."
                                  : "Extract Knowledge"}
                              </button>

                              {extractionMessages[document.id] && (
                                <span
                                  style={{
                                    color: extractionMessages[
                                      document.id
                                    ].startsWith("Extraction failed")
                                      ? "#ff8888"
                                      : "#75d7aa",
                                    marginTop: "7px",
                                    fontSize: "11px",
                                  }}
                                >
                                  {extractionMessages[document.id]}
                                </span>
                              )}
                            </div>

                            <span className="member-role">
                              {document.extraction_status}
                            </span>

                          </div>

                        ))}

                      </div>

                    )}

                  </div>

                </>
              ) : (

                <div className="empty-state">
                  <Database size={38} />
                  <h3>Select a project first</h3>

                  <p>
                    Create or select a project before uploading documents.
                  </p>

                  <button
                    type="button"
                    className="primary-button"
                    onClick={() => navigateTo("overview")}
                  >
                    Go to Overview
                  </button>
                </div>

              )}

            </div>

            {/* KNOWLEDGE INGESTION PANEL */}

            <aside className="details-panel">

              <h3>Knowledge Ingestion</h3>

              <p>
                RelayMap extracts information from project documents
                and prepares it for structured knowledge reconstruction.
              </p>

              <div className="details-divider" />

              <h3>Supported Formats</h3>

              <div className="member-list">

                {[
                  ["PDF", "PDF Documents"],
                  ["DOCX", "Word Documents"],
                  ["MD", "Markdown Files"],
                  ["CSV", "CSV Files"],
                ].map(([extension, label]) => (

                  <div className="member-item" key={extension}>
                    <div className="member-avatar">
                      {extension}
                    </div>

                    <div className="member-info">
                      <strong>{label}</strong>
                      <span>Supported for upload and extraction</span>
                    </div>
                  </div>

                ))}

              </div>

              <div className="details-divider" />

              <h3>Processing Pipeline</h3>

              <p>1. Upload project documents</p>
              <p>2. Extract text and create evidence chunks</p>
              <p>3. Click Extract Knowledge to identify candidates</p>
              <p>4. Review and approve the extracted information</p>

              <div className="details-divider" />

              <h3>Storage Information</h3>

              <p>
                Original files are stored in backend storage.
                Document metadata and extracted text are registered
                in PostgreSQL.
              </p>

              <div className="details-divider" />

              <h3>Important</h3>

              <p>
                Extracted knowledge starts as a candidate.
                It must be reviewed against its original evidence
                before being used as verified project knowledge.
              </p>

            </aside>

          </section>

        )}

        {/* ======================================
            KNOWLEDGE REVIEW PAGE
        ====================================== */}

        {activePage === "knowledge" && (
          selectedProjectId !== null ? (
            <KnowledgeReview
              projectId={selectedProjectId}
              members={members.map((member) => ({
                user_id: member.user_id,
                full_name: member.full_name,
                role: member.role,
              }))}
            />
          ) : (
            <div className="empty-state">
              <ShieldCheck size={38} />
              <h3>No project selected</h3>
              <p>Select a project before reviewing knowledge records.</p>

              <button
                type="button"
                className="primary-button"
                onClick={() => navigateTo("overview")}
              >
                Go to Overview
              </button>
            </div>
          )
        )}

        {/* ======================================
            CONTINUITY DASHBOARD PAGE
        ====================================== */}

        {activePage === "continuity" && (
          selectedProjectId !== null ? (
            <ContinuityDashboard projectId={selectedProjectId} />
          ) : (
            <div className="empty-state">
              <GitBranch size={38} />
              <h3>No project selected</h3>
              <p>Select a project before checking continuity risks.</p>

              <button
                type="button"
                className="primary-button"
                onClick={() => navigateTo("overview")}
              >
                Go to Overview
              </button>
            </div>
          )
        )}

        {/* ======================================
            KNOWLEDGE MAP PAGE
        ====================================== */}

        {activePage === "map" && (
          selectedProjectId !== null ? (
            <KnowledgeMap projectId={selectedProjectId} />
          ) : (
            <div className="empty-state">
              <Network size={38} />
              <h3>No project selected</h3>
              <p>Select a project before viewing its Knowledge Map.</p>

              <button
                type="button"
                className="primary-button"
                onClick={() => navigateTo("overview")}
              >
                Go to Overview
              </button>
            </div>
          )
        )}

        {/* ======================================
            HANDOVER CENTER PAGE
        ====================================== */}

        {activePage === "handover" && (
          selectedProjectId !== null ? (
            <HandoverDashboard projectId={selectedProjectId} />
          ) : (
            <div className="empty-state">
              <FileText size={38} />
              <h3>No project selected</h3>
              <p>Select a project before viewing its Handover Center.</p>

              <button
                type="button"
                className="primary-button"
                onClick={() => navigateTo("overview")}
              >
                Go to Overview
              </button>
            </div>
          )
        )}

      </main>
    </div>
  );
}

export default App;