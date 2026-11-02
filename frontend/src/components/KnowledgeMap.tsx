
import { useCallback, useEffect, useMemo, useState, type MouseEvent } from "react";

import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  MarkerType,
  useNodesState,
  useEdgesState,
  type Node,
  type Edge,
} from "@xyflow/react";

import "@xyflow/react/dist/style.css";

import RelationshipManager from "./RelationshipManager";

import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  FileText,
  GitBranch,
  RefreshCw,
  Search,
  Users,
} from "lucide-react";

import { api, getApiError } from "../services/api";
import "./KnowledgeMap.css";


interface ApiGraphNode {
  id: string;
  type: string;
  position: {
    x: number;
    y: number;
  };
  data: Record<string, unknown>;
}

interface ApiGraphEdge {
  id: string;
  source: string;
  target: string;
  label: string;
  type?: string;
  animated?: boolean;
  data: Record<string, unknown>;
}

interface KnowledgeGraphResponse {
  project_id: number;
  nodes: ApiGraphNode[];
  edges: ApiGraphEdge[];
  summary: {
    people: number;
    knowledge_items: number;
    relationships: number;
    assignments: number;
    total_nodes: number;
    total_edges: number;
  };
}

interface GraphNodeData extends Record<string, unknown> {
  label: string;
  kind: "person" | "knowledge";
  item_type?: string;
  role?: string;
  membership_status?: string;
  responsibility?: string | null;
  work_status?: string;
  source_filename?: string;
  source_locator?: string;
  source_excerpt?: string;
  assigned_to_user_id?: number | null;
  knowledge_item_id?: number;
  user_id?: number;
}

interface GraphEdgeData extends Record<string, unknown> {
  relation_type?: string;
  relationship_id?: number;
  work_status?: string;
  evidence_excerpt?: string;
  source_filename?: string;
  source_locator?: string;
}

type MapNode = Node<GraphNodeData>;
type MapEdge = Edge<GraphEdgeData>;

type MapFilter = "all" | "people" | "knowledge";


interface KnowledgeMapProps {
  projectId: number;
}


function getNodeStyle(kind: string, itemType?: string) {
  if (kind === "person") {
    return {
      background: "#EAF5F1",
      border: "1px solid #8BC8B5",
      color: "#245F51",
    };
  }

  const palette: Record<string, { background: string; border: string; color: string }> = {
    task: {
      background: "#EEF3FC",
      border: "1px solid #A7BDE5",
      color: "#345E94",
    },
    decision: {
      background: "#F4EFFA",
      border: "1px solid #CCB9E5",
      color: "#70518F",
    },
    responsibility: {
      background: "#EDF7F0",
      border: "1px solid #A9D0B2",
      color: "#477D58",
    },
    dependency: {
      background: "#FBF4E8",
      border: "1px solid #E7C995",
      color: "#8B682F",
    },
    blocker: {
      background: "#FFF0ED",
      border: "1px solid #E6B1A8",
      color: "#A65349",
    },
    question: {
      background: "#EDF2F7",
      border: "1px solid #B9C8D8",
      color: "#526D86",
    },
  };

  return (
    palette[itemType || ""] ?? {
      background: "#F3F6F5",
      border: "1px solid #CBD7D3",
      color: "#455B55",
    }
  );
}


function getEdgeColor(relationType?: string): string {
  const colors: Record<string, string> = {
    assigned_to: "#27917D",
    depends_on: "#6485B9",
    blocks: "#D07861",
    related_to: "#89969C",
    supports: "#679D79",
    informs: "#9278AE",
  };

  return colors[relationType || ""] || "#8C9A9A";
}


function KnowledgeMap({ projectId }: KnowledgeMapProps) {
  const [nodes, setNodes, onNodesChange] =
    useNodesState<MapNode>([]);

  const [edges, setEdges, onEdgesChange] =
    useEdgesState<MapEdge>([]);

  const [summary, setSummary] =
    useState<KnowledgeGraphResponse["summary"]>({
      people: 0,
      knowledge_items: 0,
      relationships: 0,
      assignments: 0,
      total_nodes: 0,
      total_edges: 0,
    });

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const [filter, setFilter] = useState<MapFilter>("all");
  const [searchText, setSearchText] = useState("");

  const [selectedNode, setSelectedNode] =
    useState<MapNode | null>(null);

  const [selectedEdge, setSelectedEdge] =
    useState<MapEdge | null>(null);


  // --------------------------------------------------
  // LOAD GRAPH FROM FASTAPI
  // --------------------------------------------------

  const loadGraph = useCallback(async () => {
    setLoading(true);
    setError("");

    try {
      const response = await api.get<KnowledgeGraphResponse>(
        `/api/projects/${projectId}/knowledge-graph`
      );

      const graph = response.data;

      const graphNodes: MapNode[] = graph.nodes.map((node) => {
        const kind =
          node.data.kind === "person"
            ? "person"
            : "knowledge";

        const itemType = String(
          node.data.item_type ?? ""
        );

        const nodeStyle = getNodeStyle(kind, itemType);

        return {
          id: node.id,
          type: "default",
          position: {
            x: node.position.x,
            y: node.position.y,
          },
          data: {
            ...node.data,
            label: String(node.data.label ?? node.id),
            kind,
          } as GraphNodeData,
          style: {
            width: 250,
            padding: 14,
            borderRadius: 12,
            fontSize: 12,
            fontWeight: 650,
            border: nodeStyle.border,
            background: nodeStyle.background,
            color: nodeStyle.color,
            boxShadow: "0 3px 12px rgba(24, 49, 44, 0.07)",
          },
        };
      });

      const graphEdges: MapEdge[] = graph.edges.map((edge) => {
        const relationType = String(
          edge.data.relation_type ?? ""
        );

        const color = getEdgeColor(relationType);

        return {
          id: edge.id,
          source: edge.source,
          target: edge.target,
          type: "smoothstep",
          label: edge.label,
          animated: edge.animated,
          markerEnd: {
            type: MarkerType.ArrowClosed,
            color,
          },
          style: {
            stroke: color,
            strokeWidth: 2,
          },
          labelStyle: {
            fill: "#52635F",
            fontSize: 10,
            fontWeight: 600,
          },
          labelBgStyle: {
            fill: "#FFFFFF",
            fillOpacity: 0.95,
          },
          labelBgPadding: [5, 3] as [number, number],
          data: edge.data as GraphEdgeData,
        };
      });

      setNodes(graphNodes);
      setEdges(graphEdges);
      setSummary(graph.summary);

      setSelectedNode(null);
      setSelectedEdge(null);

    } catch (err) {
      setError(getApiError(err));
    } finally {
      setLoading(false);
    }
  }, [projectId, setNodes, setEdges]);


  useEffect(() => {
    void loadGraph();
  }, [loadGraph]);


  // --------------------------------------------------
  // FILTER AND SEARCH NODES
  // --------------------------------------------------

  const visibleNodes = useMemo(() => {
    const query = searchText.trim().toLowerCase();

    return nodes.filter((node) => {
      const matchesFilter =
        filter === "all" ||
        (filter === "people" && node.data.kind === "person") ||
        (filter === "knowledge" && node.data.kind === "knowledge");

      const matchesSearch =
        !query ||
        String(node.data.label).toLowerCase().includes(query) ||
        String(node.data.item_type ?? "").toLowerCase().includes(query);

      return matchesFilter && matchesSearch;
    });
  }, [nodes, filter, searchText]);


  const visibleNodeIds = useMemo(
    () => new Set(visibleNodes.map((node) => node.id)),
    [visibleNodes]
  );


  const visibleEdges = useMemo(
    () =>
      edges.filter(
        (edge) =>
          visibleNodeIds.has(edge.source) &&
          visibleNodeIds.has(edge.target)
      ),
    [edges, visibleNodeIds]
  );


  // --------------------------------------------------
  // NODE AND EDGE SELECTION
  // --------------------------------------------------

  function handleNodeClick(
    _event: MouseEvent,
    node: MapNode
  ) {
    setSelectedNode(node);
    setSelectedEdge(null);
  }


  function handleEdgeClick(
    _event: MouseEvent,
    edge: MapEdge
  ) {
    setSelectedEdge(edge);
    setSelectedNode(null);
  }


  function clearSelection() {
    setSelectedNode(null);
    setSelectedEdge(null);
  }


  // --------------------------------------------------
  // SUMMARY AND DETAILS
  // --------------------------------------------------

  const selectedData = selectedNode?.data;

  const selectedEdgeData = selectedEdge?.data;


  return (
    <section className="knowledge-map-page">

      {/* HEADER */}

      <div className="knowledge-map-header">

        <div>
          <div className="knowledge-map-eyebrow">
            <GitBranch size={15} />
            PROJECT KNOWLEDGE GRAPH
          </div>

          <h2>Knowledge Map</h2>

          <p>
            Explore how project members, responsibilities,
            tasks, decisions and dependencies connect.
          </p>
        </div>

        <button
          type="button"
          className="knowledge-map-refresh"
          onClick={() => void loadGraph()}
          disabled={loading}
        >
          <RefreshCw
            size={16}
            className={loading ? "knowledge-map-spinning" : ""}
          />
          Refresh Graph
        </button>

      </div>


      {/* SUMMARY */}

      <div className="knowledge-map-stats">

        <div className="knowledge-map-stat">
          <Users size={19} />
          <div>
            <span>People</span>
            <strong>{summary.people}</strong>
          </div>
        </div>

        <div className="knowledge-map-stat">
          <FileText size={19} />
          <div>
            <span>Knowledge Items</span>
            <strong>{summary.knowledge_items}</strong>
          </div>
        </div>

        <div className="knowledge-map-stat">
          <GitBranch size={19} />
          <div>
            <span>Relationships</span>
            <strong>{summary.relationships}</strong>
          </div>
        </div>

        <div className="knowledge-map-stat">
          <Activity size={19} />
          <div>
            <span>Assignments</span>
            <strong>{summary.assignments}</strong>
          </div>
        </div>

      </div>


      {/* ERROR */}

      {error && (
        <div className="knowledge-map-error">
          <AlertTriangle size={17} />
          {error}
        </div>
      )}


      {/* GRAPH FILTERS */}

      <div className="knowledge-map-toolbar">

        <div className="knowledge-map-filters">

          <button
            type="button"
            className={filter === "all" ? "map-filter active" : "map-filter"}
            onClick={() => {
              setFilter("all");
              clearSelection();
            }}
          >
            All
          </button>

          <button
            type="button"
            className={filter === "people" ? "map-filter active" : "map-filter"}
            onClick={() => {
              setFilter("people");
              clearSelection();
            }}
          >
            <Users size={14} />
            People
          </button>

          <button
            type="button"
            className={filter === "knowledge" ? "map-filter active" : "map-filter"}
            onClick={() => {
              setFilter("knowledge");
              clearSelection();
            }}
          >
            <FileText size={14} />
            Knowledge
          </button>

        </div>

        <div className="knowledge-map-search">
          <Search size={15} />

          <input
            value={searchText}
            onChange={(event) => {
              setSearchText(event.target.value);
              clearSelection();
            }}
            placeholder="Search nodes..."
          />
        </div>

      </div>


      {/* GRAPH AND INSPECTOR */}

      <div className="knowledge-map-workspace">

        <div className="knowledge-map-canvas">

          {loading ? (

            <div className="knowledge-map-loading">
              <RefreshCw
                size={28}
                className="knowledge-map-spinning"
              />
              <strong>Building your knowledge graph...</strong>
            </div>

          ) : visibleNodes.length === 0 ? (

            <div className="knowledge-map-loading">
              <FileText size={34} />

              <strong>No matching graph nodes</strong>

              <span>
                Approve knowledge records in Knowledge Review
                to populate the knowledge graph.
              </span>
            </div>

          ) : (

            <ReactFlow
              nodes={visibleNodes}
              edges={visibleEdges}
              onNodesChange={onNodesChange}
              onEdgesChange={onEdgesChange}
              onNodeClick={handleNodeClick}
              onEdgeClick={handleEdgeClick}
              onPaneClick={clearSelection}
              fitView
              fitViewOptions={{
                padding: 0.25,
                maxZoom: 1.1,
              }}
              minZoom={0.15}
              maxZoom={1.8}
              nodesConnectable={false}
              elementsSelectable
              deleteKeyCode={null}
              proOptions={{
                hideAttribution: false,
              }}
            >

              <Background gap={22} size={1} />

              <Controls />

              <MiniMap
                pannable
                zoomable
              />

            </ReactFlow>

          )}

        </div>


        {/* DETAILS INSPECTOR */}

        <aside className="knowledge-map-inspector">

          <div className="knowledge-map-inspector-heading">
            <h3>Graph Inspector</h3>
            <span>Selected item details</span>
          </div>


          {selectedNode && selectedData ? (

            <div className="knowledge-map-details">

              <span className="knowledge-map-detail-type">
                {String(selectedData.kind)}
                {selectedData.item_type
                  ? ` · ${String(selectedData.item_type)}`
                  : ""}
              </span>

              <h4>{String(selectedData.label)}</h4>

              {selectedData.kind === "person" ? (

                <>

                  <div className="map-detail-row">
                    <span>Project Role</span>
                    <strong>{String(selectedData.role ?? "Unknown")}</strong>
                  </div>

                  <div className="map-detail-row">
                    <span>Membership</span>
                    <strong>
                      {String(selectedData.membership_status ?? "Unknown")}
                    </strong>
                  </div>

                  <div className="map-detail-block">
                    <span>Responsibility</span>
                    <p>
                      {String(
                        selectedData.responsibility ??
                        "No responsibility recorded."
                      )}
                    </p>
                  </div>

                  <div className="map-detail-row">
                    <span>User ID</span>
                    <strong>{String(selectedData.user_id ?? "—")}</strong>
                  </div>

                </>

              ) : (

                <>

                  <div className="map-detail-row">
                    <span>Work Status</span>
                    <strong>
                      {String(selectedData.work_status ?? "Unknown")}
                    </strong>
                  </div>

                  <div className="map-detail-block">
                    <span>Source Document</span>
                    <p>
                      {String(
                        selectedData.source_filename ?? "Unavailable"
                      )}
                    </p>
                  </div>

                  <div className="map-detail-row">
                    <span>Source Location</span>
                    <strong>
                      {String(
                        selectedData.source_locator ?? "Unavailable"
                      )}
                    </strong>
                  </div>

                  <div className="map-detail-block">
                    <span>Supporting Evidence</span>
                    <p className="map-evidence-text">
                      {String(
                        selectedData.source_excerpt ??
                        "No source excerpt is available."
                      )}
                    </p>
                  </div>

                  <div className="map-detail-row">
                    <span>Knowledge Item ID</span>
                    <strong>
                      {String(selectedData.knowledge_item_id ?? "—")}
                    </strong>
                  </div>

                </>

              )}

            </div>

          ) : selectedEdge && selectedEdgeData ? (

            <div className="knowledge-map-details">

              <span className="knowledge-map-detail-type">
                RELATIONSHIP
              </span>

              <h4>{String(selectedEdge.label ?? "Connection")}</h4>

              <div className="map-detail-block">
                <span>Relationship Type</span>
                <p>
                  {String(
                    selectedEdgeData.relation_type ?? "Assignment"
                  )}
                </p>
              </div>

              {selectedEdgeData.work_status && (
                <div className="map-detail-row">
                  <span>Work Status</span>
                  <strong>
                    {String(selectedEdgeData.work_status)}
                  </strong>
                </div>
              )}

              {selectedEdgeData.evidence_excerpt ? (

                <div className="map-detail-block">
                  <span>Supporting Evidence</span>
                  <p className="map-evidence-text">
                    {String(selectedEdgeData.evidence_excerpt)}
                  </p>
                </div>

              ) : (

                <div className="map-detail-block">
                  <span>Assignment Connection</span>
                  <p>
                    This connection comes from an approved knowledge
                    item with a verified project member assignment.
                  </p>
                </div>

              )}

              {selectedEdgeData.source_filename && (
                <div className="map-detail-block">
                  <span>Source Document</span>
                  <p>
                    {String(selectedEdgeData.source_filename)}
                  </p>

                  <small>
                    {String(selectedEdgeData.source_locator ?? "")}
                  </small>
                </div>
              )}

            </div>

          ) : (

            <div className="knowledge-map-inspector-empty">
              <GitBranch size={29} />

              <strong>Select a node or connection</strong>

              <p>
                Click a person, knowledge item or relationship
                to inspect its details and supporting evidence.
              </p>
            </div>

          )}

        </aside>

      </div>

          
    {/* RELATIONSHIP BUILDER */}

<RelationshipManager
  projectId={projectId}
  onChanged={() => {
    void loadGraph();
  }}
/>
      {/* GRAPH LEGEND */}

      <div className="knowledge-map-legend">

        <strong>Graph Legend</strong>

        <span>
          <i className="legend-person" />
          People
        </span>

        <span>
          <i className="legend-task" />
          Tasks
        </span>

        <span>
          <i className="legend-decision" />
          Decisions
        </span>

        <span>
          <i className="legend-blocker" />
          Blockers
        </span>

        <span>
          <i className="legend-dependency" />
          Dependencies
        </span>

      </div>


      {/* INFORMATION NOTE */}

      <div className="knowledge-map-note">
        <CheckCircle2 size={16} />

        <span>
          This graph displays approved knowledge records and approved
          evidence-backed relationships only. Assignment connections
          use verified owner IDs. Dragging a node changes its visual
          position, not the saved project data.
        </span>
      </div>

    </section>
  );
}

export default KnowledgeMap;