import { useEffect, useState } from "react";
import {
  GitBranch,
  RefreshCw,
  GitPullRequest,
  CircleDot,
  ExternalLink,
  CheckCircle2,
  AlertTriangle,
  Search,
  Sparkles,
} from "lucide-react";

import { api, getApiError } from "../services/api";
import "./GitHubSyncPanel.css";

type GitHubRecord = {
  id: number;
  github_id: number;
  number: number;
  type: "issue" | "pull_request";
  title: string;
  body: string | null;
  state: string | null;
  url: string | null;
  author: string | null;
  assignees: {
    login: string | null;
    profile_url: string | null;
  }[];
  labels: string[];
  draft: boolean;
  merged: boolean;
  base_branch: string | null;
  head_branch: string | null;
  github_updated_at: string | null;
  synced_at: string | null;
};

type SyncSummary = {
  message: string;
  repository: string;
  created: number;
  updated: number;
  skipped: number;
  fetched_issues: number;
  fetched_pull_requests: number;
  total_stored_records: number;
  synced_at: string;
  pagination_note?: string;
};

type ExtractionSummary = {
  message: string;
  project_id: number;
  records_processed: number;
  documents_created: number;
  chunks_created: number;
  candidates_created: number;
  duplicates_skipped: number;
  review_status: string;
  important_note?: string;
};

type Props = {
  projectId: number;
};

export default function GitHubSyncPanel({ projectId }: Props) {
  const [owner, setOwner] = useState("omkarpsawardekar-ui");
  const [repo, setRepo] = useState("RelayMap");

  const [items, setItems] = useState<GitHubRecord[]>([]);
  const [total, setTotal] = useState(0);

  const [loading, setLoading] = useState(true);
  const [previewing, setPreviewing] = useState(false);
  const [syncing, setSyncing] = useState(false);

  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [summary, setSummary] = useState<SyncSummary | null>(null);
  const [extracting, setExtracting] = useState(false);
  const [extractionSummary, setExtractionSummary] = useState<ExtractionSummary | null>(null);
  const [repositoryInfo, setRepositoryInfo] = useState<any>(null);

  const [filter, setFilter] = useState<"all" | "issue" | "pull_request">(
    "all"
  );

  async function loadItems() {
    setLoading(true);
    setError("");

    try {
      const response = await api.get(
        `/api/projects/${projectId}/github/items`
      );

      setItems(response.data.items ?? []);
      setTotal(response.data.total ?? 0);
    } catch (err) {
      setError(getApiError(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    setItems([]);
    setTotal(0);
    setSummary(null);
    setRepositoryInfo(null);

    void loadItems();
  }, [projectId]);

  async function previewRepository() {
    if (!owner.trim() || !repo.trim()) {
      setError("Enter both the GitHub owner and repository name.");
      return;
    }

    setPreviewing(true);
    setError("");
    setMessage("");

    try {
      const response = await api.post(
        `/api/projects/${projectId}/github/preview`,
        {
          owner: owner.trim(),
          repo: repo.trim(),
        }
      );

      setRepositoryInfo(response.data.repository);

      setMessage(
        `Repository found: ${response.data.repository.full_name}`
      );
    } catch (err) {
      setError(getApiError(err));
      setRepositoryInfo(null);
    } finally {
      setPreviewing(false);
    }
  }

  async function syncRepository() {
    if (!owner.trim() || !repo.trim()) {
      setError("Enter both the GitHub owner and repository name.");
      return;
    }

    setSyncing(true);
    setError("");
    setMessage("");
    setSummary(null);

    try {
      const response = await api.post<SyncSummary>(
        `/api/projects/${projectId}/github/sync`,
        {
          owner: owner.trim(),
          repo: repo.trim(),
        }
      );

      setSummary(response.data);
      setRepositoryInfo({
        full_name: response.data.repository,
        html_url: `https://github.com/${response.data.repository}`,
      });

      setMessage("GitHub repository synchronized successfully.");

      await loadItems();
    } catch (err) {
      setError(getApiError(err));
    } finally {
      setSyncing(false);
    }
  }

  async function createKnowledgeCandidates() {
  setExtracting(true);
  setError("");
  setMessage("");
  setExtractionSummary(null);

  try {
    const response = await api.post<ExtractionSummary>(
      `/api/projects/${projectId}/github/extract`
    );

    const result = response.data;

    setExtractionSummary(result);

    if (result.candidates_created > 0) {
      setMessage(
        `${result.candidates_created} knowledge candidate(s) created successfully!`
      );
    } else {
      setMessage(
        "Extraction completed, but no new candidates were created. Check the source content or whether these records were already extracted."
      );
    }
  } catch (err) {
    setError(
      `Could not extract GitHub knowledge: ${getApiError(err)}`
    );
  } finally {
    setExtracting(false);
  }
}

  const visibleItems = items.filter((item) => {
    if (filter === "all") return true;
    return item.type === filter;
  });

  const issueCount = items.filter(
    (item) => item.type === "issue"
  ).length;

  const pullRequestCount = items.filter(
    (item) => item.type === "pull_request"
  ).length;

  return (
    <section className="github-panel">

      <div className="github-panel-header">
        <div className="github-heading-icon">
          <GitBranch size={23} />
        </div>

        <div>
          <h3>GitHub Integration</h3>
          <p>
            Import repository issues and pull requests into RelayMap.
          </p>
        </div>

        <span className="github-public-badge">PUBLIC REPO</span>
      </div>

      {error && (
        <div className="github-message error">
          <AlertTriangle size={16} />
          {error}
        </div>
      )}

      {message && (
        <div className="github-message success">
          <CheckCircle2 size={16} />
          {message}
        </div>
      )}

      <div className="github-repository-form">

        <div className="github-input-group">
          <label htmlFor="github-owner">Repository Owner</label>

          <input
            id="github-owner"
            value={owner}
            onChange={(event) => setOwner(event.target.value)}
            placeholder="GitHub username"
          />
        </div>

        <div className="github-input-group">
          <label htmlFor="github-repository">Repository Name</label>

          <input
            id="github-repository"
            value={repo}
            onChange={(event) => setRepo(event.target.value)}
            placeholder="Repository name"
          />
        </div>

        <div className="github-actions">
          <button
            type="button"
            className="github-preview-button"
            onClick={() => void previewRepository()}
            disabled={previewing || syncing}
          >
            {previewing ? (
              <RefreshCw className="github-spin" size={15} />
            ) : (
              <Search size={15} />
            )}

            {previewing ? "Checking..." : "Preview"}
          </button>

          <button
            type="button"
            className="github-sync-button"
            onClick={() => void syncRepository()}
            disabled={syncing || previewing}
          >
            {syncing ? (
              <RefreshCw className="github-spin" size={16} />
            ) : (
              <GitBranch size={16} />
            )}

            {syncing ? "Syncing..." : "Sync Now"}
          </button>
        </div>

      </div>

      {repositoryInfo && (
        <div className="github-repository-info">
          <div>
            <strong>{repositoryInfo.full_name}</strong>

            <span>
              {repositoryInfo.description || "Public GitHub repository"}
            </span>
          </div>

          {repositoryInfo.html_url && (
            <a
              href={repositoryInfo.html_url}
              target="_blank"
              rel="noopener noreferrer"
              aria-label="Open GitHub repository"
            >
              <ExternalLink size={17} />
            </a>
          )}
        </div>
      )}

      {summary && (
        <div className="github-sync-summary">

          <strong>Latest synchronization</strong>

          <div className="github-sync-stats">
            <div>
              <span>{summary.created}</span>
              <small>Created</small>
            </div>

            <div>
              <span>{summary.updated}</span>
              <small>Updated</small>
            </div>

            <div>
              <span>{summary.skipped}</span>
              <small>Skipped</small>
            </div>

            <div>
              <span>{summary.total_stored_records}</span>
              <small>Total stored</small>
            </div>
          </div>

          {summary.pagination_note && (
            <p>{summary.pagination_note}</p>
          )}

        </div>
      )}

      {/* GITHUB KNOWLEDGE EXTRACTION */}

<div className="github-extraction-panel">
  <div className="github-extraction-heading">
    <div>
      <h4>Knowledge Reconstruction</h4>
      <p>
        Convert imported GitHub issues and pull requests into
        evidence-backed knowledge candidates.
      </p>
    </div>

    <Sparkles size={21} />
  </div>

  <button
    type="button"
    className="github-extract-button"
    onClick={() => void createKnowledgeCandidates()}
    disabled={extracting || syncing || loading || total === 0}
  >
    {extracting ? (
      <RefreshCw className="github-spin" size={16} />
    ) : (
      <Sparkles size={16} />
    )}

    {extracting
      ? "Creating Candidates..."
      : "Create Knowledge Candidates"}
  </button>

  {total === 0 && (
    <p className="github-extraction-hint">
      Synchronize a repository before extracting its knowledge.
    </p>
  )}

  {extractionSummary && (
    <div className="github-extraction-results">
      <div>
        <strong>{extractionSummary.records_processed}</strong>
        <span>Records processed</span>
      </div>

      <div>
        <strong>{extractionSummary.documents_created}</strong>
        <span>Sources created</span>
      </div>

      <div>
        <strong>{extractionSummary.chunks_created}</strong>
        <span>Evidence chunks</span>
      </div>

      <div>
        <strong>{extractionSummary.candidates_created}</strong>
        <span>New candidates</span>
      </div>
    </div>
  )}

  {extractionSummary && (
    <p className="github-extraction-hint">
      These candidates have status Pending. Review them in
      Knowledge Review before treating them as verified facts.
    </p>
  )}
</div>

      <div className="github-imported-section">

        <div className="github-imported-heading">
          <div>
            <h4>Imported GitHub Records</h4>
            <span>{total} records stored in PostgreSQL</span>
          </div>

          <button
            type="button"
            className="github-refresh-button"
            onClick={() => void loadItems()}
            disabled={loading}
            title="Refresh imported records"
          >
            <RefreshCw
              size={16}
              className={loading ? "github-spin" : ""}
            />
          </button>
        </div>

        <div className="github-record-filters">

          <button
            type="button"
            className={filter === "all" ? "active" : ""}
            onClick={() => setFilter("all")}
          >
            All ({total})
          </button>

          <button
            type="button"
            className={filter === "issue" ? "active" : ""}
            onClick={() => setFilter("issue")}
          >
            Issues ({issueCount})
          </button>

          <button
            type="button"
            className={filter === "pull_request" ? "active" : ""}
            onClick={() => setFilter("pull_request")}
          >
            Pull Requests ({pullRequestCount})
          </button>

        </div>

        {loading ? (
          <div className="github-empty">
            <RefreshCw className="github-spin" size={21} />
            <p>Loading imported GitHub records...</p>
          </div>
        ) : visibleItems.length === 0 ? (
          <div className="github-empty">
            <GitBranch size={29} />

            <strong>No GitHub records found</strong>

            <p>
              Preview a repository and click Sync Now to import its records.
            </p>
          </div>
        ) : (
          <div className="github-record-list">

            {visibleItems.map((item) => (

              <article
                className="github-record-card"
                key={item.id}
              >
                <div className="github-record-icon">
                  {item.type === "issue" ? (
                    <CircleDot size={19} />
                  ) : (
                    <GitPullRequest size={19} />
                  )}
                </div>

                <div className="github-record-content">

                  <div className="github-record-title">
                    <strong>
                      #{item.number} {item.title}
                    </strong>

                    <span
                      className={`github-state ${item.state ?? "unknown"}`}
                    >
                      {item.merged
                        ? "Merged"
                        : item.state ?? "Unknown"}
                    </span>
                  </div>

                  <div className="github-record-meta">
                    <span>
                      {item.type === "issue"
                        ? "Issue"
                        : "Pull Request"}
                    </span>

                    {item.author && <span>by {item.author}</span>}

                    {item.assignees?.length > 0 && (
                      <span>
                        Assigned to{" "}
                        {item.assignees
                          .map((person) => person.login)
                          .filter(Boolean)
                          .join(", ")}
                      </span>
                    )}
                  </div>

                  {item.labels?.length > 0 && (
                    <div className="github-labels">
                      {item.labels.map((label, index) => (
                        <span key={`${label}-${index}`}>{label}</span>
                      ))}
                    </div>
                  )}

                  {item.url && (
                    <a
                      className="github-record-link"
                      href={item.url}
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      View on GitHub
                      <ExternalLink size={12} />
                    </a>
                  )}

                </div>

              </article>

            ))}

          </div>
        )}

      </div>

    </section>
  );
}