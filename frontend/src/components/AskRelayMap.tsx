import { useEffect, useState, type FormEvent } from "react";
import {
  AlertCircle,
  BookOpen,
  CheckCircle2,
  FileText,
  MessageSquare,
  Send,
  Sparkles,
} from "lucide-react";

import { api, getApiError } from "../services/api";
import "./AskRelayMap.css";


interface ProjectQuestionCitation {
  knowledge_item_id: number;
  title: string;
  document_name: string;
  source_locator: string;
  excerpt: string;
  item_type: string;
}

interface ProjectQuestionResponse {
  project_id: number;
  question: string;
  answer: string;
  sufficient_evidence: boolean;
  uncertainty: string;
  citations: ProjectQuestionCitation[];
  retrieval_method: string;
  model: string;
}

interface AskRelayMapProps {
  projectId: number;
}


function AskRelayMap({ projectId }: AskRelayMapProps) {
  const [question, setQuestion] = useState("");
  const [result, setResult] =
    useState<ProjectQuestionResponse | null>(null);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    setQuestion("");
    setResult(null);
    setError("");
  }, [projectId]);

  async function handleSubmit(
    event: FormEvent<HTMLFormElement>
  ) {
    event.preventDefault();

    const cleanQuestion = question.trim();

    if (cleanQuestion.length < 3) {
      setError("Please enter a more specific question.");
      return;
    }

    setLoading(true);
    setError("");
    setResult(null);

    try {
      const response =
        await api.post<ProjectQuestionResponse>(
          `/api/projects/${projectId}/ask`,
          {
            question: cleanQuestion,
          }
        );

      setResult(response.data);

    } catch (err) {
      setError(getApiError(err));

    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="ask-page">

      <div className="ask-intro">
        <div className="ask-eyebrow">
          <Sparkles size={15} />
          EVIDENCE-GROUNDED AI
        </div>

        <h2>Ask RelayMap</h2>

        <p>
          Ask questions about your project. RelayMap searches
          approved project knowledge and provides answers
          with links to the supporting source records.
        </p>
      </div>


      <div className="ask-panel">

        <div className="ask-panel-heading">
          <div className="ask-panel-icon">
            <MessageSquare size={19} />
          </div>

          <div>
            <h3>Project Knowledge Assistant</h3>
            <p>
              Answers are based only on approved knowledge records.
            </p>
          </div>
        </div>


        <form className="ask-form" onSubmit={handleSubmit}>

          <label htmlFor="relaymap-question">
            Your question
          </label>

          <textarea
            id="relaymap-question"
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            placeholder="Example: What are the main unresolved blockers in this project?"
            rows={4}
            maxLength={1200}
            disabled={loading}
          />

          <div className="ask-form-footer">
            <span>
              {question.length}/1200 characters
            </span>

            <button
              type="submit"
              className="ask-submit"
              disabled={loading || question.trim().length < 3}
            >
              <Send size={16} />
              {loading ? "Analysing evidence..." : "Ask RelayMap"}
            </button>
          </div>

        </form>


        {error && (
          <div className="ask-error">
            <AlertCircle size={17} />
            <span>{error}</span>
          </div>
        )}

      </div>


      {result && (
        <div className="ask-result">

          <div
            className={`ask-answer-status ${
              result.sufficient_evidence
                ? "ask-status-supported"
                : "ask-status-insufficient"
            }`}
          >
            {result.sufficient_evidence ? (
              <CheckCircle2 size={17} />
            ) : (
              <AlertCircle size={17} />
            )}

            <span>
              {result.sufficient_evidence
                ? "Supported by approved project evidence"
                : "Insufficient approved evidence"}
            </span>
          </div>


          <div className="ask-answer-card">

            <div className="ask-result-heading">
              <Sparkles size={18} />
              <h3>RelayMap's Answer</h3>
            </div>

            <p className="ask-answer-text">
              {result.answer}
            </p>

            {result.uncertainty && (
              <div className="ask-uncertainty">
                <strong>Note:</strong> {result.uncertainty}
              </div>
            )}

          </div>


          <div className="ask-citations-card">

            <div className="ask-result-heading">
              <BookOpen size={18} />
              <h3>Supporting Evidence</h3>
              <span className="ask-citation-count">
                {result.citations.length}
              </span>
            </div>

            {result.citations.length === 0 ? (

              <p className="ask-empty-citations">
                No supporting records were cited for this answer.
                Review or add project knowledge to improve the result.
              </p>

            ) : (

              <div className="ask-citation-list">

                {result.citations.map((citation) => (

                  <article
                    className="ask-citation"
                    key={citation.knowledge_item_id}
                  >

                    <div className="ask-citation-top">
                      <div className="ask-citation-file-icon">
                        <FileText size={17} />
                      </div>

                      <div className="ask-citation-info">
                        <strong>{citation.title}</strong>

                        <span>
                          {citation.document_name}
                          {" · "}
                          {citation.source_locator}
                        </span>
                      </div>

                      <span className="ask-citation-type">
                        {citation.item_type}
                      </span>
                    </div>

                    <blockquote>
                      “{citation.excerpt}”
                    </blockquote>

                    <small>
                      Approved knowledge record #{citation.knowledge_item_id}
                    </small>

                  </article>

                ))}

              </div>

            )}

          </div>


          <p className="ask-disclaimer">
            RelayMap provides evidence-backed assistance, not
            automatic project decisions. Verify important actions
            against the original source documents.
          </p>

        </div>
      )}

    </section>
  );
}

export default AskRelayMap;